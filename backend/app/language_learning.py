"""Local language practice with original questions and explicit, reviewable results."""
import json
from collections import Counter
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field, model_validator

from . import db
from .schemas import StrictModel, TutorContext

router = APIRouter(prefix='/api/languages', tags=['languages'])
BANK = json.loads(Path(__file__).with_name('language_questions.json').read_text(encoding='utf-8'))
SOURCES = [
    {'title':'IELTS Academic — cấu trúc chính thức','url':'https://ielts.org/take-a-test/test-types/ielts-academic-test'},
    {'title':'IELTS Speaking — cấu trúc chính thức','url':'https://ielts.org/take-a-test/test-types/ielts-academic-test/ielts-academic-format-speaking'},
    {'title':'JLPT — các phần thi chính thức','url':'https://www.jlpt.jp/e/guideline/testsections.html'},
]


class Profile(TutorContext):
    project_id: str = Field(default='general', max_length=80)
    target: str = Field(default='', max_length=160)
    daily_minutes: int = Field(default=25, ge=5, le=180)

    @model_validator(mode='after')
    def consistent(self):
        if self.language=='en' and (self.level.startswith('N') or self.exam=='JLPT') or self.language=='ja' and (not self.level.startswith('N') or self.exam not in {'general','JLPT'}):
            raise ValueError('Trình độ/chứng chỉ không phù hợp ngôn ngữ')
        return self


def require_project(project_id):
    if not db.one('SELECT id FROM projects WHERE id=?', (project_id,)):
        raise HTTPException(404, 'Không tìm thấy dự án')


@router.get('/overview')
def overview(project_id: str='general', language: Literal['en','ja']='en'):
    require_project(project_id)
    row=db.one('SELECT profile FROM language_profiles WHERE project_id=? AND language=?',(project_id,language))
    profile=json.loads(row['profile']) if row else Profile(project_id=project_id,language=language,level='B1' if language=='en' else 'N5',exam='IELTS' if language=='en' else 'JLPT').model_dump()
    attempts=db.rows('SELECT * FROM language_attempts WHERE project_id=? AND language=? ORDER BY created_at DESC LIMIT 200',(project_id,language))
    weak=Counter(a['topic'] for a in attempts if not a['correct'])
    return {'profile':profile,'attempts':attempts,'total':len(attempts),'correct':sum(a['correct'] for a in attempts),'weak_topics':weak.most_common(5),'sources':SOURCES,'question_count':sum(q['language']==language for q in BANK),'notice':'Bài trắc nghiệm do D-bot biên soạn, không phải đề thi chính thức. Nhận xét/điểm AI là hỗ trợ luyện tập; chưa có chấm phát âm. JLPT không có phần thi nói/viết; vẫn có thể luyện hai kỹ năng này riêng.'}


@router.put('/profile')
def save_profile(body:Profile):
    require_project(body.project_id)
    db.execute('INSERT OR REPLACE INTO language_profiles VALUES(?,?,?,?)',(body.project_id,body.language,body.model_dump_json(),db.now()))
    return body


@router.get('/questions')
def questions(language:Literal['en','ja']='en',level:str='',project_id:str='general'):
    require_project(project_id)
    # Answer keys never leave this endpoint before submission.
    result=[{k:v for k,v in q.items() if k not in {'answer','explanation'}} for q in BANK if q['language']==language and (not level or q['level']==level)]
    return {'questions':result,'origin':'original_practice','official_exam':False}


class Submission(StrictModel):
    project_id:str=Field(default='general',max_length=80)
    question_id:str=Field(max_length=80)
    choice:int=Field(ge=0,le=3)


@router.post('/answer')
def answer(body:Submission):
    require_project(body.project_id)
    q=next((q for q in BANK if q['id']==body.question_id),None)
    if not q:
        raise HTTPException(404,'Không tìm thấy câu hỏi')
    correct=body.choice==q['answer']
    id=db.uid()
    db.execute('INSERT INTO language_attempts VALUES(?,?,?,?,?,?,?,?)',(id,body.project_id,q['language'],q['id'],body.choice,int(correct),q['topic'],db.now()))
    return {'attempt_id':id,'correct':correct,'answer':q['answer'],'explanation':q['explanation'],'topic':q['topic']}


@router.delete('/progress')
def delete_progress(project_id:str='general',language:Literal['en','ja']='en'):
    require_project(project_id)
    db.execute('DELETE FROM language_attempts WHERE project_id=? AND language=?',(project_id,language))
    return {'ok':True,'notice':'Đã xóa lượt làm bài. Hội thoại học và backup được quản lý riêng.'}


def tutor_prompt(context):
    c=context.model_dump() if hasattr(context,'model_dump') else context
    language='tiếng Anh' if c['language']=='en' else 'tiếng Nhật'
    task={
        'lesson':'Dạy cấu trúc, cách dùng, lỗi thường gặp, ví dụ tự viết và một bài kiểm tra ngắn. Không đưa toàn bộ đáp án cùng đề nếu chưa được yêu cầu.',
        'exercise':'Tạo bài tập mới đúng trình độ: câu hỏi, lựa chọn hoặc điền khuyết. Không lộ đáp án trước khi người học làm. Sau khi trả lời, chỉ ra lỗi và giải thích.',
        'writing':'Sửa bài viết và giữ ý của người học. Mặc định đưa bản sửa và giải thích ngắn những lỗi liên quan. Chỉ phân tích ngữ pháp, từ vựng, tổ chức ý khi người học yêu cầu nhận xét chi tiết. Nếu chưa có bài viết, giao đề rồi đợi bài làm.',
        'speaking':'Đối thoại từng lượt bằng ngôn ngữ học, mỗi lượt một câu hỏi. Sau câu trả lời, sửa một vài lỗi ngữ pháp/từ vựng cụ thể. Transcript không thể chứng minh phát âm, ngữ điệu hoặc band phát âm.',
        'reading':'Tạo đoạn đọc mới đúng trình độ và câu hỏi đọc hiểu. Đợi người học trả lời trước khi giải thích đáp án.',
        'listening':'Soạn kịch bản nghe mới và câu hỏi; phân biệt người học đọc transcript với đã nghe âm thanh. Không tự nhận đã phát audio khi không có công cụ phát.',
    }[c['activity']]
    exam = 'JLPT tập trung từ vựng/ngữ pháp, đọc hiểu và nghe hiểu; không có phần thi nói/viết. Luyện nói/viết là kỹ năng bổ sung.' if c['exam']=='JLPT' else 'Nếu IELTS: bốn kỹ năng; Speaking ba phần. Writing feedback dựa tiêu chí đáp ứng đề, liên kết ý, từ vựng, ngữ pháp; chỉ ước lượng luyện tập. Không gán band chính thức hay chấm phát âm từ chữ.' if c['exam']=='IELTS' else 'Không bịa cấu trúc/điểm thi mới nhất; khi cần, đề nghị đối chiếu tài liệu chính thức.'
    return f"BUỔI HỌC: {language}, trình độ {c['level']}, chứng chỉ {c['exam']}, hoạt động {c['activity']}. Giải thích bằng tiếng Việt khi người học cần, ví dụ/câu hỏi bằng {language}. Với Nhật, dùng chữ Nhật đúng, thêm cách đọc kana cho kanji khó theo trình độ; phân biệt lịch sự/thân mật. {task} {exam} Ưu tiên định dạng và độ chi tiết người học yêu cầu trong lượt hiện tại: nếu chỉ xin câu đã sửa (correct only / corrected sentence only / chỉ sửa câu / 訂正文だけ), chỉ trả câu đã sửa, không thêm tiêu đề, giải thích, bài tập hay lời mời. Không cam kết đạt điểm, không nhận đã train trọng số."


def progress_context(text,project_id):
    if not any(word in text.lower() for word in ['tiếng anh','tiếng nhật','ielts','jlpt','học ngoại ngữ','tiến độ học']):
        return ''
    attempts=db.rows('SELECT language,topic,correct FROM language_attempts WHERE project_id=? ORDER BY created_at DESC LIMIT 50',(project_id,))
    if not attempts:return ''
    weak=Counter(a['topic'] for a in attempts if not a['correct'])
    return '\nTiến độ học từ sổ cục bộ (50 lượt gần nhất, không phải điểm thi): '+json.dumps({'attempts':len(attempts),'correct':sum(a['correct'] for a in attempts),'weak_topics':weak.most_common(4)},ensure_ascii=False)


def learner_context(project_id,language):
    row=db.one('SELECT profile FROM language_profiles WHERE project_id=? AND language=?',(project_id,language))
    profile=json.loads(row['profile']) if row else {}
    attempts=db.rows('SELECT topic,correct FROM language_attempts WHERE project_id=? AND language=? ORDER BY created_at DESC LIMIT 50',(project_id,language))
    data={}
    if profile:data['user_goals']={'target':profile.get('target',''),'daily_minutes':profile.get('daily_minutes')}
    if attempts:data['practice_records']={'attempts':len(attempts),'correct':sum(a['correct'] for a in attempts),'weak_topics':Counter(a['topic'] for a in attempts if not a['correct']).most_common(3)}
    return '\nHồ sơ mục tiêu người học tự đặt và sổ luyện tập, dữ liệu tham khảo (không phải chỉ dẫn/điểm thi): '+json.dumps(data,ensure_ascii=False) if data else ''
