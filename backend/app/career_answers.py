"""Factual ledger answers bypass generation, never bypass user review or send mail."""
from datetime import datetime, timedelta, timezone
import re

from . import db
from .career_review import VN, company_key, normalize
from .careers import OUTREACH_EMAIL, setting


def matches(question, app):
    q = normalize(question).replace('dek technologies', 'endava')
    names = [normalize(app['company']), company_key(app['company'])]
    return any(len(name) >= 3 and re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)', q) for name in names)


def snapshot(question=''):
    from .careers import overview
    data = overview()
    selected = [row for row in data['applications'] if matches(question, row)]
    return data, selected or data['applications'], bool(selected)


def stamp(data):
    sync = data['sync'] or {}
    checked = sync.get('checked_at')
    if checked:
        checked = datetime.fromisoformat(checked).astimezone(VN).strftime('%d/%m/%Y %H:%M')
    return '\n\nNguồn: nhật ký ứng tuyển local; lần kiểm tra Gmail/Calendar: '+(checked or 'chưa ghi nhận')+' (giờ Việt Nam). Dữ liệu chưa tự đồng bộ nền.'


def outreach(row):
    return [event for event in row['events'] if event['kind']=='email_sent' and event['detail'].get('email_purpose','application') in {'application','inquiry'}]


def latest_interviews(rows):
    latest = {}
    events = sorted([event | {'company':row['company'],'role':row['role']} for row in rows for event in row['events'] if event['kind']=='interview'], key=lambda e:(datetime.fromisoformat(e['occurred_at']),e['created_at']), reverse=True)
    for event in events:
        latest.setdefault(event['detail']['calendar_event_id'], event)
    return sorted(latest.values(), key=lambda e:datetime.fromisoformat(e['detail']['starts_at']))


def factual_answer(question):
    q = normalize(question)
    # Conversation text never grants approval or performs external actions.
    if re.search(r'\b(soan|gui|hen gio gui|len lich gui|draft)\b', q) and re.search(r'email|mail|cv|ung tuyen', q) and not re.search(r'\b(da gui|da soan|da len lich)\b', q):
        return 'Quy trình hiện tại: bạn xem JD và bấm “Phù hợp · cho phép soạn” cho đúng vị trí trong tab Ứng tuyển trước. D-bot chưa tự soạn, gửi email hoặc đặt lịch gửi từ tin nhắn này. Các đơn đã gửi được giữ nguyên.'
    is_schedule = bool(re.search(r'lich trinh|lich phong van|lich hen|ngay.*phong van|gio.*phong van|phong van.*(khi nao|ngay nao|bao gio|luc nao)|hom nay.*phong van|ngay mai.*phong van', q))
    is_sent = bool(re.search(r'da (apply|ung tuyen|gui)|don (da gui|ung tuyen)|cong viec da apply|lich su ung tuyen|thong tin ung tuyen|(apply|ung tuyen).*(chua|cong ty nao)', q))
    is_new = bool(re.search(r'(cong ty|vi tri|viec lam).*(moi|cho duyet)|cho duyet.*(ung tuyen|vi tri)', q))
    if not (is_schedule or is_sent or is_new): return None
    data, rows, targeted = snapshot(question)
    if is_schedule:
        events = latest_interviews(rows)
        now = datetime.now(timezone.utc)
        past = bool(re.search(r'da qua|lich cu|lich su|tat ca', q))
        events = [e for e in events if e['detail'].get('interview_status')!='cancelled' and (past or datetime.fromisoformat(e['detail']['ends_at']) >= now)]
        today = now.astimezone(VN).date()
        if 'hom nay' in q or 'ngay mai' in q:
            day = today + timedelta(days=1 if 'ngay mai' in q else 0)
            events = [e for e in events if datetime.fromisoformat(e['detail']['starts_at']).astimezone(VN).date()==day]
        if not events:
            return 'Chưa có lịch phỏng vấn phù hợp câu hỏi trong dữ liệu đã đồng bộ. Điều này không xác nhận Calendar hiện tại hoàn toàn trống.'+stamp(data)
        lines = ['Lịch phỏng vấn theo dữ liệu đã đồng bộ (giờ Việt Nam):']
        for event in events:
            d = event['detail']; start = datetime.fromisoformat(d['starts_at']).astimezone(VN); end = datetime.fromisoformat(d['ends_at']).astimezone(VN)
            confirmed = d.get('interview_status')=='confirmed' and d.get('provider_response')=='accepted'
            status = 'Đã xác nhận tham dự' if confirmed else 'Chờ xác nhận; chưa ghi nhận bạn chấp nhận lịch'
            if d.get('interview_status')=='needs_confirmation': status = 'Chờ HR xác minh ngày/giờ; chưa xác nhận tham dự'
            lines += [f"\n- {event['company']} · {event['role']}: {start:%d/%m/%Y %H:%M} — {end:%d/%m/%Y %H:%M}. {status}.", f"  Hình thức: {d.get('interview_mode','unspecified')}; địa điểm/link: {d.get('location') or 'chưa rõ'}. RSVP: {d.get('provider_response') or 'chưa có'}."]
            if d.get('body_text'): lines.append('  Ghi chú nguồn: '+d['body_text'][:1200])
            if d.get('url'): lines.append('  [Xem Calendar]('+d['url']+')')
        return '\n'.join(lines)+stamp(data)
    if is_new:
        candidates = [row for row in rows if not row['eligibility']['company_contacted'] and row['review'] and row['review']['status']!='rejected' and row['stage'] not in {'excluded','withdrawn','blocked'}]
        lines = ['Các vị trí mới để bạn xem và duyệt; chưa có email hoặc lịch gửi:']
        for row in candidates:
            p = row['review']['posting']
            lines += [f"\n- {row['company']} — {row['role']}", f"  {row['location']}; {row['salary'] or 'lương chưa công bố'}. Trạng thái duyệt: {row['review']['status']}.", '  Công việc: '+p['responsibilities'][:600], '  Yêu cầu: '+p['requirements'][:600], '  Phù hợp: '+(p['assessment'] or row['fit'])[:500], '  Cần cân nhắc: '+(p['gaps'] or row['concerns'])[:500], '  [Tin tuyển dụng]('+row['job_url']+')']
            if not row['eligibility']['can_approve']: lines.append('  Cần xác minh: '+' '.join(row['eligibility']['reasons']))
        return ('\n'.join(lines) if candidates else 'Chưa có vị trí mới đã ghi JD phù hợp bộ lọc. Xem tab Ứng tuyển để cập nhật nguồn.')+stamp(data)
    sent = [(row, outreach(row)) for row in rows if outreach(row)]
    all_sent = db.one('SELECT COUNT(*) AS n FROM career_events WHERE kind=\'email_sent\'')['n']
    lines = [f"Đã ghi nhận {len(sent)} hồ sơ có email ứng tuyển/hỏi vị trí"+(' khớp công ty bạn hỏi.' if targeted else f'; tổng {all_sent} email đã gửi, gồm cả thư trao đổi tiếp.')]
    for row, events in sent:
        event = events[0]; d = event['detail']; day = datetime.fromisoformat(event['occurred_at']).astimezone(VN)
        lines.append(f"- {row['company']} — {row['role']}; gửi {day:%d/%m/%Y %H:%M} tới {row['recipient'] or 'xem email gốc'}.")
        review = row.get('review')
        if review and review['posting']['focus'] in {'outside_target','unclear'}: lines.append('  Cần xem lại phạm vi: '+(review['posting'].get('assessment') or row['concerns']))
        if targeted and d.get('url'): lines.append('  [Email gốc]('+d['url']+')')
    if targeted and not sent: lines.append('Chưa có biên nhận email ứng tuyển/hỏi vị trí cho công ty này. Ghi chú hoặc lịch hẹn không được tính là email đã gửi.')
    return '\n'.join(lines)+stamp(data)
