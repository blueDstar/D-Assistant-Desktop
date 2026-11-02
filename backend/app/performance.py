"""Explicit fast/quality routing; never claim that display buffering speeds inference."""
import re
from . import db


def runtime_config(config, body):
    selected = dict(config)
    preference = body.performance or config.get('performance', 'auto')
    fast = preference == 'fast' or (preference == 'auto' and body.mode == 'chat')
    if preference=='auto' and (body.tutor or body.continue_response):fast=False
    # The small chat model is not the language tutor. Explicit writing/language
    # requests and Japanese/English input use the stronger model automatically.
    routing_text='\n'.join([message['content'][:2000] for message in body.history[-6:]]+[body.text])
    language_task = re.search(r'correct|grammar|translate|dịch|ngữ pháp|tiếng anh|tiếng nhật|ielts|jlpt|toeic|toefl|sửa.{0,24}câu|[\u3040-\u30ff\u4e00-\u9fff]', routing_text, re.I)
    english_input = any(text.isascii() and len(re.findall(r'[A-Za-z]{2,}',text))>=3 for text in [body.text]+[m['content'][:2000] for m in body.history[-6:] if m['role']=='user'])
    technical_task = re.search(r'\b(pid|pwm|ros2?|esp32|stm32|c\+\+|python|plc|can bus|mqtt|robotics)\b|c\+\+|code|chương trình|trí tuệ nhân tạo|mạch điện|vi điều khiển|điều khiển|lập trình|thuật toán|robot|kỹ thuật|kĩ thuật|nghiên cứu|ứng tuyển|phỏng vấn|portfolio|của tôi|về tôi|tôi học|ngành tôi|tôi làm|công việc|tôi đang|tôi là ai|tên tôi|tôi tên|mục tiêu|sở thích|hồ sơ',routing_text,re.I)
    if preference=='auto' and (language_task or english_input or technical_task or re.search(r'\bAI\b',body.text)):fast=False
    # Source-heavy research stays on the quality model in automatic mode.
    if preference == 'auto' and body.use_knowledge and (body.source_ids or db.one("SELECT id FROM sources WHERE project_id=? AND status='ready' LIMIT 1", (body.project_id,))):
        fast = False
    if fast:
        selected['model'] = config.get('fast_model', config['model'])
        selected['context'] = config['context'] if selected['model']==config['model'] else min(config['context'], 3072)
    # Reserve context for the prompt and recent turns. Fast routing must not
    # silently impose a 192/384-token quota on lessons or detailed questions.
    selected['max_output'] = min(config['max_output'], selected['context'] // 2)
    explicit_short = body.response_length=='short' or body.response_length=='standard' and bool(re.search(r'ngắn gọn|trả lời ngắn|briefly|keep it short',body.text,re.I))
    if explicit_short:
        selected['response_length']='short'
        selected['max_output'] = min(selected['max_output'], 384)
    elif body.response_length == 'long':
        selected['max_output'] = min(max(selected['max_output'], 1536), selected['context'] // 2)
    selected.setdefault('response_length', body.response_length)
    personal_request=re.search(r'ứng tuyển|phỏng vấn|portfolio|hồ sơ|của tôi|về tôi|tôi học|ngành tôi|tôi làm|công việc|tôi đang|tôi là ai|tên tôi|tôi tên|mục tiêu|sở thích',body.text,re.I)
    selected['brief_prompt']=bool(selected['response_length']=='short' and body.mode=='chat' and not body.tutor and not personal_request and not language_task)
    selected['response_profile'] = 'fast' if fast else 'quality'
    selected['voice_conversation'] = body.voice_conversation
    if body.tutor:
        selected['native_tools']=False
    elif fast:
        # Do not attach a calculator schema to every ordinary chat turn.
        # Numeric follow-ups still keep it; this never grants new tools.
        arithmetic = re.search(r'\d|tính|calculate|compute|sum|nhân|chia|cộng|trừ|bao nhiêu|đổi đơn vị', body.text, re.I)
        followup = re.search(r'tiếp|nữa|lại|kết quả|that|again|continue', body.text, re.I)
        selected['native_tools'] = bool(selected.get('native_tools') and (arithmetic or followup))
    return selected
