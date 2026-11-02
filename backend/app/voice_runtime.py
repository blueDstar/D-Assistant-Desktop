"""Reusable local audio worker with bounded lifetime, cancellation and no raw audio files."""
import asyncio
import json
import os
import sys
import time

from fastapi import HTTPException

from .config import ROOT


class VoiceRuntime:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.process = None
        self.idle = None
        self.loaded = []
        self.serial = 0

    async def close(self):
        if self.idle:
            self.idle.cancel(); self.idle = None
        if self.process and self.process.returncode is None:
            self.process.kill()
            await self.process.wait()
        self.process = None
        self.loaded = []

    async def release_idle(self):
        if not self.lock.locked():
            async with self.lock:
                await self.close()

    async def _expire(self):
        await asyncio.sleep(180)
        async with self.lock:
            self.idle = None
            await self.close()

    async def call(self, mode, payload, request):
        started = time.perf_counter()
        acquired = False
        try:
            async with asyncio.timeout(150):
                while self.lock.locked():
                    if await request.is_disconnected():
                        raise HTTPException(499, 'Đã hủy âm thanh')
                    await asyncio.sleep(.1)
                async with self.lock:
                    acquired = True
                    if self.idle:
                        self.idle.cancel(); self.idle = None
                    reused = bool(self.process and self.process.returncode is None)
                    if not reused:
                        self.process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'app.voice_worker', 'serve', stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, cwd=ROOT / 'backend', env=os.environ | {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1', 'PYTHONUTF8': '1'}, limit=24 * 1024 * 1024)
                    self.serial += 1
                    packet = {'id': self.serial, 'mode': mode, 'payload': payload}
                    self.process.stdin.write(json.dumps(packet, ensure_ascii=False).encode() + b'\n')
                    await self.process.stdin.drain()
                    read = asyncio.create_task(self.process.stdout.readline())
                    try:
                        while not read.done():
                            if await request.is_disconnected():
                                raise HTTPException(499, 'Đã hủy âm thanh')
                            await asyncio.sleep(.05)
                        line = await read
                    finally:
                        if not read.done(): read.cancel()
                    if not line:
                        raise HTTPException(503, 'Voice worker đã dừng. Thử lại để nạp engine local.')
                    response = json.loads(line)
                    if response.get('id') != self.serial:
                        raise HTTPException(503, 'Voice response không khớp phiên')
                    self.loaded = response.get('loaded', [])
                    self.idle = asyncio.create_task(self._expire())
                    if not response.get('ok'):
                        raise HTTPException(422, response.get('error', 'Voice lỗi')[:800])
                    return response['result'], {'elapsed_seconds': time.perf_counter() - started, 'worker_seconds': response['worker_seconds'], 'worker_reused': reused}
        except TimeoutError:
            if acquired:
                await self.close()
            raise HTTPException(504, 'Xử lý voice quá 150 giây. Chọn đoạn ngắn hơn.')
        except BaseException:
            if acquired:
                await self.close()
            raise


runtime = VoiceRuntime()
