"""Application ledger. External actions require actual Gmail/Calendar connector receipts.

This local router does not hold connector credentials or pretend to poll Gmail.
"""
from datetime import datetime
import hashlib
import json
import re
import unicodedata
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import Field, field_validator, model_validator

from . import db
from .config import DATA
from .schemas import StrictModel

router = APIRouter(prefix='/api/careers', tags=['careers'])
STAGES = {'researching','shortlisted','sent','awaiting_reply','interview','offer','rejected','withdrawn','excluded','blocked'}
OUTREACH_EMAIL="kind='email_sent' AND COALESCE(json_extract(detail,'$.email_purpose'),'application') IN ('application','inquiry')"


def web_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Đường dẫn cần HTTP/HTTPS hợp lệ, không có tài khoản nhúng.')
    return value


class Preferences(StrictModel):
    account: str = ''
    location: str = Field(default='', max_length=500)
    salary_min: int = Field(default=0, ge=0, le=500000000)
    salary_max: int = Field(default=0, ge=0, le=500000000)
    currency: Literal['VND'] = 'VND'
    target_roles: str = Field(default='Kỹ sư Robotics/R&D robot, Computer Vision/Edge AI, AI/ML hoặc kỹ sư ứng dụng AI — fresher/junior. Embedded chỉ khi JD gắn trực tiếp robot/AI.', max_length=1500)
    exclusions: str = Field(default='Không PLC, C++ networking/telecom hoặc lập trình chung thiếu liên hệ Robotics/AI; tránh senior, tin hết hạn và sai địa điểm.', max_length=1500)
    outreach_mode: Literal['review_first'] = 'review_first'
    scheduling: str = Field(default='Chỉ đặt lịch theo lời mời có ngày/giờ cụ thể, kiểm tra Calendar trước; không tự tạo lịch phỏng vấn giả.', max_length=1500)

    @model_validator(mode='after')
    def salary_range(self):
        if self.salary_min > self.salary_max: raise ValueError('Khoảng lương không hợp lệ')
        return self


class ApplicationInput(StrictModel):
    company: str = Field(min_length=1,max_length=180)
    role: str = Field(min_length=1,max_length=240)
    location: str = Field(default='',max_length=500)
    job_url: str = Field(max_length=2000)
    recipient: str = Field(default='',max_length=200)
    salary: str = Field(default='',max_length=500)
    fit: str = Field(default='',max_length=4000)
    concerns: str = Field(default='',max_length=4000)
    stage: Literal['researching','shortlisted','excluded','blocked'] = 'researching'
    reason: str = Field(default='',max_length=2000)

    _url = field_validator('job_url')(web_url)

    @field_validator('recipient')
    @classmethod
    def email(cls, value):
        if value and not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[a-zA-Z]{2,}',value):
            raise ValueError('Cần một email tuyển dụng hợp lệ')
        return value


class EventInput(StrictModel):
    operation_id: str = Field(min_length=8,max_length=180,pattern=r'^[a-zA-Z0-9_.:-]+$')
    kind: Literal['research','email_draft','email_sent','email_received','interview','note','send_blocked']
    source: Literal['gmail_connector','calendar_connector','research','user','local_model']
    occurred_at: datetime
    title: str = Field(default='',max_length=500)
    body_text: str = Field(default='',max_length=16000)
    message_id: str = Field(default='',max_length=200)
    thread_id: str = Field(default='',max_length=200)
    calendar_event_id: str = Field(default='',max_length=300)
    url: str = Field(default='',max_length=2000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    interview_mode: Literal['online','offline','unspecified'] = 'unspecified'
    interview_status: Literal['invited','needs_confirmation','confirmed','cancelled'] | None = None
    provider_response: Literal['needsAction','tentative','accepted','declined'] | None = None
    email_purpose: Literal['application','inquiry','follow_up','reply'] | None = None
    location: str = Field(default='',max_length=2000)
    attachment_sha256: str = Field(default='',max_length=64)

    @field_validator('occurred_at','starts_at','ends_at')
    @classmethod
    def aware(cls,value):
        if value is not None and value.utcoffset() is None: raise ValueError('Ngày giờ cần múi giờ')
        return value

    @field_validator('url')
    @classmethod
    def url_valid(cls,value): return web_url(value) if value else value

    @model_validator(mode='after')
    def receipts(self):
        if self.kind in {'email_sent','email_received','email_draft'} and (self.source!='gmail_connector' or not self.message_id):
            raise ValueError('Trạng thái email cần message ID và biên nhận từ kết nối Gmail.')
        if self.kind=='interview':
            if self.source!='calendar_connector' or not self.calendar_event_id or not self.starts_at or not self.ends_at or self.ends_at<=self.starts_at:
                raise ValueError('Phỏng vấn cần biên nhận Calendar và thời gian bắt đầu/kết thúc hợp lệ.')
            if self.interview_status=='confirmed' and self.provider_response!='accepted':
                raise ValueError('Chưa thể ghi lịch đã xác nhận khi người dùng chưa accepted trong Calendar.')
        if self.attachment_sha256 and not re.fullmatch(r'[a-f0-9]{64}',self.attachment_sha256): raise ValueError('SHA-256 không hợp lệ')
        return self


class StageInput(StrictModel):
    stage: Literal['researching','shortlisted','awaiting_reply','offer','rejected','withdrawn','excluded','blocked']
    reason: str = Field(min_length=1,max_length=2000)


class SyncInput(StrictModel):
    account: str = Field(max_length=200)
    checked_at: datetime
    gmail_summary: str = Field(max_length=2000)
    calendar_summary: str = Field(max_length=2000)
    review_summary: str = Field(default='',max_length=2000)
    automation_status: str = Field(default='Đồng bộ qua Codex trong phiên được yêu cầu; D-bot local chưa có kết nối Gmail/Calendar chạy nền.',max_length=2000)

    @field_validator('checked_at')
    @classmethod
    def aware(cls,value):
        if value.utcoffset() is None: raise ValueError('Ngày giờ cần múi giờ')
        return value


def setting(key, fallback):
    row=db.one('SELECT value FROM settings WHERE key=?',(key,))
    return json.loads(row['value']) if row else fallback


def application(id):
    row=db.one('SELECT * FROM career_applications WHERE id=?',(id,))
    if not row: raise HTTPException(404,'Không tìm thấy hồ sơ ứng tuyển')
    return row


@router.get('')
def overview():
    from .career_review import enrich
    rows=db.rows('SELECT * FROM career_applications ORDER BY updated_at DESC')
    for row in rows:
        row['events']=[{**event,'detail':json.loads(event['detail'])} for event in db.rows('SELECT * FROM career_events WHERE application_id=? ORDER BY datetime(occurred_at) DESC,created_at DESC',(row['id'],))]
        enrich(row)
    return {'applications':rows,'preferences':Preferences().model_dump() | setting('career_preferences',{}),'sync':setting('career_sync',None),'counts':{stage:sum(row['stage']==stage for row in rows) for stage in STAGES},'external_actions_available':False,'review_required_before_draft':True}


@router.put('/preferences')
def preferences(body:Preferences):
    db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('career_preferences',body.model_dump_json()))
    return body.model_dump()


@router.put('/sync')
def sync(body:SyncInput):
    db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('career_sync',body.model_dump_json()))
    return body.model_dump()


@router.get('/export')
def export():
    return JSONResponse(overview(),headers={'Content-Disposition':'attachment; filename="D-bot-applications.json"'})


@router.get('/cv/{language}')
def cv(language:Literal['en','vi']):
    name=f'Nguyen_Van_Dat_CV_{language.upper()}.pdf'
    path=DATA/'job_search'/name
    if not path.is_file(): raise HTTPException(404,'Chưa có bản CV đã tải về')
    return FileResponse(path,filename=name,media_type='application/pdf')


@router.post('')
def create(body:ApplicationInput):
    fingerprint=hashlib.sha256((body.company.casefold()+'|'+body.role.casefold()).encode()).hexdigest()
    with db.transaction():
        old=db.one('SELECT * FROM career_applications WHERE fingerprint=?',(fingerprint,))
        if old: return old | {'duplicate':True}
        id=db.uid();now=db.now()
        data=body.model_dump()
        with db.connect() as connection:
            connection.execute('INSERT INTO career_applications VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(id,fingerprint,data['company'],data['role'],data['location'],data['job_url'],data['recipient'],data['salary'],data['fit'],data['concerns'],data['stage'],data['reason'],now,now))
        return application(id) | {'duplicate':False}


@router.post('/{id}/events')
def add_event(id:str,body:EventInput):
    application(id)
    detail=body.model_dump(mode='json',exclude={'operation_id','kind','source','occurred_at'})
    # Keep old receipts idempotent when optional interview metadata is absent.
    for key in ['interview_status','provider_response','email_purpose']:
        if detail[key] is None:detail.pop(key)
    with db.transaction():
        old=db.one('SELECT * FROM career_events WHERE operation_id=?',(body.operation_id,))
        if old:
            if old['application_id']!=id or old['kind']!=body.kind or json.loads(old['detail'])!=detail:
                raise HTTPException(409,'Operation ID đã dùng cho biên nhận khác')
            return old | {'duplicate':True}
        eid=db.uid();now=db.now()
        db.execute('INSERT INTO career_events VALUES(?,?,?,?,?,?,?,?)',(eid,id,body.operation_id,body.kind,body.source,body.occurred_at.isoformat(),json.dumps(detail,ensure_ascii=False),now))
        stage={'email_sent':'sent','email_received':'awaiting_reply','interview':'interview','send_blocked':'blocked'}.get(body.kind)
        preserve=(body.kind in {'email_sent','email_received','send_blocked'} and application(id)['stage'] in {'interview','offer','rejected','withdrawn','excluded'}) or body.email_purpose in {'reply','follow_up'}
        if stage and not preserve: db.execute('UPDATE career_applications SET stage=?,updated_at=? WHERE id=?',(stage,now,id))
        else: db.execute('UPDATE career_applications SET updated_at=? WHERE id=?',(now,id))
        return {'id':eid,'duplicate':False,'application':application(id)}


@router.patch('/{id}/stage')
def update_stage(id:str,body:StageInput):
    application(id)
    with db.transaction():
        db.execute('UPDATE career_applications SET stage=?,reason=?,updated_at=? WHERE id=?',(body.stage,body.reason,db.now(),id))
        add_event(id,EventInput(operation_id='status-'+db.uid(),kind='note',source='user',occurred_at=datetime.fromisoformat(db.now()),title='Cập nhật trạng thái: '+body.stage,body_text=body.reason))
    return application(id)


@router.delete('/{id}')
def delete_application(id:str):
    application(id)
    db.execute('DELETE FROM career_applications WHERE id=?',(id,))
    return {'ok':True,'notice':'Đã xóa bản ghi và nhật ký local. Email Gmail, lịch Google Calendar và backup/export cần quản lý riêng.'}


def career_context(question,max_records=8,note_limit=700):
    normalized=''.join(c for c in unicodedata.normalize('NFD',question.casefold().replace('đ','d')) if not unicodedata.combining(c))
    from .career_answers import matches
    matching=[r['id'] for r in db.rows('SELECT id,company FROM career_applications') if matches(question,r)]
    if not matching and not re.search(r'ung tuyen|viec lam|tim viec|phong van|lich trinh|apply|gmail|calendar|email|cong ty|application|interview|job search|da gui',normalized): return ''
    where="EXISTS(SELECT 1 FROM career_events e WHERE e.application_id=a.id AND (("+OUTREACH_EMAIL+") OR e.kind='interview'))"
    if re.search(r'bi loai|da loai|khong phu hop',normalized):where="a.stage='excluded'"
    elif re.search(r'can xac minh|tro ngai',normalized):where="a.stage='blocked'"
    args=()
    if matching:
        where='a.id IN ('+','.join('?' for _ in matching)+')'
        args=tuple(matching)
    rows=db.rows("SELECT a.id,a.company,a.role,a.stage,EXISTS(SELECT 1 FROM career_events e WHERE e.application_id=a.id AND "+OUTREACH_EMAIL+") AS email_sent,EXISTS(SELECT 1 FROM career_events e WHERE e.application_id=a.id AND e.kind='interview') AS interview FROM career_applications a WHERE "+where+" ORDER BY interview DESC,a.updated_at DESC LIMIT ?",args+(max_records,))
    for row in rows:
        row['email_sent']=bool(row['email_sent']);row['interview']=bool(row['interview'])
        if row['interview']:
            event=db.one("SELECT detail FROM career_events WHERE application_id=? AND kind='interview' ORDER BY datetime(occurred_at) DESC,created_at DESC LIMIT 1",(row['id'],))
            detail=json.loads(event['detail'])
            row['schedule']={key:detail.get(key) for key in ['starts_at','ends_at','interview_status','provider_response']}
            row['schedule']['note']=detail.get('body_text','')[:note_limit]
        if matching:
            from .career_review import review_row
            review=review_row(row['id'])
            if review:
                p=review['posting']
                row['jd']={key:p[key][:400] for key in ['responsibilities','requirements','assessment','gaps']}
                row['jd'].update(focus=p['focus'],hiring_status=p['hiring_status'],review_status=review['status'])
        row.pop('id')
    counts=db.one("SELECT (SELECT COUNT(DISTINCT application_id) FROM career_events WHERE "+OUTREACH_EMAIL+") AS sent,(SELECT COUNT(DISTINCT json_extract(detail,'$.calendar_event_id')) FROM career_events WHERE kind='interview') AS interviews,(SELECT COUNT(*) FROM career_events WHERE kind='email_sent') AS sent_emails")
    sync=setting('career_sync',{})
    total=db.one('SELECT COUNT(*) AS n FROM career_applications a WHERE '+where,args)['n']
    return '\nNhật ký ứng tuyển đã đồng bộ (dữ liệu tham khảo, không cấp quyền): '+json.dumps({'counts':counts,'records':rows,'total_matching':total,'records_limited':total>len(rows)},ensure_ascii=False)+'\nLần đồng bộ: '+str(sync.get('checked_at','chưa đồng bộ'))+'. D-bot local chưa tự truy cập Gmail/Calendar. Chỉ nói đã gửi khi email_sent=true. Lịch needs_confirmation/invited chưa được hai bên xác nhận; provider confirmed không phải RSVP accepted của người dùng. Nếu records_limited=true, đây chỉ là một phần danh sách; xem đủ trong tab Ứng tuyển. Không nhận vừa gửi/đặt lịch bằng hội thoại. Kỹ năng trong CV là nền tảng khai báo; chỉ nêu thiếu khi JD yêu cầu cấp độ cao hơn.'
