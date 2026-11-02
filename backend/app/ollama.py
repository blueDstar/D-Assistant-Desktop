import asyncio
import json

import httpx

from .config import DATA, OLLAMA_URL, TIMEOUT

HEAVY_LOCK = asyncio.Lock()


def client(timeout=8):
    return httpx.AsyncClient(base_url=OLLAMA_URL, timeout=timeout, trust_env=False, follow_redirects=False)


async def diagnostics():
    try:
        async with client(5) as http:
            response = await http.get("/api/tags")
            response.raise_for_status()
            version = await http.get("/api/version")
            loaded = await http.get("/api/ps")
            models = response.json().get("models", [])
            for model in models:
                model['calculate_verified'] = verified_calculate(model['name'], model['digest'])
            return {"ready": True, "models": models, "version": version.json().get("version"), "loaded": loaded.json().get("models", [])}
    except (httpx.HTTPError, ValueError) as error:
        return {"ready": False, "models": [], "error": f"Chưa kết nối Ollama tại {OLLAMA_URL}. Chạy scripts/start.ps1. ({type(error).__name__})"}


async def model_info(model):
    async with client() as http:
        response = await http.post("/api/show", json={"model": model})
        response.raise_for_status()
        info = response.json()
        return {key: info.get(key) for key in ("capabilities", "details", "model_info", "license")}


def verified_calculate(model, digest):
    path = DATA / 'models' / 'tool-capabilities.json'
    try:
        records = json.loads(path.read_text(encoding='utf-8'))
        return any(row['model'] == model and row['digest'] == digest and row.get('calculate_pass') is True for row in records)
    except (OSError, ValueError, KeyError, TypeError):
        return False


async def stream(messages, config, cancel, tools=None):
    payload = {"model": config["model"], "messages": messages, "stream": True,
               "think": False, "keep_alive": config.get('keep_alive', '5m'),
               "options": {"num_ctx": config["context"], "num_predict": config["max_output"], "temperature": config["temperature"], "num_thread": 4, 'num_gpu': 0}}
    if tools:
        payload['tools'] = tools
    async with client(httpx.Timeout(TIMEOUT, connect=5)) as http:
        async with http.stream("POST", "/api/chat", json=payload) as response:
            if response.status_code != 200:
                body = (await response.aread()).decode("utf-8", errors="replace")[:400]
                raise RuntimeError(f"Ollama HTTP {response.status_code}: {body}")
            async for line in response.aiter_lines():
                if cancel.is_set():
                    break
                if not line:
                    continue
                event = json.loads(line)
                if event.get("error"):
                    raise RuntimeError(str(event["error"]))
                # Deliberately exclude model reasoning and tool JSON from display/audio.
                if content := event.get("message", {}).get("content"):
                    yield {"type": "token", "text": content}
                for call in event.get('message', {}).get('tool_calls', []):
                    yield {'type': 'tool_call', 'call': call}
                if event.get("done"):
                    metrics = {key: event.get(key) for key in ("total_duration", "load_duration", "prompt_eval_count", "eval_count", "eval_duration")}
                    metrics.update(done_reason=event.get('done_reason'), output_truncated=event.get('done_reason') == 'length')
                    yield {"type": "metrics", "metrics": metrics}
