import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import DATA, PORT
import uvicorn

STOP = ROOT / '.runtime' / 'stop-backend'


async def serve():
    server = uvicorn.Server(uvicorn.Config('app.main:app', host='127.0.0.1', port=PORT, access_log=False, timeout_graceful_shutdown=5))
    async def watch():
        while not server.should_exit:
            if STOP.exists():
                server.should_exit = True
                break
            await asyncio.sleep(.4)
    task = asyncio.create_task(watch())
    try:
        await server.serve()
    finally:
        task.cancel()


if __name__ == '__main__':
    asyncio.run(serve())
