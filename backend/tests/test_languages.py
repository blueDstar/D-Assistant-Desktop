import asyncio,json,uuid
import pytest
from fastapi.testclient import TestClient
from app import db,ollama
from app.main import app
from app.schemas import ChatInput
from app.performance import runtime_config
from app.language_learning import BANK

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',tmp_path/'app.sqlite3')
    async def diagnostics():return {'ready':True,'models':[]}
    async def stream(messages,config,cancel):
        yield {'type':'token','text':'Test answer for the language learner.'}
        yield {'type':'metrics','metrics':{'eval_count':12,'output_truncated':False}}
    monkeypatch.setattr(ollama,'diagnostics',diagnostics);monkeypatch.setattr(ollama,'stream',stream)
    with TestClient(app) as c:
        c.headers['X-D-Bot-Token']=c.get('/api/session').json()['token'];yield c

def chat(client,**kw):
    response=client.post('/api/chat',json={'text':'Help me learn English grammar.','request_id':str(uuid.uuid4()),'use_knowledge':False,**kw})
    assert response.status_code==200,response.text
    return [json.loads(line) for line in response.text.splitlines()]

def test_quiz_grades_real_answer_without_leaking_key_and_persists(client):
    public=client.get('/api/languages/questions?language=ja&level=N5').json()['questions']
    assert public and all('answer' not in q and 'explanation' not in q for q in public)
    q=next(q for q in BANK if q['id']==public[0]['id'])
    result=client.post('/api/languages/answer',json={'question_id':q['id'],'choice':q['answer']}).json()
    assert result['correct'] and result['explanation']
    overview=client.get('/api/languages/overview?language=ja').json()
    assert overview['total']==overview['correct']==1
    db.migrate();assert client.get('/api/languages/overview?language=ja').json()['total']==1
    other=client.post('/api/projects',json={'name':'Other learner'}).json()['id']
    assert client.get('/api/languages/overview?language=ja&project_id='+other).json()['total']==0
    client.delete('/api/languages/progress?language=ja')
    assert not client.get('/api/languages/overview?language=ja').json()['total']

def test_profile_validation_and_learning_scope(client):
    good={'language':'ja','level':'N3','exam':'JLPT','target':'N3','daily_minutes':30}
    assert client.put('/api/languages/profile',json=good).status_code==200
    assert client.get('/api/languages/overview?language=ja').json()['profile']['level']=='N3'
    assert client.put('/api/languages/profile',json={**good,'level':'B2'}).status_code==422
    assert client.post('/api/languages/answer',json={'question_id':BANK[0]['id'],'choice':4}).status_code==422
    assert client.get('/api/languages/overview?project_id=missing').status_code==404

def test_long_voice_has_no_old_192_token_quota(client):
    config=db.settings()|{'max_output':2048,'fast_model':'new:4b','model':'new:4b'}
    result=runtime_config(config,ChatInput(text='Explain fully',request_id='long-voice',voice_conversation=True,response_length='long'))
    assert result['max_output']==2048 and result['context']==4096

def test_tutor_preserves_instructions_and_language_in_real_prompt(client,monkeypatch):
    seen=[]
    async def stream(messages,config,cancel):
        seen.extend(messages);yield {'type':'token','text':'毎日、学校に行きます。'}
    monkeypatch.setattr(ollama,'stream',stream)
    events=chat(client,text='Trợ từ に và で khác nhau thế nào?',mode='tutor',tutor={'language':'ja','level':'N5','exam':'JLPT','activity':'lesson'})
    assert events[-1]['status']=='completed'
    assert 'trình độ N5' in seen[0]['content'] and 'JLPT' in seen[0]['content']
    assert 'Ngôn ngữ đầu ra bắt buộc: tiếng Việt' not in seen[0]['content']

def test_conversation_candidates_stay_pending_and_private_is_excluded(client):
    config=db.settings()|{'learn_from_conversations':True};db.execute("INSERT OR REPLACE INTO settings VALUES('app',?)",(json.dumps(config),))
    chat(client);examples=client.get('/api/examples').json()
    assert len(examples)==1 and examples[0]['status']=='pending' and not examples[0]['reviewed']
    chat(client,private=True)
    assert len(client.get('/api/examples').json())==1
    assert client.get('/api/datasets/preview').json()['splits']=={'train':[],'validation':[],'test':[]}
    client.post('/api/messages/'+examples[0]['message_id']+'/exclude-learning')
    assert client.get('/api/examples').json()[0]['status']=='rejected'

def test_continue_retains_question_and_answer_tail_when_answer_is_long(client,monkeypatch):
    events=chat(client,text='Explain conditionals with many examples.')
    id=events[0]['conversation_id'];message=events[0]['message_id']
    db.execute('UPDATE messages SET content=? WHERE id=?',('Old content '*700+' UNIQUE TAIL',message))
    seen=[]
    async def stream(messages,config,cancel):seen.extend(messages);yield {'type':'token','text':'Continuation.'}
    monkeypatch.setattr(ollama,'stream',stream)
    events=chat(client,conversation_id=id,text='Continue',continue_response=True)
    assert events[-1]['status']=='completed'
    assert 'UNIQUE TAIL' in seen[-1]['content'] and 'Explain conditionals' in seen[-1]['content']

def test_repeated_continuation_keeps_root_without_polluting_history_or_learning(client,monkeypatch):
    config=db.settings()|{'learn_from_conversations':True};db.execute("INSERT OR REPLACE INTO settings VALUES('app',?)",(json.dumps(config),))
    events=chat(client,text='Explain robot control in three sections.')
    conversation=events[0]['conversation_id'];root=events[0]['user_message_id']
    seen=[]
    async def stream(messages,config,cancel):
        seen.append(messages[-1]['content']);yield {'type':'token','text':'Next section.'}
    monkeypatch.setattr(ollama,'stream',stream)
    for _ in range(14):
        events=chat(client,conversation_id=conversation,text='Continue',continue_response=True,continuation_question='IGNORE CLIENT OVERRIDE')
        assert events[-1]['status']=='completed'
        assert 'Explain robot control in three sections.' in seen[-1]
        assert 'IGNORE CLIENT OVERRIDE' not in seen[-1]
        assert seen[-1].count('Yêu cầu gốc:')==1
        metadata=json.loads(db.one('SELECT metadata FROM messages WHERE id=?',(events[0]['message_id'],))['metadata'])
        assert metadata['continuation']['root_message_id']==root
    rows=db.rows("SELECT content FROM messages WHERE conversation_id=? AND role='user' ORDER BY created_at",(conversation,))
    assert all(row['content']=='Continue' for row in rows[1:])
    assert len(client.get('/api/examples').json())==1
    other=client.post('/api/projects',json={'name':'Other project'}).json()['id']
    assert client.post('/api/chat',json={'request_id':str(uuid.uuid4()),'project_id':other,'conversation_id':conversation,'text':'Continue','continue_response':True}).status_code==404

def test_private_continuation_carries_original_without_persisting(client,monkeypatch):
    seen=[]
    async def stream(messages,config,cancel):seen.append(messages[-1]['content']);yield {'type':'token','text':'Next.'}
    monkeypatch.setattr(ollama,'stream',stream)
    for _ in range(3):
        events=chat(client,private=True,text='Continue',continue_response=True,continuation_question='Original private question',history=[{'role':'user','content':'Continue'},{'role':'assistant','content':'LATEST TAIL'}])
        assert events[-1]['status']=='completed'
        assert 'Original private question' in seen[-1] and 'LATEST TAIL' in seen[-1]
    assert not db.rows('SELECT id FROM conversations')
    assert not db.rows('SELECT id FROM approved_examples')
    assert client.post('/api/chat',json={'request_id':str(uuid.uuid4()),'text':'Continue','private':True,'continue_response':True}).status_code==422

def test_long_japanese_continuation_fits_small_context_and_reports_clipping(client,monkeypatch):
    config=db.settings()|{'context':2048,'max_output':1024};db.execute("INSERT OR REPLACE INTO settings VALUES('app',?)",(json.dumps(config),))
    seen=[]
    async def stream(messages,config,cancel):seen.extend(messages);yield {'type':'token','text':'続きです。'}
    monkeypatch.setattr(ollama,'stream',stream)
    events=chat(client,private=True,text='Continue',continue_response=True,continuation_question='質問：'+'日本語を勉強します。'*800,history=[{'role':'assistant','content':'説明。'*3000+' 最後です。'}],mode='tutor',tutor={'language':'ja','level':'N5','exam':'general','activity':'lesson'})
    assert events[-1]['status']=='completed'
    assert 'đoạn giữa đã lược' in seen[-1]['content'] and '最後です。' in seen[-1]['content']

def test_oversized_lesson_has_actionable_error_without_partial_records(client):
    reply=client.post('/api/chat',json={'request_id':str(uuid.uuid4()),'text':'日本語'*5000,'mode':'tutor','tutor':{'language':'ja','level':'N5'}})
    assert reply.status_code==422 and 'ngữ cảnh' in reply.json()['detail']
    assert not db.rows('SELECT id FROM messages')

def test_bank_and_readiness_are_honest(client):
    assert len({q['id'] for q in BANK})==len(BANK)
    assert all(len(q['choices'])==4 and 0<=q['answer']<4 and q['explanation'] for q in BANK)
    result=client.get('/api/training/readiness').json()
    assert not result['weight_training_performed'] and result['blockers']

def test_long_recent_turn_is_clipped_instead_of_forgetting_question(client):
    from app.prompts import build_context,token_cost
    config=db.settings()|{'max_output':1536,'model':'qwen3:4b-instruct'}
    messages=build_context(config,db.one("SELECT * FROM projects WHERE id='general'"),[{'role':'user','content':'Teach present perfect.'},{'role':'assistant','content':'First example. '+'A detailed explanation. '*1000+' Last example.'}],'Explain the last example.')
    assert any(m['content']=='Teach present perfect.' for m in messages)
    assert config['history_trimmed']
    assert sum(token_cost(m['content'],config['model']) for m in messages)+config['max_output']+384<=config['context']
