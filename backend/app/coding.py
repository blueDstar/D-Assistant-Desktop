"""Scoped coding files, reviewable batches and guarded recovery. No shell execution."""
import base64
import difflib
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import threading
import time
import tomllib
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field, ConfigDict

from . import db
from .config import DATA
from .schemas import StrictModel

router=APIRouter(prefix='/api/coding',tags=['coding'])
MAX_FILE=512000
MAX_BATCH=1024000
TEXT={'.md','.markdown','.mdx','.txt','.py','.pyi','.js','.jsx','.mjs','.cjs','.ts','.tsx','.json','.jsonc','.yaml','.yml','.toml','.ini','.cfg','.html','.css','.scss','.sass','.less','.svg','.c','.cpp','.h','.hpp','.cs','.java','.go','.rs','.sql','.sh','.ps1','.bat','.cmd','.vue','.svelte','.ino','.xml','.r','.rb','.php','.gitignore','.editorconfig'}
SKIP={'.git','.hg','.svn','.codex','.agents','.aws','.ssh','.gnupg','.vscode','node_modules','.venv','venv','.runtime','__pycache__','.pytest_cache','dist','build','.next','coverage'}
SECRET={'.npmrc','.pypirc','.netrc','id_rsa','id_ed25519','credentials.json','service-account.json'}
LOCKS={}


def audit(workspace_id,event,reference='',detail=None):
    db.execute('INSERT INTO coding_audit VALUES(?,?,?,?,?,?)',(db.uid(),workspace_id,event,reference,json.dumps(detail or {},ensure_ascii=False),db.now()))


def sha(raw):return hashlib.sha256(raw).hexdigest() if raw is not None else None
def unpack(value):return base64.b64decode(value,validate=True) if value is not None else None
def pack(value):return base64.b64encode(value).decode('ascii') if value is not None else None


def validate_syntax(path,raw):
    """Parse/compile only: never execute model-generated code or import its modules."""
    kind=path.suffix.casefold()
    if kind not in {'.py','.json','.toml'}:return {'status':'not_run','executed':False}
    text=raw.decode('utf-8-sig')
    try:
        if kind=='.py':compile(text,str(path),'exec',dont_inherit=True)
        elif kind=='.json':json.loads(text)
        else:tomllib.loads(text)
    except (SyntaxError,ValueError,RecursionError,MemoryError) as error:
        raise ValueError('Kiểm tra cú pháp từ chối '+path.name+': '+str(error)[:350])
    return {'status':'passed','check':'Python 3.12 compile' if kind=='.py' else 'JSON parse' if kind=='.json' else 'TOML parse','executed':False}


def protected(parts):
    return any(p.casefold() in SKIP or p.casefold() in SECRET or p.casefold().startswith('.env') or p.casefold().endswith(('.pem','.key','.p12','.pfx')) for p in parts)


def workspace(id, require_enabled=True):
    row=db.one('SELECT * FROM coding_workspaces WHERE id=?',(id,))
    if not row:raise HTTPException(404,'Workspace lập trình không tồn tại')
    if require_enabled and not row['enabled']:raise HTTPException(403,'Workspace đã bị thu hồi quyền. Chọn lại thư mục để cấp quyền.')
    root=Path(row['root'])
    if require_enabled and (not root.is_dir() or root.resolve()!=root):raise HTTPException(409,'Thư mục gốc đã thay đổi hoặc không còn tồn tại')
    return row


def relative_path(value):
    if not value or len(value)>700 or '\x00' in value or '\\' in value or ':' in value or PureWindowsPath(value).is_absolute():
        raise ValueError('Dùng đường dẫn tương đối với dấu / trong workspace; không có drive/UNC/ADS.')
    parts=value.split('/')
    if any(not p or p in {'.','..'} or p.endswith((' ','.')) or re.search(r'[<>"|?*\x00-\x1f]',p) or re.fullmatch(r'(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?',p) for p in parts):
        raise ValueError('Đường dẫn không hợp lệ hoặc có thành phần Windows dành riêng')
    if protected(parts):raise ValueError('Không truy cập thư mục nội bộ, môi trường, khóa hoặc file chứa thông tin xác thực')
    return '/'.join(parts)


def resolve_file(ws,value, text_only=True):
    value=relative_path(value)
    root=Path(ws['root']);candidate=root/value
    resolved=candidate.resolve()
    if not resolved.is_relative_to(root) or resolved.is_relative_to(DATA.resolve()):
        raise ValueError('File ngoài workspace hoặc thuộc dữ liệu riêng của D-bot')
    current=root
    for part in value.split('/'):
        current=current/part
        if current.is_symlink() or current.is_junction():raise ValueError('Không đi qua symlink/junction trong workspace')
    if text_only and candidate.suffix.casefold() not in TEXT and candidate.name.casefold() not in {'dockerfile','makefile','license','.gitignore','.editorconfig'}:
        raise ValueError('Chỉ hỗ trợ file mã nguồn/Markdown/text, không sửa file nhị phân')
    return candidate


def raw_file(path):
    if not path.exists():return None
    if not path.is_file() or path.stat().st_size>MAX_FILE:raise ValueError('File không phải text hoặc vượt 500 KiB')
    raw=path.read_bytes()
    if b'\0' in raw:raise ValueError('File nhị phân không được hỗ trợ')
    raw.decode('utf-8-sig')
    return raw


def encode_text(content,old,path):
    if '\x00' in content:raise ValueError('Nội dung chứa byte NUL')
    content=content.replace('\r\n','\n').replace('\r','\n')
    if old and b'\r\n' in old and old.count(b'\n')==old.count(b'\r\n'):
        content=content.replace('\n','\r\n')
    bom=(old is not None and old.startswith(b'\xef\xbb\xbf')) or (old is None and path.suffix.casefold()=='.ps1')
    raw=(b'\xef\xbb\xbf' if bom else b'')+content.encode('utf8')
    if len(raw)>MAX_FILE:raise ValueError('File đề xuất vượt 500 KiB')
    return raw


class WorkspaceInput(StrictModel):
    root:str=Field(min_length=1,max_length=1000)
    name:str=Field(default='',max_length=120)


class ReadInput(StrictModel):
    path:str=Field(min_length=1,max_length=700)
    start_line:int=Field(default=1,ge=1,le=100000)
    lines:int=Field(default=160,ge=1,le=240)


class WriteInput(StrictModel):
    model_config=ConfigDict(str_strip_whitespace=False)
    path:str=Field(min_length=1,max_length=700)
    content:str=Field(max_length=500000)
    expected_hash:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')


class BatchInput(StrictModel):
    summary:str=Field(min_length=1,max_length=2000)
    files:list[WriteInput]=Field(min_length=1,max_length=16)


@router.get('/workspaces')
def list_workspaces():return db.rows('SELECT * FROM coding_workspaces ORDER BY updated_at DESC')


@router.post('/workspaces')
def register_workspace(body:WorkspaceInput):
    if not Path(body.root).is_absolute():raise ValueError('Cần đường dẫn tuyệt đối tới thư mục project')
    if body.root.startswith(('\\\\','//')):raise ValueError('Không cấp quyền UNC/network share')
    try:path=Path(body.root).resolve(strict=True)
    except OSError:raise ValueError('Thư mục chưa tồn tại hoặc không đọc được')
    if not path.is_dir() or path==Path(path.anchor) or protected(path.parts) or path.is_relative_to(DATA.resolve()):
        raise ValueError('Chọn thư mục project cụ thể, không chọn gốc ổ đĩa/thư mục nội bộ/dữ liệu D-bot')
    old=db.one('SELECT * FROM coding_workspaces WHERE root=?',(str(path),))
    if old:
        db.execute('UPDATE coding_workspaces SET enabled=1,updated_at=? WHERE id=?',(db.now(),old['id']))
        return workspace(old['id'])
    id=db.uid();now=db.now()
    db.execute('INSERT INTO coding_workspaces VALUES(?,?,?,?,?,?)',(id,str(path),body.name or path.name,1,now,now))
    audit(id,'workspace_granted',detail={'root':str(path)})
    return workspace(id)


@router.delete('/workspaces/{id}')
def revoke_workspace(id:str):
    workspace(id,False)
    db.execute('UPDATE coding_workspaces SET enabled=0,updated_at=? WHERE id=?',(db.now(),id))
    audit(id,'workspace_revoked')
    from .coding_agent import ACTIVE
    for cancel,workspace_id in list(ACTIVE.values()):
        if workspace_id==id:cancel.set()
    return {'ok':True,'notice':'Đã thu hồi quyền. File project và lịch sử thay đổi vẫn còn.'}


def tree(ws,query='',content=False):
    root=Path(ws['root']);found=[];visited=0;started=time.monotonic()
    for current,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=sorted(d for d in dirs if not protected([d]) and not (Path(current)/d).is_symlink() and not (Path(current)/d).is_junction() and not (Path(current)/d).resolve().is_relative_to(DATA.resolve()))
        for name in sorted(files):
            visited+=1
            if visited>5000 or time.monotonic()-started>4:return {'files':found,'limited':True}
            relative=(Path(current)/name).relative_to(root).as_posix()
            try:
                path=resolve_file(ws,relative)
                if not path.is_file() or path.stat().st_size>MAX_FILE:continue
                if content:
                    text=raw_file(path).decode('utf-8-sig')
                    for number,line in enumerate(text.splitlines(),1):
                        if query.casefold() in line.casefold():found.append({'path':relative,'line':number,'text':line[:500]})
                        if len(found)>=50:return {'files':found,'limited':True}
                elif not query or query.casefold() in relative.casefold():found.append({'path':relative,'bytes':path.stat().st_size})
            except (ValueError,OSError,UnicodeError):continue
            if len(found)>=300:return {'files':found,'limited':True}
    return {'files':found,'limited':False}


@router.get('/workspaces/{id}/files')
def list_files(id:str,query:str=''):return tree(workspace(id),query[:200])


@router.get('/workspaces/{id}/search')
def search_files(id:str,query:str):
    if not query or len(query)>200:raise ValueError('Từ khóa từ 1–200 ký tự')
    return tree(workspace(id),query,True)


def read_file(ws,body):
    path=resolve_file(ws,body.path);raw=raw_file(path)
    if raw is None:raise HTTPException(404,'File không tồn tại')
    text=raw.decode('utf-8-sig');lines=text.splitlines(keepends=True)
    selected=''.join(lines[body.start_line-1:body.start_line+body.lines-1])
    return {'path':body.path,'content':selected,'sha256':sha(raw),'total_lines':len(lines),'start_line':body.start_line,'end_line':min(len(lines),body.start_line+body.lines-1),'complete':body.start_line==1 and len(lines)<=body.lines,'bytes':len(raw)}


@router.post('/workspaces/{id}/read')
def read(id:str,body:ReadInput):return read_file(workspace(id),body)


def batch_row(id):
    row=db.one('SELECT * FROM coding_batches WHERE id=?',(id,))
    if not row:raise HTTPException(404,'Không tìm thấy bản thay đổi')
    return row


def public_batch(row):
    files=[]
    for f in json.loads(row['files']):
        old=(unpack(f['before']) or b'').decode('utf-8-sig')
        new=unpack(f['after']).decode('utf-8-sig')
        diff=''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),fromfile=f['path']+' (trước)',tofile=f['path']+' (sau)'))
        files.append({'path':f['path'],'before_hash':f['before_hash'],'after_hash':f['after_hash'],'content':new,'old_content':old,'diff':diff[:200000],'diff_truncated':len(diff)>200000,'validation':f.get('validation',{'status':'not_run','executed':False})})
    return {key:value for key,value in row.items() if key not in {'files','created_dirs'}}|{'files':files}


def propose(ws,body,source='manual'):
    seen=set();files=[];total=0
    for entry in body.files:
        path=resolve_file(ws,entry.path)
        key=str(path).casefold()
        if key in seen:raise ValueError('Một file xuất hiện nhiều lần trong bản thay đổi')
        seen.add(key);before=raw_file(path)
        if sha(before)!=entry.expected_hash:raise HTTPException(409,'File đã thay đổi hoặc đã tồn tại: '+entry.path+'. Đọc lại rồi tạo đề xuất mới.')
        after=encode_text(entry.content,before,path);total+=len(after)+(len(before) if before else 0)
        if total>MAX_BATCH:raise ValueError('Tổng thay đổi và bản gốc vượt 1 MiB; chia thành các tác vụ nhỏ')
        if before==after:continue
        validation=validate_syntax(path,after) if source=='model' else {'status':'not_run','executed':False}
        files.append({'path':entry.path,'before':pack(before),'after':pack(after),'before_hash':sha(before),'after_hash':sha(after),'validation':validation})
    if not files:raise ValueError('Không có thay đổi nội dung')
    id=db.uid();now=db.now()
    db.execute('INSERT INTO coding_batches VALUES(?,?,?,?,?,?,?,?,?,?)',(id,ws['id'],source,body.summary,'proposed',json.dumps(files,ensure_ascii=False),'[]','',now,now))
    audit(ws['id'],'proposed',id,{'files':[f['path'] for f in files],'source':source})
    return public_batch(batch_row(id))


@router.post('/workspaces/{id}/batches')
def propose_manual(id:str,body:BatchInput):return propose(workspace(id),body)


@router.get('/batches/{id}')
def get_batch(id:str):return public_batch(batch_row(id))


@router.get('/workspaces/{id}/history')
def history(id:str):
    workspace(id,False)
    return {'batches':db.rows('SELECT id,summary,status,source,created_at,updated_at,error FROM coding_batches WHERE workspace_id=? ORDER BY created_at DESC LIMIT 60',(id,)),'runs':db.rows('SELECT id,task,model,status,batch_id,answer,error,created_at FROM coding_runs WHERE workspace_id=? ORDER BY created_at DESC LIMIT 30',(id,))}


def lock(ws):return LOCKS.setdefault(ws['id'],threading.RLock())


def atomic_write(path,raw,identifier):
    temp=path.with_name('.dbot-'+identifier+'.tmp')
    created=False
    try:
        with temp.open('xb') as output:
            created=True;output.write(raw);output.flush();os.fsync(output.fileno())
        os.replace(temp,path)
    finally:
        if created:temp.unlink(missing_ok=True)


def restore_files(ws,files,dirs,identifier):
    # Validate every current hash before touching any file; never undo later user edits.
    for f in files:
        actual=sha(raw_file(resolve_file(ws,f['path'])))
        if actual not in {f['before_hash'],f['after_hash']}:
            raise HTTPException(409,'File có thay đổi mới; không khôi phục đè: '+f['path'])
        if sha(unpack(f['before']))!=f['before_hash']:raise ValueError('Bản khôi phục không khớp hash')
    for index,f in enumerate(reversed(files)):
        path=resolve_file(ws,f['path'])
        if sha(raw_file(path))==f['before_hash']:continue
        before=unpack(f['before'])
        if before is None:path.unlink()
        else:atomic_write(path,before,identifier+'-undo-'+str(index))
    for directory in reversed(dirs):
        path=resolve_file(ws,directory,False)
        if path.exists():
            try:path.rmdir()
            except OSError:pass  # Only empty directories created by this batch.


@router.post('/batches/{id}/apply')
def apply_batch(id:str):
    initial=batch_row(id);ws=workspace(initial['workspace_id'])
    with lock(ws):
        row=batch_row(id)
        if row['status']=='applied':return public_batch(row)|{'idempotent':True}
        if row['status']!='proposed':raise HTTPException(409,'Bản thay đổi không ở trạng thái chờ áp dụng; kiểm tra/khôi phục trước.')
        files=json.loads(row['files']);dirs=[]
        for f in files:
            path=resolve_file(ws,f['path'])
            if sha(raw_file(path))!=f['before_hash']:raise HTTPException(409,'File đã đổi sau khi tạo diff: '+f['path'])
            if sha(unpack(f['after']))!=f['after_hash']:raise ValueError('Nội dung đề xuất không khớp hash')
            parent=path.parent;missing=[]
            while parent!=Path(ws['root']) and not parent.exists():missing.append(parent);parent=parent.parent
            for p in reversed(missing):
                value=p.relative_to(ws['root']).as_posix()
                if value not in dirs:dirs.append(value)
        db.execute("UPDATE coding_batches SET status='applying',created_dirs=?,updated_at=? WHERE id=?",(json.dumps(dirs),db.now(),id))
        written=[]
        try:
            for index,f in enumerate(files):
                path=resolve_file(ws,f['path']);path.parent.mkdir(parents=True,exist_ok=True)
                if sha(raw_file(path))!=f['before_hash']:raise HTTPException(409,'File đổi trong lúc áp dụng: '+f['path'])
                atomic_write(path,unpack(f['after']),id+'-'+str(index));written.append(f)
            db.execute("UPDATE coding_batches SET status='applied',updated_at=? WHERE id=?",(db.now(),id))
            audit(ws['id'],'applied',id,{'files':[{k:f[k] for k in ['path','before_hash','after_hash']} for f in files]})
            return public_batch(batch_row(id))
        except Exception as error:
            state='failed'
            try:restore_files(ws,written,dirs,id)
            except Exception:state='interrupted'
            db.execute('UPDATE coding_batches SET status=?,error=?,updated_at=? WHERE id=?',(state,str(error)[:1500],db.now(),id))
            audit(ws['id'],state,id,{'error':str(error)[:500]})
            if isinstance(error,OSError):raise HTTPException(422,'Ghi file không thành công; kiểm tra trạng thái khôi phục: '+str(error)[:300])
            raise


@router.post('/batches/{id}/revert')
def revert_batch(id:str):
    row=batch_row(id);ws=workspace(row['workspace_id'])
    with lock(ws):
        row=batch_row(id)
        if row['status']=='reverted':return public_batch(row)|{'idempotent':True}
        if row['status'] not in {'applied','interrupted','failed'}:raise HTTPException(409,'Chỉ khôi phục bản đã áp dụng/gián đoạn')
        restore_files(ws,json.loads(row['files']),json.loads(row['created_dirs']),id)
        db.execute("UPDATE coding_batches SET status='reverted',updated_at=? WHERE id=?",(db.now(),id))
        audit(ws['id'],'reverted',id)
        return public_batch(batch_row(id))
