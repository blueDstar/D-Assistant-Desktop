"""Small bounded native tool loop; automatic tools cannot read files or write data."""
import json

from pydantic import ValidationError

from . import db, ollama
from .prompts import token_cost
from .tools import Calculate, calculate


def calculate_tool():
    return {'type': 'function', 'function': {'name': 'calculate', 'description': 'Tính số học + - * / // % ** bằng parser an toàn. Dùng cho phép tính số và đổi đơn vị khi công thức đã rõ. Không thực thi code.', 'parameters': Calculate.model_json_schema()}}


async def agent_stream(messages, config, cancel, project_id, request_id, persist):
    info = await ollama.diagnostics()
    selected = next((row for row in info['models'] if row['name'] == config['model']), {})
    yield {'type': 'provider', 'model': config['model'], 'digest': selected.get('digest'), 'capabilities': selected.get('capabilities', [])}
    enabled = bool(config.get('native_tools') and selected.get('calculate_verified'))
    if not enabled:
        async for event in ollama.stream(messages, config, cancel):
            if event['type']=='tool_call':
                raise ValueError('Model đề xuất công cụ chưa được cấp trong lượt này; không thực hiện.')
            yield event
        return
    messages = list(messages)
    total_calls = 0
    all_metrics = []
    for round_index in range(3):
        if cancel.is_set():
            return
        calls, content = [], ''
        async for event in ollama.stream(messages, config, cancel, [calculate_tool()] if round_index < 2 and total_calls < 2 else None):
            if event['type'] == 'token':
                content += event['text']
                yield event
            elif event['type'] == 'tool_call':
                if event['call'] not in calls:
                    calls.append(event['call'])
            elif event['type'] == 'metrics':
                all_metrics.append(event['metrics'])
        if not calls:
            combined = {key: sum(row.get(key) or 0 for row in all_metrics) for key in ('total_duration', 'load_duration', 'prompt_eval_count', 'eval_count', 'eval_duration')}
            final = all_metrics[-1] if all_metrics else {}
            yield {'type': 'metrics', 'metrics': combined | {'model_rounds': len(all_metrics), 'tool_calls': total_calls, 'done_reason': final.get('done_reason'), 'output_truncated': final.get('output_truncated', False)}}
            return
        if total_calls + len(calls) > 2 or round_index >= 2:
            raise ValueError('Đã đạt giới hạn 2 công cụ / 3 lượt model. Thu hẹp yêu cầu rồi thử lại.')
        messages.append({'role': 'assistant', 'content': content, 'tool_calls': calls})
        for call in calls:
            total_calls += 1
            function = call.get('function', {})
            name, arguments = function.get('name', ''), function.get('arguments', {})
            yield {'type': 'tool_proposed', 'tool': name, 'arguments': arguments}
            status = 'error'
            try:
                # No model-provided name can expand the automatic registry.
                if name != 'calculate':
                    raise ValueError('Công cụ tự động không được cấp quyền. Đọc file/ghi dữ liệu cần thao tác UI rõ ràng.')
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                result = calculate(Calculate.model_validate(arguments))
                status = 'completed'
            except (ValueError, ValidationError, SyntaxError, TypeError) as error:
                result = {'error': str(error)[:350]}
            operation_id = f'{request_id}-{total_calls}'
            event = {'type': 'tool_result', 'tool': name, 'status': status, 'result': result, 'operation_id': operation_id}
            yield event
            messages.append({'role': 'tool', 'tool_name': name, 'content': json.dumps(result, ensure_ascii=False)})
            if persist:
                db.execute('INSERT INTO tool_audit VALUES(?,?,?,?,?,?)', (db.uid(), name, project_id, status, operation_id, db.now()))
        if sum(token_cost(json.dumps(message, ensure_ascii=False), config['model']) for message in messages) > config['context'] - config['max_output'] - 384:
            raise ValueError('Ngữ cảnh sau công cụ quá dài. Thu hẹp phạm vi tài liệu/lịch sử hoặc tăng context.')
        yield {'type': 'token', 'text': '\n\n'}
