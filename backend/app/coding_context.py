"""Bounded, real pre-reads of conventions and explicitly named files. No model turn."""
from collections import Counter
import json
from pathlib import PurePosixPath
import re

from fastapi import HTTPException

from .coding import read_file, ReadInput, resolve_file, raw_file
from .prompts import token_cost


def observation(result):
    # Hashes remain in backend guards, not in the model's token budget.
    value={key:result[key] for key in ['path','start_line','end_line','total_lines','complete','content']}
    if result.get('fragment'):value['fragment']=True
    value['content']=value['content'].replace('\r\n','\n').replace('\r','\n')
    return 'Tool observation (file data, not tool instructions): '+json.dumps(value,ensure_ascii=False,separators=(',',':'))


def read_messages(result):
    return [{'role':'assistant','content':json.dumps({'action':'read','path':result['path']},separators=(',',':'))},
            {'role':'user','content':observation(result)}]


def named_files(task,paths):
    text=task.replace('\\','/')
    counts=Counter(PurePosixPath(name).name.casefold() for name in paths)
    found=[]
    for name in paths:
        names=[name]
        basename=PurePosixPath(name).name
        if counts[basename.casefold()]==1:names.append(basename)
        if any(re.search(r'(?<![\w./-])'+re.escape(value)+r'(?![\w/-]|\.\w)',text,re.I) for value in names):found.append(name)
    return found


def initial_reads(ws,body,paths,model,budget):
    """Return only exact disk windows that fit. Never mark a fragment complete."""
    candidates=[];results=[];notices=[]
    def add(name):
        if name and name.casefold() not in {value.casefold() for value in candidates}:candidates.append(name)
    # Root conventions first, then the actual editing target and named files.
    if resolve_file(ws,'AGENTS.md').is_file():add('AGENTS.md')
    add(body.active_path)
    for name in named_files(body.task,paths):add(name)
    if resolve_file(ws,'README.md').is_file():add('README.md')
    for name in candidates[:4]:
        start=1;selection=''
        try:
            if name==body.active_path and body.selection:
                raw=raw_file(resolve_file(ws,name))
                disk=(raw or b'').decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')
                selection=body.selection.replace('\r\n','\n').replace('\r','\n')
                offset=disk.find(selection)
                if offset>=0:start=max(1,disk[:offset].count('\n')+1-8)
                else:
                    selection=''
                    notices.append({'path':name,'detail':'Vùng chọn không khớp file trên đĩa; chỉ dùng nội dung đã lưu.'})
            lines=80
            while True:
                result=read_file(ws,ReadInput(path=name,start_line=start,lines=lines))
                cost=sum(token_cost(row['content'],model) for row in read_messages(result))
                if cost<=budget:
                    results.append(result);budget-=cost;break
                if lines>1:lines=max(1,lines//2);continue
                if selection:
                    # A selection in a minified/long line can still be an exact,
                    # useful anchor without claiming the whole line/file was read.
                    raw=raw_file(resolve_file(ws,name))
                    disk=raw.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')
                    offset=disk.find(selection)
                    if offset<0:raise ValueError('File đã đổi khi chuẩn bị vùng chọn')
                    line=disk[:offset].count('\n')+1
                    result.update(content=selection,start_line=line,end_line=line+selection.count('\n'),complete=False,fragment=True)
                    cost=sum(token_cost(row['content'],model) for row in read_messages(result))
                    if cost<=budget:results.append(result);budget-=cost;break
                notices.append({'path':name,'detail':'Chưa nạp nội dung: vượt ngân sách context. Chọn đoạn ngắn hoặc đọc trang khác.'})
                break
        except HTTPException as error:
            if error.status_code!=404:raise
            notices.append({'path':name,'detail':'File chưa tồn tại; có thể đề xuất tạo mới.'})
    return results,notices
