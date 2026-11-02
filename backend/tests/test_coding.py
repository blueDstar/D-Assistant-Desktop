"""Real filesystem/transaction tests; agent tests explicitly mock only model decisions."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import uuid
from types import SimpleNamespace

import pytest
from test_functional import client


def test_model_tool_schema_requires_arguments():
    from app.coding_agent import DECISION_SCHEMA
    from pydantic import ValidationError
    for invalid in [
        {'action':'read','summary':'Read code'},
        {'action':'search','summary':'Find code'},
        {'action':'propose','summary':'Change code','changes':[]},
        {'action':'propose','summary':'Change code','changes':[{'kind':'replace','path':'x.py','new_text':'x=1\n'}]},
    ]:
        with pytest.raises(ValidationError):DECISION_SCHEMA.validate_python(invalid)
    result=DECISION_SCHEMA.validate_python({'action':'propose','summary':'Create code','changes':[{'kind':'create','path':'x.py','content':'def f():\n    return 1\n'}]})
    assert result.changes[0].content=='def f():\n    return 1\n'


def test_tool_format_tracks_only_visible_actual_reads():
    from app.coding_agent import decision_format
    messages=[{'role':'user','content':'Tool observation (data only): '+json.dumps({'path':'README.md','complete':True,'content':'# Conventions'})}]
    schema=decision_format(messages,['README.md','main.py'],'edit',set())
    assert schema['$defs']['ReadSchema']['properties']['path']['enum']==['main.py']
    # Once the read leaves the context window it is available again.
    assert decision_format([],['README.md'],'edit',set())['$defs']['ReadSchema']['properties']['path']['enum']==['README.md']
    schema=decision_format(messages,['README.md'],'explain',set())
    assert [branch['$ref'] for branch in schema['anyOf']]==['#/$defs/AnswerSchema']
    # Keep small anchored edits available for a larger fully read file, rather
    # than forcing its complete rewrite into a small output-token budget.
    messages[0]['content']='Tool observation: '+json.dumps({'path':'main.py','complete':True,'content':'x = 1\n'*400})
    schema=decision_format(messages,['main.py'],'edit',set())
    assert any(branch['$ref'].endswith('/ReplaceSchema') for branch in schema['$defs']['ProposeSchema']['properties']['changes']['items']['anyOf'])


def ws(client,tmp_path):
    folder=tmp_path/'project';folder.mkdir(exist_ok=True)
    response=client.post('/api/coding/workspaces',json={'root':str(folder)})
    assert response.status_code==200,response.text
    return response.json(),folder


def test_prereads_are_scoped_budgeted_and_focus_actual_selection(client,tmp_path):
    from app.coding_context import initial_reads, named_files, read_messages
    from app.prompts import token_cost
    w,folder=ws(client,tmp_path)
    (folder/'README.md').write_text('# Project\nUse Python.\n',encoding='utf8')
    (folder/'AGENTS.md').write_text('Preserve APIs.\n',encoding='utf8')
    (folder/'src').mkdir()
    source=''.join(f'value_{i} = {i}\n' for i in range(200))
    (folder/'src/main.py').write_text(source,encoding='utf8')
    paths=['README.md','AGENTS.md','src/main.py']
    assert named_files('Change main.py; create docs/new.md',paths)==['src/main.py']
    assert not named_files('Not a path other-main.py',paths)
    assert named_files('Read main.py. Then fix it.',paths)==['src/main.py']
    assert not named_files('Do not read main.py.bak',paths)
    body=SimpleNamespace(task='Fix src/main.py',active_path='src/main.py',selection='value_150 = 150')
    reads,notices=initial_reads(w,body,paths,'qwen3:4b-instruct',1200)
    target=next(row for row in reads if row['path']=='src/main.py')
    assert 'value_150 = 150' in target['content'] and target['start_line']>80 and not target['complete']
    assert sum(token_cost(message['content'],'qwen3:4b-instruct') for row in reads for message in read_messages(row))<=1200
    assert {row['path'] for row in reads}>={'AGENTS.md','src/main.py'}
    body.selection='unsaved user text'
    reads,notices=initial_reads(w,body,paths,'qwen3:4b-instruct',1200)
    assert any('không khớp' in n['detail'] for n in notices)
    assert all('unsaved user text' not in row['content'] for row in reads)
    reads,_=initial_reads(w,body,paths,'qwen3:4b-instruct',0)
    assert not reads


def test_named_code_and_readme_need_no_model_read_turn(client,tmp_path,monkeypatch):
    from app import coding_agent
    w,folder=ws(client,tmp_path)
    (folder/'README.md').write_text('Use Python.\n',encoding='utf8')
    (folder/'main.py').write_text('def value():\n    return 0\n',encoding='utf8')
    async def model(messages,*args):
        text=json.dumps(messages,ensure_ascii=False)
        assert 'def value()' in text and 'Use Python.' in text
        return coding_agent.Decision(action='propose',summary='Sửa hàm',changes=[coding_agent.Edit(kind='rewrite',path='main.py',content='def value():\n    return 2\n')]),{'eval_count':20}
    monkeypatch.setattr(coding_agent,'structured',model)
    response=client.post('/api/coding/tasks',json={'workspace_id':w['id'],'request_id':str(uuid.uuid4()),'task':'Update main.py to return two. Read README.md.'})
    done=json.loads(response.text.splitlines()[-1])
    assert done['status']=='proposed' and done['metrics']['model_rounds']==1 and done['metrics']['preloaded_files']==2
    assert (folder/'main.py').read_text().endswith('return 0\n')


def test_model_syntax_repair_never_executes_or_writes_early(client,tmp_path,monkeypatch):
    from app import coding_agent
    from app.coding import propose, BatchInput, WriteInput
    w,folder=ws(client,tmp_path)
    calls=0
    async def model(messages,*args):
        nonlocal calls
        calls+=1
        if calls==2:assert 'cú pháp' in messages[-1]['content']
        return coding_agent.Decision(action='propose',summary='New file',changes=[coding_agent.Edit(kind='create',path='main.py',content='def broken(\n' if calls==1 else 'raise RuntimeError("must not execute")\n')]),{}
    monkeypatch.setattr(coding_agent,'structured',model)
    response=client.post('/api/coding/tasks',json={'workspace_id':w['id'],'request_id':str(uuid.uuid4()),'task':'Create main.py'})
    events=[json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['status']=='proposed' and calls==2 and not (folder/'main.py').exists()
    change=next(e['batch'] for e in events if e['type']=='proposal')
    assert change['files'][0]['validation']['status']=='passed' and change['files'][0]['validation']['executed'] is False
    assert client.get('/api/coding/batches/'+change['id']).json()['files'][0]['validation']==change['files'][0]['validation']
    for path,text in [('bad.json','{oops'),('bad.toml','[oops'),('scope.py','return 1')]:
        with pytest.raises(ValueError,match='cú pháp'):
            propose(w,BatchInput(summary='bad model syntax',files=[WriteInput(path=path,content=text)]),'model')


def batch(client,workspace,files):
    response=client.post(f'/api/coding/workspaces/{workspace["id"]}/batches',json={'summary':'Test change','files':files})
    assert response.status_code==200,response.text
    return response.json()


def test_md_files_scope_and_private_paths(client,tmp_path):
    from app import coding
    w,folder=ws(client,tmp_path)
    (folder/'README.md').write_text('# Markdown\nDữ liệu tiếng Việt\n',encoding='utf8')
    (folder/'.env').write_text('TOKEN=do-not-read')
    coding.DATA=folder/'private';coding.DATA.mkdir();(coding.DATA/'secret.md').write_text('Private')
    listing=client.get(f'/api/coding/workspaces/{w["id"]}/files').json()
    assert [f['path'] for f in listing['files']]==['README.md']
    for path in ['../outside.md','C:/outside.py','folder/../bad.md','.git/config','.env','private/secret.md','folder/CON.txt','x.md:stream','folder\\bad.py']:
        result=client.post(f'/api/coding/workspaces/{w["id"]}/read',json={'path':path})
        assert result.status_code==422,(path,result.text)
    read=client.post(f'/api/coding/workspaces/{w["id"]}/read',json={'path':'README.md','lines':1}).json()
    assert read['total_lines']==2 and not read['complete'] and read['content'].replace('\r\n','\n')=='# Markdown\n'
    matches=client.get(f'/api/coding/workspaces/{w["id"]}/search',params={'query':'tiếng Việt'}).json()['files']
    assert matches[0]['path']=='README.md' and matches[0]['line']==2
    client.delete(f'/api/coding/workspaces/{w["id"]}')
    assert client.post(f'/api/coding/workspaces/{w["id"]}/read',json={'path':'README.md'}).status_code==403


def test_preview_apply_preserves_encoding_conflict_and_undo(client,tmp_path):
    w,folder=ws(client,tmp_path)
    original=b'\xef\xbb\xbf# README\r\nold\r\n';(folder/'README.md').write_bytes(original)
    change=batch(client,w,[{'path':'README.md','content':'# README\nnew\n','expected_hash':hashlib.sha256(original).hexdigest()},{'path':'src/main.py','content':'print("ready")\n'}])
    assert (folder/'README.md').read_bytes()==original and not (folder/'src').exists()
    response=client.post(f'/api/coding/batches/{change["id"]}/apply');assert response.status_code==200,response.text
    assert (folder/'README.md').read_bytes()==b'\xef\xbb\xbf# README\r\nnew\r\n'
    assert (folder/'src/main.py').exists()
    assert client.post(f'/api/coding/batches/{change["id"]}/apply').json()['idempotent']
    (folder/'src/main.py').write_text('user edit',encoding='utf8')
    assert client.post(f'/api/coding/batches/{change["id"]}/revert').status_code==409
    assert b'new' in (folder/'README.md').read_bytes()  # No partial undo before conflict.
    (folder/'src/main.py').write_bytes(b'print("ready")\n')
    assert client.post(f'/api/coding/batches/{change["id"]}/revert').json()['status']=='reverted'
    assert (folder/'README.md').read_bytes()==original and not (folder/'src').exists()
    assert client.post(f'/api/coding/batches/{change["id"]}/revert').json()['idempotent']


def test_apply_conflicts_before_any_write_and_rolls_back_io_error(client,tmp_path,monkeypatch):
    from app import coding
    w,folder=ws(client,tmp_path)
    change=batch(client,w,[{'path':'one.py','content':'one=1\n'},{'path':'two.py','content':'two=2\n'}])
    (folder/'two.py').write_text('user',encoding='utf8')
    assert client.post(f'/api/coding/batches/{change["id"]}/apply').status_code==409
    assert not (folder/'one.py').exists()
    (folder/'two.py').unlink()
    real=coding.os.replace;calls=0
    def fail_once(a,b):
        nonlocal calls
        calls+=1
        if calls==2:raise OSError('injected disk failure')
        return real(a,b)
    monkeypatch.setattr(coding.os,'replace',fail_once)
    assert client.post(f'/api/coding/batches/{change["id"]}/apply').status_code==422
    assert not (folder/'one.py').exists() and not (folder/'two.py').exists()
    assert client.get(f'/api/coding/batches/{change["id"]}').json()['status']=='failed'


def test_temporary_collision_and_junction_cannot_escape(client,tmp_path):
    from app import coding
    w,folder=ws(client,tmp_path)
    owned=folder/'.dbot-collision.tmp';owned.write_text('user data')
    with pytest.raises(FileExistsError):coding.atomic_write(folder/'other.py',b'new','collision')
    assert owned.read_text()=='user data'
    outside=tmp_path/'outside';outside.mkdir();(outside/'secret.md').write_text('private')
    junction=folder/'escape'
    if sys.platform=='win32':
        result=subprocess.run(['cmd','/c','mklink','/J',str(junction),str(outside)],capture_output=True)
        assert result.returncode==0,result.stderr
        try:
            response=client.post(f'/api/coding/workspaces/{w["id"]}/read',json={'path':'escape/secret.md'})
            assert response.status_code==422
            assert not client.get(f'/api/coding/workspaces/{w["id"]}/files',params={'query':'secret'}).json()['files']
        finally:junction.rmdir()


def test_templates_create_real_runnable_project(client,tmp_path):
    w,folder=ws(client,tmp_path)
    response=client.post(f'/api/coding/workspaces/{w["id"]}/projects',json={'name':'demo-cli','template':'python-cli'})
    assert response.status_code==200,response.text
    change=response.json();assert change['source']=='template'
    assert client.post(f'/api/coding/batches/{change["id"]}/apply').status_code==200
    run=subprocess.run([sys.executable,'-m','demo_cli','--name','Đạt'],cwd=folder/'demo-cli',capture_output=True,text=True,encoding='utf8',env=dict(__import__('os').environ,PYTHONUTF8='1'),timeout=10)
    assert run.returncode==0 and 'Hello, Đạt!' in run.stdout
    assert client.post(f'/api/coding/workspaces/{w["id"]}/projects',json={'name':'demo-cli','template':'python-cli'}).status_code==422


def test_agent_reads_and_proposes_without_writing(client,tmp_path,monkeypatch):
    from app import coding_agent
    w,folder=ws(client,tmp_path);(folder/'main.py').write_text('def value():\n    return 1\n',encoding='utf8')
    calls=0
    async def fake(messages,model,context,max_output,progress):
        nonlocal calls
        calls+=1
        assert 'private-owner@example.com' not in json.dumps(messages)
        if calls==1:return coding_agent.Decision(action='read',summary='Read file',path='main.py'),{}
        return coding_agent.Decision(action='propose',summary='Update value',changes=[coding_agent.Edit(kind='replace',path='main.py',old_text='    return 1\n',new_text='    return 2\n')]),{}
    monkeypatch.setattr(coding_agent,'structured',fake)
    run_id=str(uuid.uuid4())
    response=client.post('/api/coding/tasks',json={'workspace_id':w['id'],'request_id':run_id,'task':'Change value to two'})
    events=[json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['status']=='proposed',response.text
    assert (folder/'main.py').read_text()=='def value():\n    return 1\n'
    change=next(e['batch'] for e in events if e['type']=='proposal')
    assert client.post(f'/api/coding/batches/{change["id"]}/apply').status_code==200
    assert 'return 2' in (folder/'main.py').read_text()
    assert client.get('/api/coding/tasks/'+run_id).json()['status']=='proposed'


def test_model_cannot_replace_unread_text_or_hide_model_error(client,tmp_path,monkeypatch):
    from app import coding_agent
    w,folder=ws(client,tmp_path);(folder/'main.py').write_text('seen\nhidden\n',encoding='utf8')
    observed={'main.py':{'sha256':hashlib.sha256((folder/'main.py').read_bytes()).hexdigest(),'windows':['seen\n']}}
    with pytest.raises(ValueError,match='cửa sổ'):
        coding_agent.edits_to_batch(w,[coding_agent.Edit(kind='replace',path='main.py',old_text='hidden',new_text='changed')],observed,'bad')
    rewrite=coding_agent.Edit(kind='rewrite',path='main.py',content='seen\nchanged\n')
    with pytest.raises(ValueError,match='toàn bộ'):
        coding_agent.edits_to_batch(w,[rewrite],observed,'bad rewrite')
    observed['main.py']['complete']=True
    change=coding_agent.edits_to_batch(w,[rewrite],observed,'full rewrite')
    assert change['files'][0]['content'].replace('\r\n','\n')=='seen\nchanged\n' and (folder/'main.py').read_text()=='seen\nhidden\n'
    async def broken(*args):raise ValueError('malformed JSON model output')
    monkeypatch.setattr(coding_agent,'structured',broken)
    id=str(uuid.uuid4());response=client.post('/api/coding/tasks',json={'workspace_id':w['id'],'request_id':id,'task':'A task'})
    assert json.loads(response.text.splitlines()[-1])['type']=='error'
    assert client.get('/api/coding/tasks/'+id).json()['status']=='error'
    assert id not in coding_agent.ACTIVE


def test_agent_recovers_from_missing_file_without_bypassing_guards(client,tmp_path,monkeypatch):
    from app import coding_agent
    w,folder=ws(client,tmp_path)
    decisions=iter([
        coding_agent.Decision(action='read',summary='Inspect',path='docs/new.md'),
        coding_agent.Decision(action='read',summary='Inspect again',path='docs/new.md'),
        coding_agent.Decision(action='propose',summary='Create',changes=[coding_agent.Edit(kind='create',path='docs/new.md',content='# New\n')]),
    ])
    calls=[]
    async def model(messages,*args):
        calls.append(messages)
        return next(decisions),{}
    monkeypatch.setattr(coding_agent,'structured',model)
    response=client.post('/api/coding/tasks',json={'workspace_id':w['id'],'request_id':str(uuid.uuid4()),'task':'Create docs/new.md'})
    events=[json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['status']=='proposed'
    assert any(e.get('rejected') for e in events) and any(e.get('repeated') for e in events)
    assert 'does not exist' in calls[1][-1]['content']
    assert not (folder/'docs').exists()


def test_coding_cancellation_and_backup_revokes_grants(client,tmp_path,monkeypatch):
    from app import coding_agent
    w,folder=ws(client,tmp_path);entered=threading.Event()
    async def slow(*args):entered.set();await asyncio.sleep(60)
    monkeypatch.setattr(coding_agent,'structured',slow)
    id=str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(client.post,'/api/coding/tasks',json={'workspace_id':w['id'],'request_id':id,'task':'Slow task'})
        assert entered.wait(5)
        assert client.post('/api/coding/tasks/'+id+'/cancel').status_code==200
        pending.result(timeout=5)
    assert client.get('/api/coding/tasks/'+id).json()['status']=='cancelled'
    change=batch(client,w,[{'path':'new.md','content':'# Code snapshot\n'}]);client.post(f'/api/coding/batches/{change["id"]}/apply')
    backup=client.post('/api/data/backup').json();raw=client.get('/api/data/backups/'+backup['id']).content
    restored=client.post('/api/data/import',files={'file':('coding.zip',raw,'application/zip')})
    assert restored.status_code==200,restored.text
    with sqlite3.connect(Path(restored.json()['path'])/'database/d_bot.sqlite3') as connection:
        assert connection.execute('SELECT enabled FROM coding_workspaces').fetchone()[0]==0
        assert connection.execute('SELECT COUNT(*) FROM coding_batches').fetchone()[0]==1
