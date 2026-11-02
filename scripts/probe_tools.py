"""Probe native calculate on the actual local model, pin evidence to its digest."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app import db, ollama
from app.agent import calculate_tool
from app.config import DATA, DEFAULTS
from app.tools import Calculate, calculate


async def main(model):
    diagnostic = await ollama.diagnostics()
    selected = next(row for row in diagnostic['models'] if row['name'] == model)
    started = time.perf_counter()
    calls, answer = [], ''
    async for event in ollama.stream([{'role': 'system', 'content': 'Bạn có công cụ calculate. Khi người dùng yêu cầu tính, phải gọi công cụ đó với biểu thức chính xác.'}, {'role': 'user', 'content': 'Hãy gọi calculate để tính 120*2*3.14159/60 với nhãn đơn vị rad/s.'}], DEFAULTS | {'model': model, 'max_output': 192}, asyncio.Event(), [calculate_tool()]):
        if event['type'] == 'tool_call': calls.append(event['call'])
        elif event['type'] == 'token': answer += event['text']
    passed = False
    for call in calls:
        function = call.get('function', {})
        if function.get('name') == 'calculate':
            result = calculate(Calculate.model_validate(function['arguments']))
            passed = abs(result['value'] - 12.56636) < 0.00001
    record = {'model': model, 'digest': selected['digest'], 'calculate_pass': passed, 'calls': calls, 'text': answer, 'seconds': time.perf_counter() - started, 'tested_at': db.now()}
    path = DATA / 'models' / 'tool-capabilities.json'
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    previous = [row for row in previous if row['digest'] != selected['digest']]
    path.write_text(json.dumps([*previous, record], ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--model', required=True)
    asyncio.run(main(parser.parse_args().model))
