import base64
import time
import asyncio
import contextlib
import httpx

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from typing import Literal
from fastapi.responses import Response
from pydantic import Field

from . import db, ollama
from .config import MAX_UPLOAD
from .schemas import StrictModel
from .voice_runtime import runtime
from contextlib import asynccontextmanager

router = APIRouter(prefix="/api/voice", tags=["voice"])


@asynccontextmanager
async def language_audio_slot(enabled,request):
    if not enabled:
        yield
        return
    # RAM 8 GB: do not retain the 4B LLM beside Whisper Small + Kokoro.
    while ollama.HEAVY_LOCK.locked():
        if await request.is_disconnected():raise HTTPException(499,'Đã hủy âm thanh')
        await asyncio.sleep(.1)
    async with ollama.HEAVY_LOCK:
        config=db.settings();owned={config['model'],config['fast_model'],config['coding_model']}
        try:
            async with ollama.client(30) as client:
                response=await client.get('/api/ps');response.raise_for_status()
                for model in response.json().get('models',[]):
                    name=model.get('name',model.get('model'))
                    if name in owned:
                        result=await client.post('/api/generate',json={'model':name,'stream':False,'keep_alive':0})
                        result.raise_for_status()
        except httpx.ConnectError:
            pass  # Local audio remains usable while the LLM service is off.
        yield


class SpeechInput(StrictModel):
    text: str = Field(min_length=1, max_length=12000)
    speed: float = Field(default=1.0, ge=0.5, le=2)
    language: Literal['vi','en','ja'] = 'vi'


class WarmInput(StrictModel):
    quality: bool = False
    project_id: str = Field(default='general', max_length=80)
    use_knowledge: bool = True
    private: bool = False


@router.post("/transcribe")
async def transcribe(request: Request, file: UploadFile = File(...), context:Literal['general','desktop','confirmation']=Form('general'), language:Literal['vi','en','ja','auto']|None=Form(None)):
    data = await file.read(MAX_UPLOAD + 1)
    await file.close()
    if not data or len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Audio rỗng hoặc vượt giới hạn upload.")
    selected=language or db.settings()['stt_language']
    async with language_audio_slot(selected in {'en','ja'} or context=='general',request):
        output, timing = await runtime.call('stt', {'audio': base64.b64encode(data).decode('ascii'), 'language': selected,'context':context}, request)
    return output | timing | {"raw_audio_saved": False}


@router.post("/synthesize")
async def synthesize(body: SpeechInput, request: Request):
    payload = body.model_dump() | {'pronunciations': db.settings()['pronunciations']}
    async with language_audio_slot(body.language in {'en','ja'},request):
        output, timing = await runtime.call('tts', payload, request)
    return Response(base64.b64decode(output['audio']), media_type="audio/wav", headers={"Cache-Control": "no-store", "X-Elapsed-Seconds": str(round(timing['elapsed_seconds'], 3)), 'X-Worker-Reused': str(timing['worker_reused']).lower(), "X-Raw-Audio-Saved": "false"})


@router.post('/prepare')
async def prepare(request:Request):
    # Engine preparation only. Do not prefill a language model before a command.
    output,timing=await runtime.call('warm',{},request)
    return output|timing|{'llm_warmed':False,'raw_audio_saved':False}


@router.post('/warm')
async def warm(body: WarmInput, request: Request):
    started = time.perf_counter()
    result, timing = await runtime.call('warm', {}, request)
    from .schemas import ChatInput
    from .performance import runtime_config
    from .prompts import build_context
    from .agent import calculate_tool
    config = runtime_config(db.settings(), ChatInput(text='Xin chào.', request_id='voice-warmup', project_id=body.project_id, performance='quality' if body.quality else None, use_knowledge=body.use_knowledge, voice_conversation=True))
    if not ollama.HEAVY_LOCK.locked():
        async with ollama.HEAVY_LOCK:
            try:
                model = config['model']
                project = db.one('SELECT * FROM projects WHERE id=?', (body.project_id,))
                if not project:
                    raise ValueError('Không tìm thấy dự án')
                messages = build_context(config, project, [], 'Xin chào.')
                if body.private:
                    messages[0]['content'] += '\nĐây là phiên không lưu. Chỉ giữ working context của tab. Không có ghi nhớ dài hạn hoặc dữ liệu huấn luyện; không nhận đã lưu bộ nhớ khi người dùng nói hãy nhớ.'
                payload = {'model': model, 'messages': messages, 'stream':False, 'think':False, 'keep_alive':config.get('keep_alive','5m'),'options':{'num_ctx':config['context'],'num_predict':1,'num_thread':4,'num_gpu':0}}
                info = await ollama.diagnostics()
                if config.get('native_tools') and any(row['name']==model and row.get('calculate_verified') for row in info['models']):
                    payload['tools'] = [calculate_tool()]
                async with ollama.client(120) as client:
                    pending = asyncio.create_task(client.post('/api/chat', json=payload))
                    try:
                        while not pending.done():
                            if await request.is_disconnected():
                                raise HTTPException(499, 'Đã hủy chuẩn bị hội thoại')
                            await asyncio.sleep(.1)
                        response = await pending
                    finally:
                        if not pending.done():
                            pending.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await pending
                    response.raise_for_status()
                    result['llm_warmed'] = model
            except Exception:
                result['llm_warmed'] = False
    return result | timing | {'total_seconds': time.perf_counter() - started}


@router.get('/status')
def status():
    return {'worker_running': bool(runtime.process and runtime.process.returncode is None), 'loaded': runtime.loaded, 'busy': runtime.lock.locked(), 'idle_seconds': 180, 'raw_audio_saved': False}
