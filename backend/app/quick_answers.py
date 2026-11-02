"""Exact local replies to trivial requests, labelled separately from model output."""
import re
from datetime import datetime, timedelta, timezone
from . import db


def quick_answer(text, has_history=False):
    value = re.sub(r'[.!?。！？]+$', '', text.strip().casefold()).strip()
    name = db.settings()['user_name']
    standalone = {'mấy giờ rồi','bây giờ mấy giờ','bây giờ là mấy giờ','giờ hiện tại','hôm nay ngày mấy','hôm nay là ngày mấy','hôm nay ngày bao nhiêu','hôm nay là ngày bao nhiêu','bạn là ai','bạn tên gì','tên bạn là gì','bạn là trợ lý của ai'}
    if has_history and value not in standalone:
        return None
    if value in {'xin chào','chào','chào bạn','chào dbot','chào d-bot','alo'}:
        return f'Mình đây, {name}. Bạn cần mình giúp gì?'
    if value in {'hello','hi','hey'}:
        return f'Hi {name}, how can I help?'
    if value in {'こんにちは','おはよう','こんばんは'}:
        return 'こんにちは。何をお手伝いしましょうか。'
    if value in {'cảm ơn','cảm ơn bạn','cảm ơn nhé','thanks','thank you'}:
        return 'Rất vui được giúp bạn.' if value not in {'thanks','thank you'} else 'You’re welcome.'
    if value in {'bạn là ai','bạn tên gì','tên bạn là gì','bạn là trợ lý của ai'}:
        return f'Mình là D-bot, trợ lý cá nhân của {name}, đang chạy local trên máy này.'
    now = datetime.now(timezone(timedelta(hours=7)))
    if value in {'mấy giờ rồi','bây giờ mấy giờ','bây giờ là mấy giờ','giờ hiện tại'}:
        return f'Bây giờ là {now:%H:%M}, giờ Việt Nam.'
    if value in {'hôm nay ngày mấy','hôm nay là ngày mấy','hôm nay ngày bao nhiêu','hôm nay là ngày bao nhiêu'}:
        return f'Hôm nay là ngày {now:%d/%m/%Y}, theo giờ Việt Nam.'
    return None
