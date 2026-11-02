const vscode=acquireVsCodeApi();let lastFiles='',lastBatch='',lastModels='';
const el=id=>document.getElementById(id);
document.addEventListener('click',event=>{const button=event.target.closest('button[data-action]');if(!button)return;vscode.postMessage({type:button.dataset.action,task:el('task').value,index:button.dataset.index?Number(button.dataset.index):0,path:button.dataset.path})});
el('model').addEventListener('change',()=>vscode.postMessage({type:'model',value:el('model').value}));
window.addEventListener('message',({data})=>{
 if(data.type!=='state')return;
 el('workspace').textContent=data.workspace||'Chưa chọn thư mục';el('status').textContent=data.stage||'';el('answer').textContent=data.answer||'';el('events').textContent=(data.events||[]).join('\n\n');
 if(typeof data.taskDraft==='string')el('task').value=data.taskDraft;
 const models=JSON.stringify(data.models);if(models!==lastModels){el('model').replaceChildren();for(const name of data.models||[]){const option=document.createElement('option');option.value=name;option.textContent=name;el('model').append(option)}lastModels=models}el('model').value=data.model;
 el('run').disabled=data.busy;el('explain').disabled=data.busy;el('stop').disabled=!data.busy;el('model').disabled=data.busy;
 const files=JSON.stringify(data.files);if(files!==lastFiles){el('files').replaceChildren();for(const path of data.files||[]){const button=document.createElement('button');button.dataset.action='file';button.dataset.path=path;button.textContent=path;el('files').append(button)}lastFiles=files}
 const batch=data.batch;el('proposal').hidden=!batch;
 if(batch){el('batch-title').textContent=batch.summary;el('batch-status').textContent=`${batch.status} · ${batch.files.length} file · ${batch.source}${batch.error?' · '+batch.error:''}`;el('apply').disabled=data.busy||batch.status!=='proposed';el('revert').disabled=data.busy||!['applied','interrupted','failed'].includes(batch.status);el('open-project').hidden=batch.source!=='template'||batch.status!=='applied';const key=JSON.stringify(batch.files.map(f=>[f.path,f.after_hash]));if(key!==lastBatch){el('changes').replaceChildren();batch.files.forEach((file,index)=>{const row=document.createElement('div'),button=document.createElement('button');button.dataset.action='diff';button.dataset.index=String(index);button.textContent='Xem diff · '+file.path;row.append(button);const details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');summary.textContent=file.before_hash?'Sửa file':'File mới';pre.textContent=file.diff||'(file trống)';details.append(summary,pre);row.append(details);el('changes').append(row)});lastBatch=key}}
});
vscode.postMessage({type:'ready'});
