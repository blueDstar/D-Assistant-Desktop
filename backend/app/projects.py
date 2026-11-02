import hashlib
import json

from fastapi import APIRouter, HTTPException
from pydantic import Field

from . import db
from .research import delete_source
from .schemas import StrictModel

router = APIRouter(prefix='/api/projects', tags=['projects'])


def deletion_preview(id):
    project = db.one('SELECT * FROM projects WHERE id=?', (id,))
    if not project or id == 'general':
        raise HTTPException(422, 'Không xóa không gian chung; chỉ xóa dự án cụ thể.')
    counts = {table: db.one(f'SELECT COUNT(*) AS n FROM {table} WHERE project_id=?', (id,))['n'] for table in ['conversations', 'sources', 'memories', 'notes', 'feedback', 'approved_examples', 'jobs']}
    counts['messages'] = db.one('SELECT COUNT(*) AS n FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE project_id=?)', (id,))['n']
    for table in ['language_profiles','language_attempts']:
        counts[table]=db.one(f'SELECT COUNT(*) AS n FROM {table} WHERE project_id=?',(id,))['n']
    snapshots = [row['id'] for row in db.rows('SELECT * FROM training_exports') if any(item['project_id'] == id for item in json.loads(row['manifest']).get('provenance', []))]
    checksum = hashlib.sha256(json.dumps({'id': id, 'name': project['name'], 'counts': counts, 'snapshots': snapshots}, sort_keys=True).encode()).hexdigest()
    return {'project': project, 'counts': counts, 'snapshot_ids': snapshots, 'preview_hash': checksum, 'notice': 'Xóa các bản ghi và file tài liệu đang hoạt động của dự án. Backup, snapshot dataset, file đã tải và ảnh hưởng trong adapter fine-tune (nếu có) cần xử lý riêng.'}


@router.get('/{id}/delete-preview')
def preview(id: str):
    return deletion_preview(id)


class DeleteProject(StrictModel):
    confirmation_name: str = Field(min_length=1, max_length=120)
    preview_hash: str = Field(min_length=64, max_length=64)


@router.post('/{id}/delete')
def remove(id: str, body: DeleteProject):
    from .chat import RUNNING
    if RUNNING:
        raise HTTPException(409, 'Dừng các lượt chat đang chạy trước khi xóa dự án.')
    preview = deletion_preview(id)
    if body.confirmation_name != preview['project']['name'] or body.preview_hash != preview['preview_hash']:
        raise HTTPException(409, 'Nội dung đã thay đổi hoặc tên chưa khớp. Xem lại preview trước khi xóa.')
    if db.one("SELECT id FROM messages WHERE status='running' AND conversation_id IN (SELECT id FROM conversations WHERE project_id=?)", (id,)):
        raise HTTPException(409, 'Dừng chat của dự án trước khi xóa.')
    for source in db.rows('SELECT id FROM sources WHERE project_id=?', (id,)):
        delete_source(source['id'])
    with db.connect() as connection:
        # Cached tool receipts can contain old memory/note text; remove with scope.
        operation_ids = [row[0] for row in connection.execute('SELECT operation_id FROM tool_audit WHERE project_id=?', (id,))]
        for operation_id in operation_ids:
            connection.execute('DELETE FROM operations WHERE id=?', (operation_id,))
        connection.execute('DELETE FROM tool_audit WHERE project_id=?', (id,))
        connection.execute('DELETE FROM projects WHERE id=?', (id,))
    return {'ok': True, 'notice': preview['notice'], 'snapshot_ids': preview['snapshot_ids']}
