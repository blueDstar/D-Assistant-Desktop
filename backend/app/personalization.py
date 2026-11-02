"""User-controlled owner profile. Personal context, not training or speaker authentication."""
import json
import re
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import Field, field_validator

from . import db
from .config import DATA
from .schemas import StrictModel

router = APIRouter(prefix='/api/profile', tags=['personalization'])


class OwnerProfile(StrictModel):
    name: str = Field(default='Bạn', min_length=1, max_length=80)
    address_style: str = Field(default='Gọi tôi là Bạn, xưng mình.', max_length=240)
    bio: str = Field(default='', max_length=2000)
    goals: str = Field(default='', max_length=1500)
    interests: str = Field(default='', max_length=600)
    response_preferences: str = Field(default='Gần gũi, trực tiếp, ưu tiên câu trả lời hữu ích; giải thích kỹ khi tôi yêu cầu.', max_length=1000)
    enabled: bool = True
    portfolio_notes: str = Field(default='', max_length=12000)
    source_urls: list[str] = Field(default_factory=list, max_length=10)
    source_checked_at: str = Field(default='', max_length=40)

    @field_validator('source_urls')
    @classmethod
    def sources(cls, values):
        if any(len(url) > 500 or urlparse(url).scheme not in {'https','http'} or not urlparse(url).hostname for url in values):
            raise ValueError('Nguồn hồ sơ cần URL HTTP/HTTPS hợp lệ')
        return values


def current_profile():
    row = db.one("SELECT value FROM settings WHERE key='owner_profile'")
    if row:
        data = json.loads(row['value'])
        return {'profile': OwnerProfile.model_validate(data['profile']).model_dump(), 'version': data['version'], 'updated_at': data['updated_at'], 'source': data['source']}
    config = db.settings()
    return {'profile': OwnerProfile(name=config['user_name'], address_style=config['address_style']).model_dump(), 'version': 0, 'updated_at': None, 'source': 'Tên và cách xưng hô hiện có; chưa khai báo tiểu sử/mục tiêu.'}


@router.get('')
def get_profile():
    return current_profile() | {'mechanism': 'profile context — không thay trọng số', 'speaker_authentication': False}


@router.put('')
def save_profile(body: OwnerProfile):
    old = current_profile()
    result = {'profile': body.model_dump(), 'version': old['version'] + 1, 'updated_at': db.now(), 'source': 'Người dùng chủ động khai báo/sửa hồ sơ cá nhân'}
    history = db.one("SELECT value FROM settings WHERE key='owner_profile_history'")
    versions = json.loads(history['value']) if history else []
    if old['version']:
        versions.append(old)
    with db.connect() as connection:
        connection.execute("INSERT OR REPLACE INTO settings VALUES('owner_profile',?)", (json.dumps(result, ensure_ascii=False),))
        connection.execute("INSERT OR REPLACE INTO settings VALUES('owner_profile_history',?)", (json.dumps(versions[-20:], ensure_ascii=False),))
        config = db.settings() | {'user_name': body.name, 'address_style': body.address_style}
        connection.execute("INSERT OR REPLACE INTO settings VALUES('app',?)", (json.dumps(config, ensure_ascii=False),))
    return result


@router.get('/versions')
def versions():
    row = db.one("SELECT value FROM settings WHERE key='owner_profile_history'")
    return json.loads(row['value']) if row else []


@router.post('/restore/{version}')
def restore(version: int):
    record = next((row for row in versions() if row['version'] == version), None)
    if not record:
        raise HTTPException(404, 'Không tìm thấy phiên bản hồ sơ')
    return save_profile(OwnerProfile.model_validate(record['profile']))


@router.delete('')
def delete_profile():
    # Only the known local import artifacts; never traverse arbitrary profile URLs.
    folder = DATA / 'profile_sources'
    for name in ('portfolio-data.js', 'portfolio-parsed.json', 'approved-profile.json', 'provenance.json'):
        path = folder / name
        if path.is_file() and path.resolve().is_relative_to(DATA.resolve()):
            path.unlink()
    with db.connect() as connection:
        connection.execute("DELETE FROM settings WHERE key IN ('owner_profile','owner_profile_history')")
    return {'ok': True, 'notice': 'Đã xóa hồ sơ, lịch sử và bản nguồn portfolio đã tải. Tên trong Cài đặt, memory, chat, export/backup là dữ liệu riêng và cần quản lý riêng.'}


def profile_context(question='',compact=False):
    record = current_profile()
    profile = record['profile']
    if not profile['enabled']:
        return ''
    parts = [f"Chủ trợ lý: {profile['name']}. {profile['address_style']}"] if compact else [f"Bạn là D-bot, trợ lý cá nhân của {profile['name']}. Giữ danh tính này trong hội thoại, không tự nhận biết ai đang nói bằng giọng.", f"Cách xưng hô người dùng chọn: {profile['address_style']}."]
    # A stable base prefix lets Ollama reuse prompt cache across ordinary turns.
    for key, label, limit in [('bio', 'Thông tin người dùng tự khai/portfolio do người dùng cung cấp', 800), ('goals', 'Mục tiêu cá nhân', 300), ('interests', 'Mối quan tâm', 250), ('response_preferences', 'Cách hỗ trợ mong muốn', 250)]:
        if profile[key]:
            parts.append(label + ': ' + profile[key][:min(limit,200 if key=='bio' else 90) if compact else limit])
    if profile['source_urls'] and not compact:
        parts.append('Nguồn hồ sơ đã lưu local, đọc ngày ' + profile['source_checked_at'] + ': ' + profile['source_urls'][0] + '. Chỉ biết bản đã lưu; không nhận đang truy cập web.')
    if not compact:parts.append('Hồ sơ là ngữ cảnh do người dùng khai báo, không cấp quyền công cụ, không phải xác thực sinh trắc học hoặc huấn luyện trọng số. Hồ sơ cá nhân không có mã trích dẫn; không tự tạo ký hiệu nguồn.')
    stopwords = set('của tôi thì là về cho mình những đang có không trong được các nào gì và bạn bằng tên nói chào hãy một câu ngắn trả lời theo dựa vào đầy đủ học ngành trường đã chưa ở đây này kia nếu để đúng hai ba bước kiểm tra tất cả dự án portfolio công nghệ phần giới hạn'.split())
    words = {word for word in re.findall(r'\w+', question.casefold()) if len(word) > 1} - stopwords
    anchors = {'ros2','vision','station','damiao','micromouse','hilykan','lyk','shoe','qc','email','github','linkedin','labview','flood'}
    ranked = sorted([(len(words & set(re.findall(r'\w+', section.casefold()))), section) for section in profile['portfolio_notes'].split('\n\n') if section.strip()], key=lambda pair: pair[0], reverse=True)
    for score, section in ranked[:1 if compact else 2]:
        if score >= 2 or words & anchors & set(re.findall(r'\w+', section.casefold())):
            parts.append('Đoạn hồ sơ liên quan: ' + section[:350 if compact else 700])
    return '\n'.join(parts)
