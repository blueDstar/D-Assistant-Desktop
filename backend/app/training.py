import asyncio
import difflib
import hashlib
import json
from pathlib import Path
import re
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import Field

from . import db, ollama
from .config import DATA, ROOT, TIMEOUT
from .prompts import SYSTEM, VERSION
from .schemas import StrictModel

router = APIRouter(prefix="/api", tags=["training"])
EVAL_CANCEL: dict[str, asyncio.Event] = {}


def capture_conversation(message_id):
    """Daily chats become pending examples only; never approve/train their own output."""
    if not db.settings().get('learn_from_conversations'):
        return None
    message = db.one("SELECT m.*,c.project_id FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE m.id=? AND m.role='assistant' AND m.status='completed' AND m.no_learning=0", (message_id,))
    if not message or not message['content'].strip() or len(message['content']) > 12000:
        return None
    if db.one('SELECT id FROM approved_examples WHERE message_id=?', (message_id,)):
        return None
    metadata = json.loads(message['metadata'])
    if metadata.get('metrics', {}).get('output_truncated') or 'continuation' in metadata or metadata.get('answer_source')=='local_quick_reply':
        return None
    question = db.one("SELECT content FROM messages WHERE conversation_id=? AND role='user' AND no_learning=0 AND created_at<=? ORDER BY created_at DESC LIMIT 1", (message['conversation_id'], message['created_at']))
    if not question:
        return None
    id = db.uid()
    db.execute('INSERT INTO approved_examples VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (id, None, message['project_id'], message['conversation_id'], message_id, question['content'], message['content'], '', 'pending', 0, 0, message['project_id'] + ':' + message['conversation_id'], db.now(), db.now()))
    return id
SENSITIVE = [r"\bsk-[A-Za-z0-9_-]{12,}", r"(?i)(?:api[_ -]?key|password|secret|access_token)\s*[:=]\s*\S+", r"(?i)[A-Z]:\\Users\\", r"-----BEGIN .*PRIVATE KEY", r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"]


def sensitive_flags(text):
    return ["Có nội dung cần kiểm tra riêng tư: " + str(index + 1) for index, pattern in enumerate(SENSITIVE) if re.search(pattern, text)]


@router.get('/training/readiness')
def training_readiness(project_id: str='general'):
    from importlib.util import find_spec
    preview=dataset_preview(project_id)
    dependencies={name:find_spec(name) is not None for name in ['torch','transformers','peft','trl']}
    return {'weight_training_performed':False,'trainer_available':False,'dependencies':dependencies,
            'approved_split_counts':{split:len(rows) for split,rows in preview['splits'].items()},
            'holdout_ready':preview['holdout_ready'],
            'blockers':['Máy đã kiểm tra: RAM 7,78 GiB, MX330 2 GiB VRAM; chưa đủ cấu hình nghiệm thu để fine-tune Qwen3.5-4B/Omni lớn.','Chưa có runner huấn luyện được nghiệm thu; chưa cài stack trainer vào môi trường chạy trợ lý.']+([] if preview['holdout_ready'] else ['Chưa đủ mẫu đã duyệt ở ba nhóm độc lập cho train/validation/test.']),
            'next_step':'Tiếp tục sửa/duyệt ví dụ trong Studio. Huấn luyện trọng số cần môi trường GPU riêng, dataset đã duyệt và đánh giá trước/sau trên holdout; không tự gửi dữ liệu ra ngoài.'}


def relevant_examples(text, project_id):
    candidates = db.rows("SELECT e.* FROM approved_examples e JOIN messages m ON m.id=e.message_id WHERE e.project_id=? AND e.status='approved' AND e.reviewed=1 AND e.self_contained=1 AND m.no_learning=0", (project_id,))
    query = set(re.findall(r"\w+", text.lower()))
    scored = [(len(query & set(re.findall(r"\w+", row["question"].lower()))) / max(1, len(query)), row) for row in candidates]
    return [row for score, row in sorted(scored, key=lambda item: item[0], reverse=True)[:2] if score >= .25]


class FeedbackInput(StrictModel):
    message_id: str
    project_id: str = "general"
    rating: str = Field(pattern="^(useful|incorrect)$")
    reason: str = Field(default="", max_length=3000)
    correction: str = Field(default="", max_length=12000)
    question: str = Field(default="", max_length=16000)


@router.post("/feedback")
def feedback(body: FeedbackInput):
    message = db.one("SELECT m.*,c.project_id FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE m.id=? AND c.project_id=? AND m.role='assistant'", (body.message_id, body.project_id))
    if not message:
        raise HTTPException(404, "Cần một câu trả lời đã lưu trong dự án")
    if message["no_learning"]:
        raise HTTPException(409, "Tin nhắn đã được đánh dấu không dùng học")
    question = db.one("SELECT content FROM messages WHERE conversation_id=? AND role='user' AND created_at<=? ORDER BY created_at DESC LIMIT 1", (message["conversation_id"], message["created_at"]))
    id = db.uid()
    with db.connect() as connection:
        connection.execute("INSERT INTO feedback VALUES(?,?,?,?,?,?,?,?)", (id, body.message_id, body.project_id, body.rating, body.reason, body.correction, "pending", db.now()))
        if body.correction or body.rating == "useful":
            example_id = db.uid()
            connection.execute("INSERT INTO approved_examples VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (example_id, id, body.project_id, message["conversation_id"], body.message_id, question["content"] if question else "", body.correction or message["content"], "", "pending", 0, 0, body.project_id + ":" + message["conversation_id"], db.now(), db.now()))
    return {"id": id, "status": "pending"}


@router.get("/feedback")
def feedback_list(project_id: str = "general"):
    return db.rows("SELECT * FROM feedback WHERE project_id=? ORDER BY created_at DESC", (project_id,))


class ExampleReview(StrictModel):
    question: str = Field(min_length=1, max_length=16000)
    answer: str = Field(min_length=1, max_length=12000)
    context: str = Field(default="", max_length=10000)
    reviewed: bool
    self_contained: bool
    status: str = Field(pattern="^(approved|rejected|pending)$")


@router.get("/examples")
def examples(project_id: str = "general"):
    result = db.rows("SELECT e.*,m.no_learning FROM approved_examples e JOIN messages m ON m.id=e.message_id WHERE e.project_id=? ORDER BY e.updated_at DESC", (project_id,))
    return [row | {"sensitive_flags": sensitive_flags(row["question"] + row["answer"] + row["context"])} for row in result]


@router.put("/examples/{id}")
def review_example(id: str, body: ExampleReview):
    old = db.one("SELECT e.*,m.no_learning FROM approved_examples e JOIN messages m ON m.id=e.message_id WHERE e.id=?", (id,))
    if not old:
        raise HTTPException(404, "Không tìm thấy ví dụ")
    if body.status == "approved" and (not body.reviewed or not body.self_contained or old["no_learning"]):
        raise HTTPException(422, "Cần review riêng tư, ví dụ tự chứa và nguồn được phép học")
    if body.status == "approved" and sensitive_flags(body.question + body.answer + body.context):
        raise HTTPException(422, "Phát hiện dữ liệu nhạy cảm. Hãy viết lại/ẩn dữ liệu trước khi duyệt.")
    db.execute("UPDATE approved_examples SET question=?,answer=?,context=?,reviewed=?,self_contained=?,status=?,updated_at=? WHERE id=?", (body.question, body.answer, body.context, int(body.reviewed), int(body.self_contained), body.status, db.now(), id))
    db.execute("UPDATE feedback SET status=? WHERE id=?", (body.status, old["feedback_id"]))
    return {"ok": True, "effect": "Ví dụ được duyệt có thể vào few-shot theo độ liên quan và ngân sách context. Chưa thay đổi trọng số."}


@router.delete("/examples/{id}")
def delete_example(id: str):
    affected = [row["id"] for row in db.rows("SELECT * FROM training_exports") if id in json.loads(row["manifest"]).get("example_ids", [])]
    db.execute("DELETE FROM approved_examples WHERE id=?", (id,))
    return {"ok": True, "snapshots_containing_example": affected, "notice": "Snapshot/export/backup đã tạo vẫn cần xóa riêng."}


@router.post("/messages/{id}/exclude-learning")
def exclude_learning(id: str):
    with db.connect() as connection:
        connection.execute("UPDATE messages SET no_learning=1 WHERE id=?", (id,))
        connection.execute("UPDATE approved_examples SET status='rejected' WHERE message_id=?", (id,))
    return {"ok": True}


def normalize(text):
    return " ".join(re.findall(r"\w+", text.lower()))


def dataset_preview(project_id=None):
    query = "SELECT e.* FROM approved_examples e JOIN messages m ON m.id=e.message_id WHERE e.status='approved' AND e.reviewed=1 AND e.self_contained=1 AND m.no_learning=0"
    selected = db.rows(query + (" AND e.project_id=?" if project_id else ""), (project_id,) if project_id else ())
    accepted, blocked = [], []
    heldout = [normalize(case['prompt']) for case in evaluation_suite() if case['channel'] == 'llm']
    for example in selected:
        flags = sensitive_flags(example["question"] + example["answer"] + example["context"])
        if not example["question"].strip() or not example["answer"].strip():
            flags.append("Ví dụ trống")
        if any(difflib.SequenceMatcher(None, normalize(example['question']), question).ratio() >= .82 for question in heldout):
            flags.append('Câu hỏi gần trùng bộ holdout; không đưa vào dataset huấn luyện')
        if flags:
            blocked.append({"id": example["id"], "reasons": flags})
        else:
            accepted.append(example)
    # Union conversation families plus near-duplicate questions BEFORE splitting.
    parents = list(range(len(accepted)))
    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    duplicate_ids = set()
    for i, first in enumerate(accepted):
        for j in range(i):
            second = accepted[j]
            score = difflib.SequenceMatcher(None, normalize(first["question"]), normalize(second["question"])).ratio()
            if first["family"] == second["family"] or score >= .78:
                parents[find(i)] = find(j)
            if score >= .94 and normalize(first["answer"]) == normalize(second["answer"]):
                duplicate_ids.add(first["id"])
    groups = {}
    for i, row in enumerate(accepted):
        if row["id"] not in duplicate_ids:
            groups.setdefault(find(i), []).append(row)
    ordered = sorted(groups.values(), key=lambda group: hashlib.sha256("|".join(sorted(row["id"] for row in group)).encode()).hexdigest())
    splits = {"train": [], "validation": [], "test": []}
    for index, group in enumerate(ordered):
        split = "test" if len(ordered) >= 3 and index == len(ordered) - 1 else "validation" if len(ordered) >= 3 and index == len(ordered) - 2 else "train"
        splits[split].extend(group)
    return {"splits": splits, "blocked": blocked, "duplicates_removed": sorted(duplicate_ids), "families": len(ordered), "holdout_ready": len(ordered) >= 3, "notice": "Cần ít nhất 3 nhóm hội thoại độc lập để có đủ train/validation/test. Không dùng số lượng mẫu làm bằng chứng model tốt hơn. Regex không thay bước review riêng tư."}


@router.get("/datasets/preview")
def preview_dataset(project_id: str | None = None):
    return dataset_preview(project_id)


class DatasetExport(StrictModel):
    project_id: str | None = None
    example_ids: list[str] = Field(default_factory=list, max_length=3000)


@router.post("/datasets/export")
def export_dataset(body: DatasetExport):
    preview = dataset_preview(body.project_id)
    if body.example_ids:
        chosen = set(body.example_ids)
        for key in preview["splits"]:
            preview["splits"][key] = [row for row in preview["splits"][key] if row["id"] in chosen]
    if not any(preview["splits"].values()):
        raise HTTPException(422, "Chưa có ví dụ được duyệt đủ điều kiện")
    id = db.uid()
    directory = DATA / "exports" / id
    directory.mkdir()
    manifest = {"schema_version": 1, "id": id, "created_at": db.now(), "system_prompt_version": VERSION, "weight_training_performed": False, "holdout_ready": preview["holdout_ready"], "family_split_policy": "conversation + near-duplicate union before split", "example_ids": [], "files": {}, "provenance": [], "warnings": [preview["notice"]]}
    for split, records in preview["splits"].items():
        lines = []
        for row in records:
            user = ("Ngữ cảnh được người dùng duyệt:\n" + row["context"] + "\n\n" if row["context"] else "") + row["question"]
            lines.append(json.dumps({"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}, {"role": "assistant", "content": row["answer"]}]}, ensure_ascii=False))
            manifest["example_ids"].append(row["id"])
            manifest["provenance"].append({"example_id": row["id"], "message_id": row["message_id"], "conversation_id": row["conversation_id"], "project_id": row["project_id"], "family": row["family"], "split": split, "approved_at": row["updated_at"]})
        encoded = (("\n".join(lines) + "\n") if lines else "").encode("utf-8")
        (directory / (split + ".jsonl")).write_bytes(encoded)
        manifest["files"][split + ".jsonl"] = {"count": len(records), "sha256": hashlib.sha256(encoded).hexdigest()}
    (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    db.execute("INSERT INTO training_exports VALUES(?,?,?,?)", (id, json.dumps(manifest, ensure_ascii=False), str(directory), db.now()))
    return manifest


@router.get("/datasets/exports")
def list_exports():
    return [{"id": row["id"], "created_at": row["created_at"], "manifest": json.loads(row["manifest"])} for row in db.rows("SELECT * FROM training_exports ORDER BY created_at DESC")]


@router.get("/datasets/exports/{id}/{filename}")
def download_dataset(id: str, filename: str):
    if filename not in {"manifest.json", "train.jsonl", "validation.jsonl", "test.jsonl"}:
        raise HTTPException(404, "Tệp không hợp lệ")
    row = db.one("SELECT * FROM training_exports WHERE id=?", (id,))
    if not row:
        raise HTTPException(404, "Không tìm thấy snapshot")
    return FileResponse(Path(row["path"]) / filename, filename=filename)


@router.delete("/datasets/exports/{id}")
def remove_export(id: str):
    row = db.one("SELECT * FROM training_exports WHERE id=?", (id,))
    if row:
        folder = Path(row["path"]).resolve()
        if folder.is_relative_to((DATA / "exports").resolve()):
            for name in ("manifest.json", "train.jsonl", "validation.jsonl", "test.jsonl"):
                (folder / name).unlink(missing_ok=True)
            folder.rmdir()
        db.execute("DELETE FROM training_exports WHERE id=?", (id,))
    return {"ok": True}


def evaluation_suite():
    return json.loads((ROOT / "training" / "evaluations" / "v1_holdout.json").read_text(encoding="utf-8"))


@router.get("/evaluations/suite")
def get_suite():
    return evaluation_suite()


class EvaluationInput(StrictModel):
    model: str = Field(min_length=1, max_length=120)
    case_ids: list[str] = Field(min_length=1, max_length=40)


async def run_evaluation(id, body, config):
    cancel = asyncio.Event()
    EVAL_CANCEL[id] = cancel
    results, status = [], 'error'
    try:
        db.execute("UPDATE evaluations SET status='running' WHERE id=?", (id,))
        async with ollama.HEAVY_LOCK:
            for case in evaluation_suite():
                if case["id"] not in body.case_ids:
                    continue
                if cancel.is_set():
                    break
                if case["channel"] != "llm":
                    results.append({"case_id": case["id"], "status": "manual_required", "rubric": case["rubric"]})
                    continue
                started = time.perf_counter()
                answer, metrics = "", {}
                try:
                    async with asyncio.timeout(TIMEOUT):
                        async for event in ollama.stream([{"role": "system", "content": SYSTEM}, {"role": "user", "content": case["prompt"]}], config | {"model": body.model, "max_output": 384, "temperature": 0}, cancel):
                            if event["type"] == "token": answer += event["text"]
                            elif event["type"] == "metrics": metrics = event["metrics"]
                    checks = {needle: needle.casefold() in answer.casefold() for needle in case.get("required_terms", [])}
                    results.append({"case_id": case["id"], "status": "completed", "answer": answer, "term_checks": checks, "human_score": None, "rubric": case["rubric"], "seconds": time.perf_counter() - started, "metrics": metrics})
                except Exception as error:
                    results.append({"case_id": case["id"], "status": "error", "error": str(error)[:300]})
                db.execute("UPDATE evaluations SET results=?,updated_at=? WHERE id=?", (json.dumps(results, ensure_ascii=False), db.now(), id))
        status = "cancelled" if cancel.is_set() else "completed"
    except Exception as error:
        results.append({"status": "error", "error": str(error)[:300]})
        status = "error"
    finally:
        EVAL_CANCEL.pop(id, None)
        db.execute("UPDATE evaluations SET status=?,results=?,updated_at=? WHERE id=?", (status, json.dumps(results, ensure_ascii=False), db.now(), id))


@router.post("/evaluations")
async def create_evaluation(body: EvaluationInput, background: BackgroundTasks):
    local = await ollama.diagnostics()
    if not any(row["name"] == body.model for row in local["models"]):
        raise HTTPException(422, "Chỉ đánh giá model local đã tải")
    if db.one("SELECT COUNT(*) AS n FROM evaluations WHERE status IN ('queued','running')")["n"]:
        raise HTTPException(409, "Đã có một evaluation đang chạy")
    if set(body.case_ids) - {case["id"] for case in evaluation_suite()}:
        raise ValueError("Mã ca kiểm thử không hợp lệ")
    id, config = db.uid(), db.settings()
    selected_model = next(row for row in local['models'] if row['name'] == body.model)
    snapshot = {"runtime": config, 'model_digest': selected_model['digest'], "prompt_version": VERSION, "memory": False, "rag": False, "few_shot": False, "suite_sha256": hashlib.sha256((ROOT / "training/evaluations/v1_holdout.json").read_bytes()).hexdigest(), "case_ids": body.case_ids}
    db.execute("INSERT INTO evaluations VALUES(?,?,?,?,?,?,?)", (id, body.model, json.dumps(snapshot, ensure_ascii=False), "queued", "[]", db.now(), db.now()))
    background.add_task(run_evaluation, id, body, config)
    return {"id": id, "status": "queued"}


@router.get("/evaluations")
def evaluations():
    return [row | {"config": json.loads(row["config"]), "results": json.loads(row["results"])} for row in db.rows("SELECT * FROM evaluations ORDER BY created_at DESC LIMIT 20")]


@router.post("/evaluations/{id}/cancel")
def cancel_eval(id: str):
    if cancel := EVAL_CANCEL.get(id):
        cancel.set()
    return {"ok": True}


class HumanScore(StrictModel):
    case_id: str
    score: int = Field(ge=0, le=2)
    note: str = Field(default="", max_length=2000)


@router.post("/evaluations/{id}/score")
def score_evaluation(id: str, body: HumanScore):
    row = db.one("SELECT * FROM evaluations WHERE id=?", (id,))
    if not row or row["status"] in {"queued", "running"}:
        raise HTTPException(409, "Chờ evaluation hoàn tất")
    results = json.loads(row["results"])
    for result in results:
        if result.get("case_id") == body.case_id:
            result.update(human_score=body.score, human_note=body.note)
    db.execute("UPDATE evaluations SET results=? WHERE id=?", (json.dumps(results, ensure_ascii=False), id))
    return {"ok": True}


@router.get("/training/capabilities")
def capabilities():
    return {"feedback": True, "approved_memory": True, "few_shot_examples": True, "dataset_export": True, "evaluation": True, "weight_training": False, "reason": "Chưa có trainer LoRA/QLoRA được nghiệm thu. GPU MX330 2 GB; không tự chạy huấn luyện.", "mechanisms": {"software": "Nâng cấp mã nguồn", "model": "Đổi model local", "knowledge": "Bộ nhớ/RAG/ví dụ được duyệt", "fine_tuning": "Thay đổi trọng số — chưa triển khai"}}
