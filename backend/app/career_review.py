"""Job-specific user review. No Gmail sending or background scheduler lives here."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
import unicodedata

from fastapi import APIRouter, HTTPException
from pydantic import Field, field_validator
from typing import Literal

from . import db
from .careers import application, web_url
from .schemas import StrictModel

router = APIRouter(prefix='/api/careers', tags=['career review'])
VN = timezone(timedelta(hours=7))


def normalize(value):
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in unicodedata.normalize('NFD', value.casefold().replace('đ', 'd')) if not unicodedata.combining(c))).strip()


def company_key(value):
    name = normalize(value)
    aliases = {
        'endava': ['endava', 'dek technologies', 'dek technologies vietnam'],
        'tma': ['tma', 'tma solutions', 'tma tech group'],
        'fpt software': ['fpt', 'fpt software', 'fsoft'],
        'hpt': ['hpt', 'hpt vietnam'],
        'questx': ['questx', 'homenest', 'homenest software', 'homenest software questx'],
        'nexgen bros': ['nexgen bros', 'nexgenbros'],
        'wisdom': ['wisdom', 'wisdom engineering', 'wisdom engineering and business solutions'],
    }
    name = re.sub(r'^(cong ty (tnhh|co phan)|company|cty)\s+', '', name)
    name = re.sub(r'\s+(co ltd|limited|ltd|inc|corporation|jsc)$', '', name)
    for key, names in aliases.items():
        if name in names or any(name.startswith(n + ' ') for n in names if len(n) > 3):
            return key
    return name


def contacted_companies():
    rows = db.rows("SELECT DISTINCT a.company FROM career_applications a JOIN career_events e ON e.application_id=a.id WHERE e.kind IN ('email_sent','email_received','interview')")
    return {company_key(row['company']) for row in rows}


class PostingInput(StrictModel):
    company_intro: str = Field(default='', max_length=3000)
    responsibilities: str = Field(min_length=10, max_length=6000)
    requirements: str = Field(min_length=10, max_length=6000)
    experience: str = Field(default='', max_length=1500)
    arrangement: str = Field(default='', max_length=1500)
    focus: Literal['robotics','computer_vision','ai_ml','ai_application','outside_target','unclear'] = 'unclear'
    hiring_status: Literal['open','needs_verification','closed'] = 'needs_verification'
    location_priority: Literal['local','nearby','unknown','outside'] = 'unknown'
    posted_on: date | None = None
    deadline: date | None = None
    checked_at: datetime
    sources: list[str] = Field(min_length=1, max_length=8)
    recipient_source: str = Field(default='', max_length=2000)
    assessment: str = Field(default='', max_length=3000)
    gaps: str = Field(default='', max_length=3000)

    @field_validator('checked_at')
    @classmethod
    def aware(cls, value):
        if value.utcoffset() is None:
            raise ValueError('Ngày kiểm tra cần múi giờ')
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError('Ngày kiểm tra không được ở tương lai')
        return value

    @field_validator('sources')
    @classmethod
    def urls(cls, value): return list(dict.fromkeys(web_url(item) for item in value))

    @field_validator('recipient_source')
    @classmethod
    def recipient_url(cls, value): return web_url(value) if value else value


class ReviewInput(StrictModel):
    expected_revision: int = Field(ge=1)
    decision: Literal['approved','rejected','pending']
    note: str = Field(default='', max_length=2000)


class PlanInput(StrictModel):
    expected_revision: int = Field(ge=1)
    subject: str = Field(min_length=1, max_length=300, pattern=r'^[^\r\n]+$')
    body_text: str = Field(min_length=10, max_length=16000)
    send_after: datetime | None = None

    @field_validator('send_after')
    @classmethod
    def aware(cls, value):
        if value and (value.utcoffset() is None or value <= datetime.now(timezone.utc)):
            raise ValueError('Giờ dự kiến phải ở tương lai và có múi giờ')
        return value


def review_row(id):
    row = db.one('SELECT * FROM career_reviews WHERE application_id=?', (id,))
    if row:
        row['posting'] = json.loads(row['posting'])
        row['plan'] = json.loads(row['plan']) if row['plan'] else None
    return row


def digest(app, posting):
    semantic = {k:v for k,v in posting.items() if k != 'checked_at'}
    identity = {k:app[k] for k in ['company','role','job_url','recipient','location','salary']}
    return hashlib.sha256(json.dumps([identity, semantic], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def eligibility(app, review=None):
    review = review if review is not None else review_row(app['id'])
    reasons = []
    contacted = company_key(app['company']) in contacted_companies()
    if contacted: reasons.append('Công ty đã được liên hệ; giữ trong lịch sử, không coi là công ty mới.')
    if app['stage'] in {'excluded','blocked','withdrawn','rejected','offer'}:
        reasons.append('Trạng thái hồ sơ hiện tại không cho chuẩn bị đơn mới.')
    if not review:
        reasons.append('Chưa có JD được xác minh và đánh giá.')
    else:
        posting = review['posting']
        role_text = normalize(app['role'])
        work_text = normalize(posting['responsibilities'])
        if re.search(r'networking|telecom|network engineer|lap trinh plc|plc programmer', role_text) or re.search(r'router|switch firmware|telecom|networking stack|plc programming', work_text):
            reasons.append('JD chứa công việc networking/telecom/PLC ngoài định hướng; cần loại khỏi đề xuất mới.')
        if posting['focus'] in {'outside_target','unclear'}: reasons.append('Công việc chưa được xác định thuộc kỹ sư Robotics/AI.')
        if posting['hiring_status'] != 'open': reasons.append('Chưa xác minh tin còn tuyển.')
        now = datetime.now(timezone.utc)
        if datetime.fromisoformat(posting['checked_at']) < now - timedelta(days=7): reasons.append('Nguồn đã quá 7 ngày kiểm tra; cần xác minh lại.')
        if posting.get('deadline') and date.fromisoformat(posting['deadline']) < now.astimezone(VN).date(): reasons.append('Tin đã qua hạn ứng tuyển.')
        if posting['location_priority'] == 'outside': reasons.append('Địa điểm ngoài khu vực mục tiêu.')
    can_review = not reasons
    approved = bool(review and review['status'] == 'approved' and review['approval_hash'] == digest(app, review['posting']))
    if not approved: reasons.append('Chưa có bạn duyệt đúng phiên bản JD này.')
    return {'company_contacted':contacted, 'can_approve':can_review, 'can_prepare':not reasons, 'reasons':reasons, 'external_send_available':False}


def enrich(app):
    app['review'] = review_row(app['id'])
    app['eligibility'] = eligibility(app, app['review'])
    return app


@router.put('/{id}/posting')
def save_posting(id:str, body:PostingInput):
    with db.transaction():
        app = application(id)
        old = review_row(id)
        posting = body.model_dump(mode='json')
        changed = not old or digest(app, posting) != digest(app, old['posting'])
        revision = (old['revision'] if old else 0) + int(changed)
        status = 'pending' if changed else old['status']
        approved = '' if changed else old['approval_hash']
        db.execute('INSERT OR REPLACE INTO career_reviews VALUES(?,?,?,?,?,?,?,?,?)', (id, revision, json.dumps(posting,ensure_ascii=False), status, approved, None if changed else old['reviewed_at'], '' if changed else old['review_note'], None if changed or not old['plan'] else json.dumps(old['plan'],ensure_ascii=False), db.now()))
        db.execute('UPDATE career_applications SET updated_at=? WHERE id=?', (db.now(), id))
        audit(id, 'Cập nhật JD phiên bản '+str(revision), 'Cần người dùng duyệt lại.' if changed else 'Xác minh lại nguồn; nội dung JD không đổi.', source='research')
    return enrich(application(id))


def audit(id, title, text, source='user'):
    now = db.now()
    db.execute('INSERT INTO career_events VALUES(?,?,?,?,?,?,?,?)', (db.uid(), id, 'review-'+db.uid(), 'note', source, now, json.dumps({'title':title,'body_text':text},ensure_ascii=False), now))


@router.post('/{id}/review')
def review_job(id:str, body:ReviewInput):
    with db.transaction():
        app = application(id); row = review_row(id)
        if not row or row['revision'] != body.expected_revision:
            raise HTTPException(409,'JD đã đổi hoặc chưa có. Tải lại để duyệt đúng phiên bản.')
        gate = eligibility(app, row)
        if body.decision == 'approved' and not gate['can_approve']:
            raise HTTPException(409, ' '.join(gate['reasons']))
        db.execute('UPDATE career_reviews SET status=?,approval_hash=?,reviewed_at=?,review_note=?,plan=NULL,updated_at=? WHERE application_id=?', (body.decision, digest(app,row['posting']) if body.decision=='approved' else '', db.now(), body.note, db.now(), id))
        audit(id, 'Người dùng duyệt JD: '+body.decision, body.note or 'Duyệt trong tab Ứng tuyển. Chưa gửi email hoặc đặt lịch.')
    return enrich(application(id))


@router.get('/{id}/outreach-eligibility')
def outreach_eligibility(id:str): return eligibility(application(id))


@router.post('/{id}/outreach-plan')
def prepare_plan(id:str, body:PlanInput):
    with db.transaction():
        app = application(id); row = review_row(id); gate = eligibility(app, row)
        if not gate['can_prepare']:
            raise HTTPException(409,' '.join(gate['reasons']))
        if row['revision'] != body.expected_revision: raise HTTPException(409,'Phiên bản JD đã đổi; cần duyệt lại.')
        if not app['recipient'] or not row['posting']['recipient_source']:
            raise HTTPException(409,'Chưa có email tuyển dụng kèm nguồn xác minh; chưa thể chuẩn bị email.')
        plan = body.model_dump(mode='json') | {'recipient':app['recipient'],'status':'prepared_local','prepared_at':db.now(),'notice':'Bản chuẩn bị local; chưa tạo Gmail draft, chưa gửi và chưa có lịch gửi trong Gmail.'}
        db.execute('UPDATE career_reviews SET plan=?,updated_at=? WHERE application_id=?', (json.dumps(plan,ensure_ascii=False),db.now(),id))
        audit(id,'Chuẩn bị email local sau duyệt','Chưa gửi hoặc lên lịch trong Gmail.')
    return plan
