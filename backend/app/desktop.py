"""Record local desktop dialogue; this route has no OS execution capability."""
import json
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import Field
from . import db
from .schemas import StrictModel

router=APIRouter(prefix='/api/desktop',tags=['desktop'])
class DesktopTurn(StrictModel):
    project_id:str=Field(default='general',max_length=80)
    conversation_id:str|None=None
    request_id:str=Field(min_length=8,max_length=80,pattern=r'^[a-zA-Z0-9-]+$')
    text:str=Field(min_length=1,max_length=16000)
    answer:str=Field(min_length=1,max_length=4000)
    source:Literal['voice','text']='text'
    stage:Literal['confirmation','ready','blocked','not_installed','idle','cancelled']='idle'
    private:bool=False

@router.post('/turn')
def record_turn(body:DesktopTurn):
    if not db.one('SELECT id FROM projects WHERE id=?',(body.project_id,)):raise HTTPException(404,'Không tìm thấy dự án')
    if body.conversation_id and not db.one('SELECT id FROM conversations WHERE id=? AND project_id=?',(body.conversation_id,body.project_id)):raise HTTPException(404,'Hội thoại không thuộc dự án')
    if body.private or not db.settings()['save_history']:return {'persisted':False,'conversation_id':body.conversation_id}
    with db.transaction():
        if db.one('SELECT id FROM messages WHERE request_id=?',(body.request_id,)):raise HTTPException(409,'Lượt đã ghi nhận; không ghi lặp')
        cid=body.conversation_id or db.uid();user_id=db.uid();message_id=db.uid();now=db.now()
        metadata=json.dumps({'model':'Desktop · lệnh trực tiếp','answer_source':'desktop_rules','desktop_stage':body.stage,'external_action_confirmed':False},ensure_ascii=False)
        with db.connect() as conn:
            if not body.conversation_id:conn.execute('INSERT INTO conversations VALUES(?,?,?,?,?)',(cid,body.project_id,body.text[:75],now,now))
            conn.execute('INSERT INTO messages(id,conversation_id,role,content,status,source,request_id,created_at) VALUES(?,?,?,?,?,?,?,?)',(user_id,cid,'user',body.text,'completed',body.source,body.request_id,now))
            conn.execute('INSERT INTO messages(id,conversation_id,role,content,status,request_id,metadata,created_at) VALUES(?,?,?,?,?,?,?,?)',(message_id,cid,'assistant',body.answer,'completed',body.request_id,metadata,now))
            conn.execute('UPDATE conversations SET updated_at=? WHERE id=?',(now,cid))
    return {'persisted':True,'conversation_id':cid,'user_message_id':user_id,'message_id':message_id}
