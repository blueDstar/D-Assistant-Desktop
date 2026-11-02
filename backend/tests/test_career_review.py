"""Isolated synthetic jobs/receipts; these tests never touch Gmail or live data."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from pathlib import Path

from test_careers import application, receipt
from test_functional import client, chat


def posting(**extra):
    return {'responsibilities':'Develop perception models for an autonomous robot.', 'requirements':'Python, OpenCV, Linux and robotics projects.', 'focus':'robotics','hiring_status':'open','location_priority':'local','checked_at':datetime.now(timezone.utc).isoformat(),'sources':['https://example.com/jobs/123'],'recipient_source':'https://example.com/jobs/123',**extra}


def prepare(client,row,**extra):
    return client.post(f'/api/careers/{row["id"]}/outreach-plan',json={'expected_revision':1,'subject':'Synthetic test subject','body_text':'Synthetic test body; not a real application.',**extra})


def test_gate_before_draft_and_revision_revokes_approval(client):
    row=application(client,recipient='hr@example.com')
    path=f'/api/careers/{row["id"]}'
    assert prepare(client,row).status_code==409
    saved=client.put(path+'/posting',json=posting()).json()
    assert saved['review']['status']=='pending' and saved['eligibility']['can_approve']
    assert prepare(client,row).status_code==409
    assert client.post(path+'/review',json={'expected_revision':2,'decision':'approved'}).status_code==409
    assert client.post(path+'/review',json={'expected_revision':1,'decision':'approved'}).json()['eligibility']['can_prepare']
    assert prepare(client,row).json()['status']=='prepared_local'
    assert prepare(client,row,send_after='2020-01-01T00:00:00').status_code==422
    # Rechecking an unchanged JD retains approval; semantic changes revoke it.
    saved=client.put(path+'/posting',json=posting()).json()
    assert saved['review']['revision']==1 and saved['review']['status']=='approved' and saved['review']['plan']
    saved=client.put(path+'/posting',json=posting(requirements='Python, OpenCV, Linux, ROS2 and advanced SLAM.')).json()
    assert saved['review']['revision']==2 and saved['review']['status']=='pending' and saved['review']['plan'] is None
    assert prepare(client,row,expected_revision=2).status_code==409
    assert client.post(path+'/review',json={'expected_revision':1,'decision':'approved'}).status_code==409
    assert client.get('/api/careers').json()['counts']['sent']==0


def test_company_alias_dedup_preserves_history_and_blocks_new_draft(client):
    original=application(client,company='Endava',role='Junior C++ Networking')
    client.post(f'/api/careers/{original["id"]}/events',json=receipt())
    alias=application(client,company='DEK Technologies Vietnam',role='AI Engineer')
    p=f'/api/careers/{alias["id"]}'
    saved=client.put(p+'/posting',json=posting()).json()
    assert saved['eligibility']['company_contacted'] and not saved['eligibility']['can_approve']
    assert client.post(p+'/review',json={'expected_revision':1,'decision':'approved'}).status_code==409
    live=next(r for r in client.get('/api/careers').json()['applications'] if r['id']==original['id'])
    assert live['stage']=='sent' and len(live['events'])==1
    assert live['events'][0]['detail']['message_id']=='synthetic-message-123'


def test_closed_expired_stale_and_networking_jobs_cannot_be_approved(client):
    from app import db
    cases=[posting(hiring_status='closed'),posting(deadline='2020-01-01'),posting(checked_at=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat()),posting(focus='outside_target'),posting(responsibilities='Implement networking stack for telecom switches.')]
    for i,value in enumerate(cases):
        row=application(client,company=f'Test {i}')
        path=f'/api/careers/{row["id"]}'
        assert not client.put(path+'/posting',json=value).json()['eligibility']['can_approve']
        assert client.post(path+'/review',json={'expected_revision':1,'decision':'approved'}).status_code==409
    row=application(client,company='No Contact Source',recipient='hr@example.com')
    path=f'/api/careers/{row["id"]}'
    client.put(path+'/posting',json=posting(recipient_source=''))
    client.post(path+'/review',json={'expected_revision':1,'decision':'approved'})
    assert prepare(client,row).status_code==409
    assert db.one('SELECT COUNT(*) AS n FROM career_events WHERE kind="email_sent"')['n']==0


def test_factual_chat_complete_list_targeting_private_and_no_model_lock(client,monkeypatch):
    from app import db, ollama
    from app.career_answers import factual_answer
    for i in range(14):
        row=application(client,company=f'RobotCompany{i}',role=f'Robot Engineer {i}')
        client.post(f'/api/careers/{row["id"]}/events',json=receipt(operation_id=f'email-outreach-{i}',message_id=f'mail-{i}'))
    text=factual_answer('Tôi đã apply công ty nào?')
    assert all(f'RobotCompany{i} ' in text for i in range(14))
    targeted=factual_answer('Tôi đã gửi RobotCompany0 vị trí gì?')
    assert 'Robot Engineer 0' in targeted and 'RobotCompany13' not in targeted
    assert factual_answer('Lập lịch học ROS2 cho tôi') is None
    assert factual_answer('Hướng dẫn kỹ thuật phỏng vấn ROS2') is None
    before=db.one('SELECT COUNT(*) AS n FROM messages')['n']
    class ForbiddenModelLock:
        def locked(self): raise AssertionError('Factual recall must not wait on model inference')
    monkeypatch.setattr(ollama,'HEAVY_LOCK',ForbiddenModelLock())
    events=chat(client,'Tôi đã apply công ty nào?',private=True)
    assert events[-1]['status']=='completed' and events[-1]['metrics']['answer_source']=='career_ledger'
    assert 'mock' not in ''.join(e.get('text','') for e in events)
    assert db.one('SELECT COUNT(*) AS n FROM messages')['n']==before
    events=chat(client,'Soạn và gửi email ứng tuyển ngay')
    assert 'Phù hợp · cho phép soạn' in ''.join(e.get('text','') for e in events)
    assert db.one('SELECT COUNT(*) AS n FROM career_events WHERE kind="email_draft"')['n']==0


def test_calendar_latest_pending_timezone_and_no_duplicate(client):
    from app.career_answers import factual_answer
    row=application(client,company='Wisdom Test',role='AI Engineer')
    day=(datetime.now(timezone.utc)+timedelta(days=2)).date().isoformat()
    base=receipt(kind='interview',source='calendar_connector',calendar_event_id='event-1',starts_at=day+'T01:00:00+00:00',ends_at=day+'T05:00:00+00:00',interview_status='needs_confirmation',provider_response='needsAction',body_text='Invitation body conflicts with Calendar; HR clarification pending.')
    url=f'/api/careers/{row["id"]}/events'
    client.post(url,json=base|{'operation_id':'calendar-before','occurred_at':'2026-10-26T00:00:00Z'})
    client.post(url,json=base|{'operation_id':'calendar-after','occurred_at':'2026-10-27T00:00:00Z'})
    text=factual_answer('Lịch trình phỏng vấn của tôi?')
    assert text.count('Wisdom Test')==1 and '08:00' in text and '12:00' in text and 'Chờ HR' in text and 'needsAction' in text
    client.post(url,json=base|{'operation_id':'calendar-cancelled','occurred_at':'2026-10-28T00:00:00Z','interview_status':'cancelled'})
    assert 'Chưa có lịch phỏng vấn' in factual_answer('Lịch trình của tôi?')


def test_review_backup_and_pre_review_backup(client):
    from app import db
    row=application(client)
    client.put(f'/api/careers/{row["id"]}/posting',json=posting())
    def restore_backup():
        backup=client.post('/api/data/backup').json()
        return client.get(f'/api/data/backups/{backup["id"]}').content
    raw=restore_backup()
    restored=client.post('/api/data/import',files={'file':('backup.zip',raw,'application/zip')})
    assert restored.status_code==200,restored.text
    with sqlite3.connect(Path(restored.json()['path'])/'database/d_bot.sqlite3') as connection:
        assert connection.execute('SELECT status FROM career_reviews').fetchone()[0]=='pending'
    db.execute('DROP TABLE career_reviews')
    raw=restore_backup()
    db.migrate()
    restored=client.post('/api/data/import',files={'file':('old.zip',raw,'application/zip')})
    assert restored.status_code==200,restored.text
    with sqlite3.connect(Path(restored.json()['path'])/'database/d_bot.sqlite3') as connection:
        assert connection.execute('SELECT COUNT(*) FROM career_reviews').fetchone()[0]==0
