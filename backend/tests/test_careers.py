"""Ledger/receipt tests. Connector IDs here are synthetic; no email is sent by tests."""
import sqlite3
from pathlib import Path
import json
from test_functional import client


def application(client, **extra):
    response=client.post('/api/careers',json={'company':'Test Robotics','role':'Junior C++','job_url':'https://example.com/jobs/123','location':'Thu Duc','stage':'shortlisted',**extra})
    assert response.status_code==200,response.text
    return response.json()


def receipt(**extra):
    return {'operation_id':'gmail-test-123','kind':'email_sent','source':'gmail_connector','occurred_at':'2026-10-27T00:00:00+07:00','message_id':'synthetic-message-123','thread_id':'synthetic-thread-123','body_text':'Application body.','url':'https://mail.google.com/','attachment_sha256':'a'*64,**extra}


def test_dedup_and_invalid_external_actions(client):
    row=application(client)
    duplicate=application(client,company='test robotics',role='junior c++')
    assert duplicate['duplicate'] and duplicate['id']==row['id']
    assert client.post('/api/careers',json={'company':'x','role':'y','job_url':'javascript:alert(1)'}).status_code==422
    assert client.post('/api/careers',json={'company':'x','role':'y','job_url':'https://example.com','stage':'sent'}).status_code==422
    assert client.post('/api/careers',json={'company':'x','role':'y','job_url':'https://example.com','recipient':'a@b.com\nBcc:other@example.com'}).status_code==422
    assert client.put('/api/careers/preferences',json={'salary_min':18000000,'salary_max':14000000}).status_code==422
    assert client.patch(f'/api/careers/{row["id"]}/stage',json={'stage':'interview','reason':'No receipt'}).status_code==422


def test_email_receipt_idempotency_and_scope(client):
    row=application(client)
    url=f'/api/careers/{row["id"]}/events'
    assert client.post(url,json=receipt(source='user')).status_code==422
    assert client.post(url,json=receipt(message_id='')).status_code==422
    assert client.post(url,json=receipt(occurred_at='2026-10-27T00:00:00')).status_code==422
    assert client.post(url,json=receipt()).json()['application']['stage']=='sent'
    assert client.post(url,json=receipt()).json()['duplicate'] is True
    assert client.post(url,json=receipt(body_text='Changed receipt')).status_code==409
    other=application(client,company='Other Company')
    assert client.post(f'/api/careers/{other["id"]}/events',json=receipt()).status_code==409
    rows=client.get('/api/careers').json()['applications']
    assert len(next(r for r in rows if r['id']==row['id'])['events'])==1
    assert client.get('/api/careers').json()['external_actions_available'] is False
    from app.careers import career_context
    context=career_context('Tôi đã gửi ứng tuyển cho công ty nào?')
    assert 'Test Robotics' in context and '"email_sent": true' in context and '"sent": 1' in context
    assert 'Test Robotics' in career_context('Toi da gui email ung tuyen cho cong ty nao?')
    assert career_context('Chào bạn')==''
    assert client.delete(f'/api/careers/{row["id"]}').json()['ok']
    remaining=client.get('/api/careers').json()['applications']
    assert len(remaining)==1 and remaining[0]['id']==other['id']


def test_interview_needs_calendar_receipt_and_valid_interval(client):
    row=application(client)
    payload=receipt(operation_id='calendar-test-123',kind='interview',source='calendar_connector',calendar_event_id='synthetic-event-123',starts_at='2026-10-28T10:00:00+07:00',ends_at='2026-10-28T11:00:00+07:00',interview_mode='online')
    url=f'/api/careers/{row["id"]}/events'
    assert client.post(url,json=payload|{'calendar_event_id':''}).status_code==422
    assert client.post(url,json=payload|{'ends_at':'2026-10-28T09:00:00+07:00'}).status_code==422
    assert client.post(url,json=payload).json()['application']['stage']=='interview'
    exported=client.get('/api/careers/export')
    assert exported.status_code==200 and exported.json()['applications'][0]['events'][0]['detail']['starts_at'].endswith('+07:00')
    assert client.post(url,json=payload|{'operation_id':'bad-confirmed-123','interview_status':'confirmed','provider_response':'needsAction'}).status_code==422
    assert client.post(url,json=payload|{'operation_id':'pending-calendar-123','interview_status':'needs_confirmation','provider_response':'needsAction'}).status_code==200
    assert client.post(url,json=receipt(operation_id='clarification-mail-123')).json()['application']['stage']=='interview'
    from app.careers import career_context
    context=career_context('Lịch phỏng vấn của tôi?')
    assert 'needs_confirmation' in context and '"interviews": 1' in context
    other=application(client,company='Reply Only')
    client.post(f'/api/careers/{other["id"]}/events',json=receipt(operation_id='reply-only-123',email_purpose='follow_up'))
    context=career_context('Các công ty đã gửi ứng tuyển?')
    assert 'Reply Only' not in context and '"sent": 1' in context


def test_career_filters_apply_before_limit_and_mark_partial_results(client):
    from app.careers import career_context
    excluded=application(client,company='Excluded PLC',stage='excluded')
    for i in range(12):
        row=application(client,company=f'Company {i}')
        client.post(f'/api/careers/{row["id"]}/events',json=receipt(operation_id=f'email-number-{i}',message_id=f'mail-{i}'))
    assert 'Excluded PLC' in career_context('Các công ty đã loại khỏi ứng tuyển?')
    assert '"records_limited": true' in career_context('Tôi đã gửi ứng tuyển cho ai?')


def test_career_backup_restore_and_pre_career_backup(client):
    from app import db
    row=application(client)
    client.post(f'/api/careers/{row["id"]}/events',json=receipt())
    backup=client.post('/api/data/backup').json()
    raw=client.get(f'/api/data/backups/{backup["id"]}').content
    restored=client.post('/api/data/import',files={'file':('backup.zip',raw,'application/zip')})
    assert restored.status_code==200,restored.text
    with sqlite3.connect(Path(restored.json()['path'])/'database/d_bot.sqlite3') as connection:
        assert connection.execute('SELECT company FROM career_applications').fetchone()[0]=='Test Robotics'
        assert connection.execute('SELECT COUNT(*) FROM career_events').fetchone()[0]==1
    # Produce a genuine old additive schema, then return the live test DB to current.
    with db.connect() as connection:
        connection.execute('DROP TABLE career_events')
        connection.execute('DROP TABLE career_applications')
    backup=client.post('/api/data/backup').json()
    raw=client.get(f'/api/data/backups/{backup["id"]}').content
    db.migrate()
    restored=client.post('/api/data/import',files={'file':('old-backup.zip',raw,'application/zip')})
    assert restored.status_code==200,restored.text
    with sqlite3.connect(Path(restored.json()['path'])/'database/d_bot.sqlite3') as connection:
        assert connection.execute('SELECT COUNT(*) FROM career_applications').fetchone()[0]==0
