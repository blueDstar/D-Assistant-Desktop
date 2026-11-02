import * as vscode from 'vscode'
import * as path from 'node:path'
import { createHash, randomBytes, randomUUID } from 'node:crypto'
import { DbotClient } from './client'
import { safeRelative, withinRoot } from './paths'

type Workspace={id:string;root:string;name:string}
class PreviewDocuments implements vscode.TextDocumentContentProvider {
  readonly values=new Map<string,string>()
  provideTextDocumentContent(uri:vscode.Uri){return this.values.get(uri.toString())||''}
  add(key:string,text:string){const uri=vscode.Uri.from({scheme:'dbot-preview',path:'/'+key});this.values.set(uri.toString(),text);return uri}
}

class Assistant implements vscode.WebviewViewProvider {
  private view?:vscode.WebviewView
  private workspace?:Workspace
  private batch:any=null
  private controller?:AbortController
  private requestId=''
  private busy=false
  private client:DbotClient
  private model:string
  private models:string[]=[]
  private files:string[]=[]
  private events:string[]=[]
  private answer=''
  private stage='Chọn thư mục để bắt đầu.'
  private taskDraft:string|undefined
  constructor(private context:vscode.ExtensionContext,private previews:PreviewDocuments,private output:vscode.OutputChannel){this.client=this.makeClient();this.model=vscode.workspace.getConfiguration('dbot').get('model','qwen3:4b-instruct')}
  private makeClient(){return new DbotClient(vscode.workspace.getConfiguration('dbot').get('endpoint','http://127.0.0.1:8008'))}
  private trusted(){if(!vscode.workspace.isTrusted)throw new Error('Hãy dùng workspace bạn tin cậy; D-bot không chạy trong Restricted Mode.')}
  resolveWebviewView(view:vscode.WebviewView){
    this.view=view;view.webview.options={enableScripts:true,localResourceRoots:[vscode.Uri.joinPath(this.context.extensionUri,'media')]}
    const nonce=randomBytes(24).toString('hex'),script=view.webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri,'media','view.js')),css=view.webview.asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri,'media','view.css'))
    view.webview.html=`<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${view.webview.cspSource}; script-src 'nonce-${nonce}';"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="${css}"></head><body><header><strong>D-bot / Lập trình</strong><small id="workspace">Chưa chọn thư mục</small></header><div class="actions"><button data-action="choose">Chọn thư mục</button><button data-action="project">Project mới</button><button data-action="markdown">Đọc Markdown</button></div><p id="status" role="status"></p><label>Model local<select id="model"></select></label><label>Yêu cầu<textarea id="task" rows="5" maxlength="12000" placeholder="Đọc README.md rồi sửa... Giữ nguyên phần không liên quan."></textarea></label><div class="actions"><button id="run" data-action="run">Đề xuất sửa</button><button id="explain" data-action="explain">Giải thích</button><button id="stop" data-action="stop">Dừng</button></div><small>Đọc file tự động; ghi khi Áp dụng. Task VS Code do bạn chọn mới được chạy.</small><pre id="answer"></pre><details><summary>Nhật ký thao tác</summary><pre id="events"></pre></details><section id="proposal" hidden><h3 id="batch-title"></h3><p id="batch-status"></p><div id="changes"></div><div class="actions"><button id="apply" data-action="apply">Áp dụng</button><button id="revert" data-action="revert">Khôi phục</button><button id="open-project" data-action="openProject">Mở project mới</button></div></section><details><summary>File trong workspace</summary><div id="files"></div></details><div class="actions"><button data-action="refresh">Tải lại</button><button data-action="runTask">Chọn task để chạy</button></div><script nonce="${nonce}" src="${script}"></script></body></html>`
    this.context.subscriptions.push(view.webview.onDidReceiveMessage(async message=>{try{await this.message(message)}catch(error){this.report(error)}}))
    view.onDidDispose(()=>{void this.stop();this.view=undefined})
    void this.refresh().catch(error=>this.report(error));this.render()
  }
  private report(error:unknown){const text=error instanceof Error?error.message:String(error);this.stage=text;this.output.appendLine(text);this.render();void vscode.window.showErrorMessage('D-bot: '+text)}
  private render(){void this.view?.webview.postMessage({type:'state',workspace:this.workspace?.root||'',model:this.model,models:[...new Set([this.model,...this.models])],files:this.files,events:this.events,answer:this.answer,stage:this.stage,busy:this.busy,batch:this.batch,taskDraft:this.taskDraft});this.taskDraft=undefined}
  async show(){await vscode.commands.executeCommand('dbot.assistant.focus')}
  async refresh(){this.client=this.makeClient();const state=await this.client.request('/coding/status');this.models=state.models;if(this.workspace){const tree=await this.client.request(`/coding/workspaces/${this.workspace.id}/files`);this.files=tree.files.map((f:any)=>f.path)}this.stage=this.workspace?'Sẵn sàng. File chưa lưu cần được lưu trước khi sửa.':'Chọn thư mục để đọc/sửa file.';this.render()}
  private async use(uri:vscode.Uri){
    this.trusted();if(uri.scheme!=='file')throw new Error('Bản này hỗ trợ workspace local, không hỗ trợ WSL/SSH/virtual filesystem.')
    if(this.busy)throw new Error('Dừng tác vụ hiện tại trước khi đổi workspace.')
    const row=await this.client.request('/coding/workspaces',{method:'POST',body:JSON.stringify({root:uri.fsPath,name:path.basename(uri.fsPath)})})
    this.workspace={id:row.id,root:uri.fsPath,name:row.name};this.batch=null;this.answer='';this.events=[];await this.refresh()
  }
  async choose(){const roots=vscode.workspace.workspaceFolders?.filter(w=>w.uri.scheme==='file')||[]
    if(roots.length){const choice=await vscode.window.showQuickPick([...roots.map(w=>({label:w.name,description:w.uri.fsPath,uri:w.uri})),{label:'Chọn thư mục khác…',description:'',uri:undefined}],{placeHolder:'Thư mục D-bot được đọc và áp dụng bản sửa'});if(!choice)return;if(choice.uri){await this.use(choice.uri);return}}
    const selected=await vscode.window.showOpenDialog({canSelectFolders:true,canSelectFiles:false,canSelectMany:false,openLabel:'Dùng thư mục này'});if(selected?.[0])await this.use(selected[0])
  }
  private async ensure(editor?:vscode.TextEditor){this.trusted();if(this.workspace)return;if(editor){const folder=vscode.workspace.getWorkspaceFolder(editor.document.uri);if(folder?.uri.scheme==='file'){await this.use(folder.uri);return}}await this.choose();if(!this.workspace)throw new Error('Chưa chọn workspace')}
  private relative(uri:vscode.Uri){if(uri.scheme!=='file'||!this.workspace)throw new Error('Cần file local trong workspace đã chọn');return safeRelative(path.relative(this.workspace.root,uri.fsPath).split(path.sep).join('/'))}
  async run(task:string,mode:'edit'|'explain'='edit',editor?:vscode.TextEditor){
    if(this.busy)return
    await this.ensure(editor)
    if(!task.trim())throw new Error('Yêu cầu đang trống')
    if(mode==='edit'&&editor?.document.isDirty)throw new Error('Lưu file trong VS Code trước khi tạo bản sửa; D-bot dùng hash trên đĩa.')
    let active_path='',selection=''
    if(editor?.document.uri.scheme==='file'){active_path=this.relative(editor.document.uri);selection=editor.selection.isEmpty?'':editor.document.getText(editor.selection);if(selection.length>6000)throw new Error('Chọn đoạn ngắn hơn 6000 ký tự để vừa context model local.')}
    this.busy=true;this.batch=null;this.answer='';this.events=[];this.stage='Đang kết nối model local';this.taskDraft=task;this.render();this.requestId=randomUUID();this.controller=new AbortController()
    try{
      await this.client.stream({workspace_id:this.workspace!.id,request_id:this.requestId,task,model:this.model,mode,active_path,selection},event=>{
        if(event.run_id!==this.requestId)return
        if(event.type==='status')this.stage=event.detail
        if(event.type==='progress')this.stage=`Bước ${event.step}/6 · ${event.elapsed_seconds}s · ${event.generated_chunks} phần đầu ra`
        if(event.type==='tool_result')this.events.push(`${event.tool}: ${event.path||event.query||''}${event.detail?' | '+event.detail:''}${event.start_line?` · dòng ${event.start_line}–${event.end_line}/${event.total_lines}`:''}`)
        if(event.type==='decision')this.events.push(`${event.action}: ${event.summary}`)
        if(event.type==='proposal')this.batch=event.batch
        if(event.type==='done'){this.answer=event.answer||'';this.stage=(event.status==='proposed'?'Đã có diff; chưa ghi file.':'Đã hoàn tất.')+` · ${event.elapsed_seconds}s · ${event.metrics?.model_rounds??'?'} lượt model`}
        if(event.type==='error')throw new Error(event.message)
        this.render()
      },this.controller.signal)
    }catch(error){if((error as Error).name==='AbortError')this.stage='Đã yêu cầu dừng; có thể xem lại lịch sử tác vụ trong D-bot.';else{this.stage=(error as Error).message;throw error}}
    finally{this.busy=false;this.requestId='';this.controller=undefined;this.render()}
  }
  async stop(){this.controller?.abort();if(this.requestId)await this.client.request(`/coding/tasks/${encodeURIComponent(this.requestId)}/cancel`,{method:'POST'}).catch(()=>{})}
  async editFile(){const editor=vscode.window.activeTextEditor;if(!editor||editor.document.uri.scheme!=='file')throw new Error('Mở file local cần sửa trước.');const task=await vscode.window.showInputBox({prompt:'Yêu cầu sửa file/vùng chọn',placeHolder:'Ví dụ: bổ sung xử lý đầu vào rỗng, giữ nguyên API'});if(task?.trim()){await this.show();await this.run(task,'edit',editor)}}
  async explainSelection(){const editor=vscode.window.activeTextEditor;if(!editor)throw new Error('Mở file hoặc chọn đoạn cần giải thích.');await this.show();await this.run('Giải thích ngắn gọn file hoặc vùng chọn: mục đích, luồng xử lý và điểm cần chú ý. Chỉ đọc, không sửa file.','explain',editor)}
  async readMarkdown(){await this.ensure();const selected=await vscode.window.showOpenDialog({canSelectFiles:true,canSelectFolders:false,canSelectMany:false,defaultUri:vscode.Uri.file(this.workspace!.root),filters:{Markdown:['md','markdown','mdx']}});if(!selected?.[0])return;const relative=this.relative(selected[0]);await this.client.request(`/coding/workspaces/${this.workspace!.id}/read`,{method:'POST',body:JSON.stringify({path:relative,lines:1})});await vscode.window.showTextDocument(selected[0]);if(/\.(md|markdown)$/i.test(selected[0].path))await vscode.commands.executeCommand('markdown.showPreview',selected[0])}
  async newProject(){this.trusted();if(this.busy)throw new Error('Dừng tác vụ hiện tại trước.');const parent=await vscode.window.showOpenDialog({canSelectFolders:true,canSelectFiles:false,canSelectMany:false,openLabel:'Chọn thư mục cha chứa project mới'});if(!parent?.[0])return;await this.use(parent[0]);const templates=await this.client.request('/coding/templates');const selected=await vscode.window.showQuickPick(templates.map((t:any)=>({label:t.name,description:t.description,id:t.id})) as {label:string;description:string;id:string}[],{placeHolder:'Mẫu project (chưa cài dependency/chạy lệnh)'});if(!selected)return;const name=await vscode.window.showInputBox({prompt:'Tên thư mục project mới',value:'my-project',validateInput:value=>/^[a-z][a-z0-9-]{0,47}$/.test(value)?null:'Dùng chữ thường, số và dấu -, bắt đầu bằng chữ.'});if(!name)return;this.batch=await this.client.request(`/coding/workspaces/${this.workspace!.id}/projects`,{method:'POST',body:JSON.stringify({name,template:selected.id})});this.stage='Đã có cấu trúc project; xem diff rồi Áp dụng.';await this.show();this.render()}
  private async diff(index:number){if(!this.batch||!Number.isInteger(index)||!this.batch.files[index])throw new Error('Không có file đề xuất');const f=this.batch.files[index];safeRelative(f.path);const before=this.previews.add(`${this.batch.id}/${index}/before`,f.old_content),after=this.previews.add(`${this.batch.id}/${index}/after`,f.content);await vscode.commands.executeCommand('vscode.diff',before,after,`${f.path} · D-bot (${this.batch.status})`)}
  private async apply(revert=false){
    this.trusted();if(!this.workspace||!this.batch||this.busy)return
    if(this.batch.workspace_id!==this.workspace.id)throw new Error('Bản sửa thuộc workspace khác')
    for(const file of this.batch.files){const uri=vscode.Uri.file(withinRoot(this.workspace.root,file.path));const doc=vscode.workspace.textDocuments.find(d=>d.uri.toString()===uri.toString());if(doc?.isDirty)throw new Error(`File chưa lưu: ${file.path}. Lưu/giải quyết buffer trước khi áp dụng hoặc khôi phục.`)}
    this.busy=true;this.render()
    try{this.batch=await this.client.request(`/coding/batches/${this.batch.id}/${revert?'revert':'apply'}`,{method:'POST'});for(const file of this.batch.files){const uri=vscode.Uri.file(withinRoot(this.workspace.root,file.path));if(revert&&!file.before_hash)continue;const raw=await vscode.workspace.fs.readFile(uri);const expected=revert?file.before_hash:file.after_hash;if(createHash('sha256').update(raw).digest('hex')!==expected)throw new Error('File vừa thay đổi sau thao tác; kiểm tra lại: '+file.path)}this.stage=revert?'Đã khôi phục bản trước.':'Đã ghi file thật; chưa chạy test/cài dependency.';this.files=(await this.client.request(`/coding/workspaces/${this.workspace.id}/files`)).files.map((f:any)=>f.path)}finally{this.busy=false;this.render()}
  }
  async runTask(){this.trusted();await this.ensure();const tasks=(await vscode.tasks.fetchTasks()).filter(t=>t.scope===vscode.TaskScope.Workspace||(typeof t.scope==='object'&&t.scope.uri.fsPath===this.workspace!.root));if(!tasks.length){void vscode.window.showInformationMessage('Không có task trong workspace. Tạo/chọn task bằng VS Code; D-bot không tự chạy shell.');return}const chosen=await vscode.window.showQuickPick(tasks.map(task=>({label:task.name,description:task.source,task})),{placeHolder:'Chọn đúng task để chạy trong workspace tin cậy'});if(chosen){await vscode.tasks.executeTask(chosen.task);this.output.appendLine('Đã yêu cầu VS Code chạy task: '+chosen.task.name);this.stage='Task đã được khởi chạy trong VS Code; xem Terminal để biết kết quả.';this.render()}}
  private async message(message:any){
    if(!message||typeof message.type!=='string')return
    switch(message.type){
      case 'ready':this.render();break
      case 'choose':await this.choose();break
      case 'refresh':await this.refresh();break
      case 'model':if(typeof message.value==='string'&&/^[a-zA-Z0-9_.:-]{1,120}$/.test(message.value)&&!message.value.includes('cloud')){this.model=message.value;this.render()}break
      case 'run':case 'explain':if(typeof message.task==='string')await this.run(message.task,message.type==='explain'?'explain':'edit',vscode.window.activeTextEditor);break
      case 'stop':await this.stop();break
      case 'project':await this.newProject();break
      case 'markdown':await this.readMarkdown();break
      case 'diff':await this.diff(message.index);break
      case 'apply':await this.apply();break
      case 'revert':await this.apply(true);break
      case 'runTask':await this.runTask();break
      case 'file':if(this.workspace&&typeof message.path==='string'){const target=withinRoot(this.workspace.root,message.path);await this.client.request(`/coding/workspaces/${this.workspace.id}/read`,{method:'POST',body:JSON.stringify({path:message.path,lines:1})});await vscode.window.showTextDocument(vscode.Uri.file(target))}break
      case 'openProject':if(this.workspace&&this.batch?.source==='template'&&this.batch.status==='applied'){const first=this.batch.files[0].path.split('/')[0];await vscode.commands.executeCommand('vscode.openFolder',vscode.Uri.file(withinRoot(this.workspace.root,first)),true)}break
    }
  }
  dispose(){void this.stop()}
}

export function activate(context:vscode.ExtensionContext){
  const previews=new PreviewDocuments(),output=vscode.window.createOutputChannel('D-bot Assistant'),assistant=new Assistant(context,previews,output)
  context.subscriptions.push(output,assistant,vscode.workspace.registerTextDocumentContentProvider('dbot-preview',previews),vscode.window.registerWebviewViewProvider('dbot.assistant',assistant))
  const commands:Record<string,()=>Promise<void>>={'dbot.open':()=>assistant.show(),'dbot.editFile':()=>assistant.editFile(),'dbot.explainSelection':()=>assistant.explainSelection(),'dbot.readMarkdown':()=>assistant.readMarkdown(),'dbot.newProject':()=>assistant.newProject(),'dbot.runTask':()=>assistant.runTask()}
  for(const [name,run] of Object.entries(commands))context.subscriptions.push(vscode.commands.registerCommand(name,async()=>{try{await run()}catch(error){void vscode.window.showErrorMessage('D-bot: '+(error as Error).message)}}))
}
export function deactivate(){}
