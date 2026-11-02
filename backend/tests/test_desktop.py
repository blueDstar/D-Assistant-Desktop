import json
from test_functional import client

def test_desktop_history_scoped_private_and_no_fake_execution(client):
    payload={'request_id':'desktop-test-123','text':'Mở PowerPoint','answer':'Bạn muốn mở PowerPoint phải không?','stage':'confirmation'}
    private=client.post('/api/desktop/turn',json=payload|{'private':True}).json();assert not private['persisted']
    from app import db
    assert db.one('SELECT COUNT(*) AS n FROM messages')['n']==0
    receipt=client.post('/api/desktop/turn',json=payload).json();assert receipt['persisted']
    rows=client.get('/api/conversations/'+receipt['conversation_id']+'/messages').json();assert len(rows)==2
    assert json.loads(rows[1]['metadata'])['external_action_confirmed'] is False
    assert client.post('/api/desktop/turn',json=payload).status_code==409
    assert client.post('/api/desktop/turn',json=payload|{'request_id':'new-request-123','project_id':'missing','conversation_id':receipt['conversation_id']}).status_code==404
    assert client.get('/api/careers').json()['applications']==[]

def test_compact_voice_keeps_grounding_and_reduces_prompt(client):
    from app.prompts import build_context,token_cost
    from app import db
    project=db.one('SELECT * FROM projects WHERE id="general"');config=db.settings()|{'response_profile':'fast','voice_conversation':True,'response_length':'short'}
    short=build_context(config,project,[],'Xin chào')[0]['content']
    normal=build_context(config|{'voice_conversation':False},project,[],'Xin chào')[0]['content']
    quality=build_context(config|{'voice_conversation':False,'response_profile':'quality'},project,[],'Xin chào')[0]['content']
    assert token_cost(short)==token_cost(normal)<token_cost(quality)
    assert token_cost(short)<350
    assert 'không cấp quyền' in short and 'biên nhận công cụ' in short and 'Robotics/AI' in short

def test_short_confirmation_is_not_discarded_as_silence(monkeypatch,tmp_path):
    from app import voice_worker
    import faster_whisper.audio
    import numpy as np
    from types import SimpleNamespace
    for name in ['model.bin','config.json','tokenizer.json','vocabulary.txt']:(tmp_path/name).touch()
    monkeypatch.setattr(voice_worker,'STT_PATH',tmp_path)
    monkeypatch.setattr(faster_whisper.audio,'decode_audio',lambda *args,**kwargs:np.full(3200,0.2,dtype=np.float32))
    class Model:
        def transcribe(self,audio,**kwargs):
            assert 'Có' in kwargs['initial_prompt']
            return iter([SimpleNamespace(no_speech_prob=0.1,start=0,end=0.2,text='Có')]),SimpleNamespace(language='vi')
    monkeypatch.setattr(voice_worker,'stt_model',lambda:Model())
    result=voice_worker.transcribe({'audio':b'synthetic','language':'vi','context':'confirmation'})
    assert result['text']=='Có' and not result['silence']
