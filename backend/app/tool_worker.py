"""Bounded owned worker, not a security sandbox. Registry/allowlist enforce access."""
import json
import sys

from fastapi import HTTPException

from . import db
from .tools import ToolCall, execute_tool


if __name__ == '__main__':
    name, body = sys.argv[1], None
    if '--ready-signal' in sys.argv[2:]:
        print('{"ready":true}', flush=True)
    try:
        body = ToolCall.model_validate_json(sys.stdin.buffer.read(512000))
        with db.transaction():
            result = execute_tool(name, body)
        output = {'http_status': 200, 'result': result}
    except HTTPException as error:
        output = {'http_status': error.status_code, 'detail': str(error.detail)}
        if body:
            db.execute('INSERT INTO tool_audit VALUES(?,?,?,?,?,?)', (db.uid(), name, body.arguments.get('project_id'), 'error', body.operation_id, db.now()))
    except Exception as error:
        output = {'http_status': 422, 'detail': str(error)[:500]}
    sys.stdout.buffer.write(json.dumps(output, ensure_ascii=False).encode('utf-8'))
