import asyncio
import contextlib
import json
import re
import time

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from . import db, ollama
from .config import TIMEOUT
from .prompts import VERSION, build_context
from .schemas import ChatInput

RUNNING: dict[str, asyncio.Event] = {}


async def chat_response(body: ChatInput, request: Request):
    from .performance import runtime_config
    config = runtime_config(db.settings(), body)
    project = db.one("SELECT * FROM projects WHERE id=?", (body.project_id,))
    if not project:
        raise HTTPException(404, "Không tìm thấy dự án")
    if body.request_id in RUNNING or db.one("SELECT id FROM messages WHERE request_id=?", (body.request_id,)):
        raise HTTPException(409, "Request ID đã được sử dụng; không gửi lặp.")
    persist = not body.private and config["save_history"]
    conversation_id = body.conversation_id
    history = body.history if not persist else []
    if conversation_id:
        conversation = db.one("SELECT * FROM conversations WHERE id=? AND project_id=?", (conversation_id, body.project_id))
        if not conversation:
            raise HTTPException(404, "Hội thoại không thuộc dự án đã chọn")
        if persist:
            history = db.rows("SELECT id,role,content,metadata FROM messages WHERE conversation_id=? AND status='completed' ORDER BY created_at", (conversation_id,))[-24:]
    elif persist:
        conversation_id = db.uid()
    # Persisted clients cannot supply fake routing history. Private sessions
    # use only their validated working history, never another project's data.
    routing_body=body.model_copy(update={'history':[{'role':m['role'],'content':m['content'][:2000]} for m in history[-6:]]})
    config=runtime_config(db.settings(),routing_body)
    display_text = body.text
    continuation = None
    if body.continue_response:
        from .continuation import continuation_context
        body = body.model_copy(update={'response_length':'long'})
        config = runtime_config(db.settings(),routing_body.model_copy(update={'response_length':'long'}))
        prompt, continuation = continuation_context(body, history, persist, conversation_id, config)
        history = []
        body = body.model_copy(update={'text': prompt})
    message_id, user_id = db.uid(), db.uid()
    from .career_answers import factual_answer
    factual = None if body.continue_response else factual_answer(body.text)
    answer_source = 'career_ledger'
    if factual is None and not body.continue_response and not body.tutor and body.mode == 'chat' and not body.source_ids:
        from .quick_answers import quick_answer
        factual = quick_answer(body.text, has_history=bool(history))
        if factual is not None:
            answer_source = 'local_quick_reply'
    additions, citations = "", []
    # Imports are local modules, not dynamic model-supplied code.
    from .research import chat_context
    if factual is None:
        if body.tutor:
            config['tutor'] = body.tutor.model_dump()
        additions, citations = chat_context(body, config)
        try:
            messages = build_context(config, project, history, body.text, additions, body.mode)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        if config.get('references_omitted'):citations=[]
    else:
        messages = [{'role':'system','content':'Phản hồi trực tiếp từ dữ liệu local.'}]
    if not persist:
        messages[0]['content'] += '\nĐây là phiên không lưu. Chỉ giữ working context của tab. Không có ghi nhớ dài hạn hoặc dữ liệu huấn luyện; không nhận đã lưu bộ nhớ khi người dùng nói hãy nhớ.'
    metadata = {"model": config["model"], "config": config, "prompt_version": VERSION, "citations": citations}
    if continuation is not None:
        metadata['continuation'] = continuation
    if body.tutor:
        metadata['tutor']=body.tutor.model_dump()
    if factual is not None:
        metadata.update(model='Phản hồi nhanh local' if answer_source=='local_quick_reply' else 'Sổ ứng tuyển · dữ liệu đã lưu', answer_source=answer_source, response_profile='verified_records')
    if persist:
        with db.connect() as connection:
            if not body.conversation_id:
                connection.execute("INSERT INTO conversations VALUES(?,?,?,?,?)", (conversation_id, body.project_id, display_text[:75], db.now(), db.now()))
            connection.execute("INSERT INTO messages(id,conversation_id,role,content,status,source,request_id,created_at) VALUES(?,?,?,?,?,?,?,?)", (user_id, conversation_id, "user", display_text, "completed", body.source, body.request_id, db.now()))
            connection.execute("INSERT INTO messages(id,conversation_id,role,content,status,request_id,metadata,created_at) VALUES(?,?,?,?,?,?,?,?)", (message_id, conversation_id, "assistant", "", "running", body.request_id, json.dumps(metadata, ensure_ascii=False), db.now()))
    receipt = None
    remember = None if body.continue_response else re.match(r"^(?:hãy nhớ|nhớ)\s*:\s*(.{1,1800})$", display_text, re.IGNORECASE | re.DOTALL)
    if remember and persist:
        from .research import MemoryInput, create_memory
        receipt = create_memory(MemoryInput(project_id=body.project_id, kind="project_fact", content=remember.group(1), source_message_id=user_id, approved=True))
        messages.insert(1, {"role": "system", "content": f'Biên nhận backend: đã lưu bộ nhớ {receipt["id"]} trong dự án hiện tại theo lệnh rõ ràng. Nội dung là phần sau dấu hai chấm trong tin nhắn người dùng.'})
    cancel = asyncio.Event()
    RUNNING[body.request_id] = cancel

    async def events():
        content, status, metrics = "", "error", {}
        started = time.perf_counter()
        first_token = None
        producer = None

        def encode(kind, **values):
            event = {"type": kind, "request_id": body.request_id, "message_id": message_id, **values}
            return json.dumps(event, ensure_ascii=False) + "\n"

        try:
            yield encode("status", status="queued", conversation_id=conversation_id, user_message_id=user_id, persisted=persist)
            if receipt:
                yield encode("tool_result", tool="manage_memory", result=receipt)
            for citation in citations:
                yield encode("citation", citation=citation)
            if factual is not None:
                if cancel.is_set() or await request.is_disconnected():
                    status = 'cancelled'
                    return
                yield encode('status', status='generating', model=metadata['model'], response_profile='verified_records', answer_source=answer_source)
                content, status = factual, 'completed'
                first_token = time.perf_counter() - started
                yield encode('token', text=content)
                metrics = {'first_token_seconds':first_token,'elapsed_seconds':time.perf_counter()-started,'answer_source':answer_source}
                yield encode('done', status=status, metrics=metrics, persisted=persist)
                return
            async with asyncio.timeout(TIMEOUT):
                while ollama.HEAVY_LOCK.locked():
                    if cancel.is_set() or await request.is_disconnected():
                        status = "cancelled"
                        return
                    await asyncio.sleep(0.15)
                async with ollama.HEAVY_LOCK:
                    if cancel.is_set():
                        status = "cancelled"
                        return
                    from .voice_runtime import runtime
                    if body.tutor or any(name in runtime.loaded for name in ['tts_en_ja','stt_learning']):
                        await runtime.release_idle()
                    yield encode("status", status="generating", model=config["model"], response_profile=config['response_profile'])
                    queue = asyncio.Queue(maxsize=128)

                    async def produce():
                        try:
                            from .agent import agent_stream
                            async for event in agent_stream(messages, config, cancel, body.project_id, body.request_id, persist):
                                await queue.put(event)
                        except Exception as error:
                            await queue.put({"type": "failure", "error": error})
                        finally:
                            if not asyncio.current_task().cancelling():
                                await queue.put({"type": "end"})

                    producer = asyncio.create_task(produce())
                    while True:
                        if cancel.is_set() or await request.is_disconnected():
                            status = "cancelled"
                            break
                        try:
                            event = await asyncio.wait_for(queue.get(), 0.2)
                        except TimeoutError:
                            continue
                        if event["type"] == "end":
                            status = "cancelled" if cancel.is_set() else "completed"
                            break
                        if event["type"] == "failure":
                            raise event["error"]
                        if event["type"] == "metrics":
                            metrics = event["metrics"]
                        elif event['type'] == 'provider':
                            metadata['model_digest'] = event['digest']
                            metadata['model_capabilities'] = event['capabilities']
                        elif event['type'] in {'tool_proposed', 'tool_result'}:
                            metadata.setdefault('tools', []).append(event)
                            yield encode(event['type'], **{key: value for key, value in event.items() if key != 'type'})
                        elif event["type"] == "token":
                            if first_token is None:
                                first_token = time.perf_counter() - started
                            content += event["text"]
                            yield encode("token", text=event["text"])
            # Invalid citation identifiers are never presented as verified sources.
            known = {c["label"] for c in citations}
            from .citations import validate_marks
            validated, invalid = validate_marks(content, known)
            if validated != content:
                content = validated
                yield encode('replace', text=content)
            if invalid:
                yield encode("status", status="warning", detail="Model đã tạo mã trích dẫn không có nguồn: " + ", ".join(invalid))
            metrics.update({"first_token_seconds": first_token, "elapsed_seconds": time.perf_counter() - started})
            yield encode("done", status=status, metrics=metrics, persisted=persist)
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception as error:
            status = "error"
            detail = "Quá thời gian xử lý. Giảm context/đầu ra hoặc chọn model nhẹ." if isinstance(error, TimeoutError) else str(error)
            yield encode("error", code="MODEL_ERROR", message=detail[:600])
        finally:
            cancel.set()
            if producer:
                producer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await producer
            RUNNING.pop(body.request_id, None)
            if persist:
                metadata["metrics"] = metrics
                db.execute("UPDATE messages SET content=?,status=?,metadata=? WHERE id=?", (content, status, json.dumps(metadata, ensure_ascii=False), message_id))
                db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (db.now(), conversation_id))
                if status == 'completed':
                    from .training import capture_conversation
                    capture_conversation(message_id)

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
