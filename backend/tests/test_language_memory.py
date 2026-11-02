from types import SimpleNamespace
import pytest
from app import db,ollama
from app.voice import language_audio_slot
from test_languages import client

@pytest.mark.asyncio
async def test_language_audio_unloads_only_owned_models_before_acquiring_worker(monkeypatch):
    posted=[]
    monkeypatch.setattr(db,'settings',lambda:{'model':'owned:4b','fast_model':'owned:4b','coding_model':'owned:4b'})
    class Reply:
        def raise_for_status(self):pass
        def json(self):return {'models':[{'name':'owned:4b'},{'name':'other-app:8b'}]}
    class HTTP:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,path):return Reply()
        async def post(self,path,json):posted.append((path,json));return Reply()
    monkeypatch.setattr(ollama,'client',lambda *args:HTTP())
    async def connected():return False
    async with language_audio_slot(True,SimpleNamespace(is_disconnected=connected)):
        assert ollama.HEAVY_LOCK.locked()
        assert posted==[('/api/generate',{'model':'owned:4b','stream':False,'keep_alive':0})]
    assert not ollama.HEAVY_LOCK.locked()

def test_tutor_prompt_budget_is_compact_without_tool_schema(client):
    from app.prompts import build_context,token_cost
    from app.performance import runtime_config
    from app.schemas import ChatInput
    body=ChatInput(text='Correct this sentence.',request_id='compact-tutor',mode='tutor',tutor={'language':'en','level':'B1','exam':'IELTS','activity':'writing'})
    config=runtime_config(db.settings(),body);config['tutor']=body.tutor.model_dump()
    messages=build_context(config,db.one("SELECT * FROM projects WHERE id='general'"),[],body.text)
    assert not config['native_tools']
    assert token_cost(messages[0]['content'],config['model'])<700
    assert 'IELTS' in messages[0]['content'] and 'Không có công cụ mở máy' in messages[0]['content']

def test_tutor_uses_saved_goal_and_reviewed_correction_with_revocation(client,monkeypatch):
    import json,uuid
    def ask(text,tutor=None):
        r=client.post('/api/chat',json={'text':text,'request_id':str(uuid.uuid4()),'use_knowledge':False,'mode':'tutor' if tutor else 'chat','tutor':tutor})
        assert r.status_code==200,r.text
        return [json.loads(line) for line in r.text.splitlines()]
    client.put('/api/languages/profile',json={'language':'en','level':'B1','exam':'IELTS','target':'IELTS 7.0','daily_minutes':30})
    events=ask('Explain passive voice in a sentence.')
    client.post('/api/feedback',json={'message_id':events[0]['message_id'],'rating':'incorrect','correction':'The robot was built by the team. Passive: be + past participle.'})
    example=client.get('/api/examples').json()[0]
    review={k:example[k] for k in ['question','answer','context']}
    assert client.put('/api/examples/'+example['id'],json=review|{'reviewed':True,'self_contained':True,'status':'approved'}).status_code==200
    seen=[]
    async def stream(messages,config,cancel):seen.extend(messages);yield {'type':'token','text':'Grammar practice.'}
    monkeypatch.setattr(ollama,'stream',stream)
    tutor={'language':'en','level':'B1','exam':'IELTS','activity':'lesson'}
    ask('Explain passive voice again.',tutor)
    assert 'IELTS 7.0' in seen[0]['content'] and 'was built' in seen[0]['content']
    client.post('/api/messages/'+example['message_id']+'/exclude-learning')
    seen.clear();ask('Explain passive voice again.',tutor)
    assert 'was built' not in seen[0]['content']
