import json,uuid
from app import db,ollama
from test_functional import client,chat


def test_rename_move_history_and_memory_remain_in_correct_scope(client):
    events=chat(client,'A robot project question')
    conversation=events[0]['conversation_id']
    project=client.post('/api/projects',json={'name':'Robot research'}).json()['id']
    memory=client.post('/api/memories',json={'project_id':'general','content':'Motor A is a demo fact','kind':'project_fact','approved':True,'source_message_id':events[0]['user_message_id']}).json()
    result=client.put('/api/conversations/'+conversation,json={'title':'Robot notes','project_id':project})
    assert result.status_code==200 and result.json()['project_id']==project
    assert not client.get('/api/conversations').json()
    assert client.get('/api/conversations',params={'project_id':project}).json()[0]['title']=='Robot notes'
    assert client.get('/api/conversations?all_projects=true').json()[0]['id']==conversation
    assert len(client.get('/api/conversations/'+conversation+'/messages').json())==2
    assert not client.get('/api/memories',params={'project_id':project}).json()
    assert db.one('SELECT project_id FROM memories WHERE id=?',(memory['id'],))['project_id']=='general'
    assert next(p for p in client.get('/api/projects').json() if p['id']==project)['conversation_count']==1
    assert client.put('/api/conversations/'+conversation,json={'project_id':'missing'}).status_code==404
    assert client.put('/api/conversations/'+conversation,json={'title':'  '}).status_code==422
    assert client.put('/api/conversations/missing',json={'title':'No'}).status_code==404
    db.execute("UPDATE messages SET status='running' WHERE id=?",(events[0]['message_id'],))
    assert client.put('/api/conversations/'+conversation,json={'title':'While running'}).status_code==409


def test_quick_replies_are_labelled_persisted_and_do_not_invoke_ollama(client,monkeypatch):
    async def forbidden(*args):raise AssertionError('Quick greeting must not call a model')
    monkeypatch.setattr(ollama,'diagnostics',forbidden)
    events=chat(client,'Xin chào')
    done=next(e for e in events if e['type']=='done')
    assert done['metrics']['answer_source']=='local_quick_reply'
    message=db.one('SELECT * FROM messages WHERE id=?',(events[0]['message_id'],))
    assert json.loads(message['metadata'])['answer_source']=='local_quick_reply'
    assert message['status']=='completed' and 'D-bot' not in message['content']
    count=len(db.rows('SELECT id FROM messages'))
    chat(client,'Mấy giờ rồi?',private=True)
    assert len(db.rows('SELECT id FROM messages'))==count


def test_quick_replies_never_consume_a_mixed_action_or_learning_task(client):
    from app.quick_answers import quick_answer
    assert quick_answer('Xin chào, mở PowerPoint và gửi email') is None
    assert quick_answer('Dịch hello sang tiếng Nhật') is None
    assert quick_answer('Hãy nhớ: xin chào') is None
    assert quick_answer('bây giờ mấy giờ') and 'Việt Nam' in quick_answer('bây giờ mấy giờ')
    events=chat(client,'hello',mode='tutor',tutor={'language':'en','level':'A1'})
    assert 'answer_source' not in events[-1].get('metrics',{})


def test_fast_chat_reduces_profile_and_schema_without_limiting_long_requests(client):
    from app.performance import runtime_config
    from app.schemas import ChatInput
    config=runtime_config(db.settings(),ChatInput(text='Chúc một ngày vui vẻ',request_id='fast-chat-test'))
    assert config['response_profile']=='fast' and not config['native_tools']
    assert runtime_config(db.settings(),ChatInput(text='Tính 12 * 5',request_id='math-probe'))['native_tools']
    long=runtime_config(db.settings(),ChatInput(text='Giải thích chi tiết',request_id='long-pid-test',response_length='long'))
    assert long['max_output']>=1536

def test_unrequested_tool_call_in_fast_chat_is_denied(client,monkeypatch):
    async def stream(*args,**kwargs):
        yield {'type':'tool_call','call':{'function':{'name':'calculate','arguments':{'expression':'2+2'}}}}
    monkeypatch.setattr(ollama,'stream',stream)
    events=chat(client,'Explain a robot',performance='fast')
    assert any(e['type']=='error' and 'chưa được cấp' in e['message'] for e in events)
    assert not db.rows('SELECT id FROM tool_audit')

def test_auto_keeps_language_tasks_on_quality_model(client):
    from app.performance import runtime_config
    from app.schemas import ChatInput
    settings=db.settings()|{'fast_model':'dbot-qwen35:2b','model':'dbot-qwen35:4b'}
    for text in ['Correct only: He work here.','Tôi muốn học tiếng Anh','学校に行きます。','Explain a robot in English']:
        config=runtime_config(settings,ChatInput(text=text,request_id='quality-language'))
        assert config['model']=='dbot-qwen35:4b' and config['response_profile']=='quality'
    assert runtime_config(settings,ChatInput(text='PID là gì?',request_id='technical-quality'))['model']=='dbot-qwen35:4b'
    assert runtime_config(settings,ChatInput(text='Gợi ý cách nghỉ ngơi ngắn gọn',request_id='fast-vietnamese'))['model']=='dbot-qwen35:2b'

def test_auto_followup_preserves_technical_context_and_brief_quality_prompt(client):
    from app.performance import runtime_config
    from app.schemas import ChatInput
    from app.prompts import build_context,token_cost
    settings=db.settings()|{'fast_model':'dbot-qwen35:2b','model':'dbot-qwen35:4b'}
    body=ChatInput(text='Giải thích tiếp ngắn gọn',request_id='quality-followup',history=[{'role':'user','content':'PID là gì?'},{'role':'assistant','content':'PID gồm P, I, D.'}])
    config=runtime_config(settings,body)
    assert config['model']=='dbot-qwen35:4b' and config['brief_prompt']
    prompt=build_context(config,db.one("SELECT * FROM projects WHERE id='general'"),[],body.text)[0]['content']
    assert token_cost(prompt,config['model'])<400 and 'không cấp quyền' in prompt

def test_english_followup_and_continuation_keep_quality_model(client):
    from app.performance import runtime_config
    from app.schemas import ChatInput
    settings=db.settings()|{'fast_model':'dbot-qwen35:2b','model':'dbot-qwen35:4b'}
    body=ChatInput(text='Vì sao thế?',request_id='english-followup',history=[{'role':'user','content':'Explain this English sentence please.'}])
    assert runtime_config(settings,body)['model']=='dbot-qwen35:4b'
    body=ChatInput(text='Tiếp tục',request_id='continue-quality',continue_response=True)
    assert runtime_config(settings,body)['model']=='dbot-qwen35:4b'
