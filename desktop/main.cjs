const {app,BrowserWindow,Tray,Menu,nativeImage,ipcMain,screen,shell,dialog,session,globalShortcut}=require('electron')
const fs=require('node:fs'),path=require('node:path'),{pathToFileURL}=require('node:url'),{spawn}=require('node:child_process'),crypto=require('node:crypto')
const {parseCommand,safeURL,resolveApp,clampBounds}=require('./commands.cjs')
const {DesktopDialogue}=require('./dialogue.cjs'),{AppResolver}=require('./app-resolver.cjs')
const {Companion}=require('./companion.cjs')
let root=__dirname
for(let i=0;i<7&&!fs.existsSync(path.join(root,'backend','app','main.py'));i++)root=path.dirname(root)
if(!fs.existsSync(path.join(root,'scripts','start.ps1')))throw new Error('Đặt D-bot Desktop trong thư mục dự án D-bot đã cài đặt.')
const data=path.join(root,'data','desktop');fs.mkdirSync(data,{recursive:true})
app.setPath('userData',path.join(data,'profile'));app.setPath('logs',path.join(root,'data','logs'));app.setPath('crashDumps',path.join(data,'crashes'))
app.setAppUserModelId('blueDStar.Dbot.Assistant')
const envText=fs.readFileSync(path.join(root,'.env'),'utf8'),port=Number(envText.match(/^DBOT_PORT=(\d+)\s*$/m)?.[1]||8008),base=`http://127.0.0.1:${port}`
const petBaseURL=pathToFileURL(path.join(__dirname,'pet.html')).href,petURL=petBaseURL+'?surface=pet',chatURL=petBaseURL+'?surface=chat'
const settingsPath=path.join(data,'settings.json')
let settings={roaming:true,petVisible:true,position:null,voiceSpeed:0.85,clickThrough:true},main,pet,quickChat,companion,splash,tray,quitting=false,panel=false,token='',backendOwned=false,ollamaOwned=false,controller=null,requestId=null,conversationId=null,shortcutReady=false
try{settings={...settings,...JSON.parse(fs.readFileSync(settingsPath,'utf8'))}}catch{}
if(!Number.isFinite(settings.voiceSpeed)||settings.voiceSpeed<0.65||settings.voiceSpeed>1.2)settings.voiceSpeed=0.85
const resolver=new AppResolver(root),dialogue=new DesktopDialogue({resolve:id=>resolver.resolve(id),execute}),speechCache=new Map(),speechPending=new Map()
let preparingVoice=null,voicePreparedAt=0
function save(){fs.writeFileSync(settingsPath,JSON.stringify(settings,null,2))}
function log(text){fs.appendFileSync(path.join(root,'data','logs','desktop.log'),new Date().toISOString()+' '+text+'\n')}
function runtimeStatus(){fs.writeFileSync(path.join(data,'runtime-status.json'),JSON.stringify({pid:process.pid,...snapshot(),main_loaded:main?.webContents.getURL()===base+'/',pet_loaded:pet?.webContents.getURL()===petURL,chat_loaded:quickChat?.webContents.getURL()===chatURL,pet_bounds:pet?.getBounds(),tray_ready:!!tray,security:{nodeIntegration:false,contextIsolation:true,sandbox:true},checked_at:new Date().toISOString()},null,2))}
function mainURL(url){return url===base+'/'||url?.startsWith(base+'/#')}
function trusted(event,petOnly=false){const win=BrowserWindow.fromWebContents(event.sender);const url=event.senderFrame?.url;if(event.senderFrame!==event.sender.mainFrame||!([main,pet,quickChat].includes(win))||(petOnly&&win!==pet&&win!==quickChat)||!((win===pet&&url===petURL)||(win===quickChat&&url===chatURL)||(win===main&&mainURL(url))))throw new Error('IPC ngoài cửa sổ D-bot bị từ chối')}
function snapshot(){return {version:app.getVersion(),roaming:settings.roaming,petVisible:settings.petVisible,clickThrough:settings.clickThrough,petMood:companion?.mood()||'idle',direction:companion?.direction||1,shortcutReady,voiceSpeed:settings.voiceSpeed,panel,mainVisible:!!main?.isVisible(),busy:!!controller,backend:base}}
function notify(){for(const win of [pet,quickChat,main])if(win&&!win.isDestroyed())win.webContents.send('desktop:state-update',snapshot())}
function windowSecurity(win){
  win.webContents.on('preload-error',(_event,_path,error)=>log('Preload error: '+error.message))
  win.webContents.on('did-fail-load',(_event,code,description)=>log('Load failed '+code+' '+description))
  win.webContents.on('render-process-gone',(_event,details)=>log('Renderer exited '+details.reason))
  win.webContents.setWindowOpenHandler(({url})=>{
    const cv=url.match(new RegExp('^'+base.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'/api/careers/cv/(en|vi)$'))
    if(cv){(async()=>{const response=await api('/careers/cv/'+cv[1]);if(!response.headers.get('content-type')?.includes('application/pdf'))throw new Error('CV cần là PDF');const folder=path.join(data,'downloads');fs.mkdirSync(folder,{recursive:true});const file=path.join(folder,'Nguyen_Van_Dat_CV_'+cv[1]+'.pdf');fs.writeFileSync(file,Buffer.from(await response.arrayBuffer()));const error=await shell.openPath(file);if(error)throw new Error(error)})().catch(e=>log(e.message))}
    else{try{shell.openExternal(safeURL(url)).catch(e=>log(e.message))}catch{}}
    return {action:'deny'}
  })
  win.webContents.on('will-navigate',(event,url)=>{if(!mainURL(url)&&url!==petURL&&url!==chatURL){event.preventDefault()}})
  win.webContents.on('will-attach-webview',event=>event.preventDefault())
}
async function healthy(){try{const result=await(await fetch(base+'/api/session',{signal:AbortSignal.timeout(10000)})).json();return typeof result.token==='string'&&result.token.length>=16}catch{return false}}
async function backend(){
  if(await healthy())return
  try{await fetch('http://127.0.0.1:11434/api/version',{signal:AbortSignal.timeout(2000)})}catch{ollamaOwned=true}
  backendOwned=true
  await new Promise((resolve,reject)=>{const child=spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',path.join(root,'scripts','start.ps1')],{cwd:root,windowsHide:true,stdio:'ignore'});child.on('error',reject);let tries=0;const timer=setInterval(async()=>{if(await healthy()){clearInterval(timer);resolve()}else if(++tries>80){clearInterval(timer);reject(new Error('Backend chưa khởi động. Xem data/logs/backend.err.log.'))}},750)})
}
async function api(route,options={}){
  if(!token)token=(await(await fetch(base+'/api/session')).json()).token
  const request=()=>fetch(base+'/api'+route,{...options,headers:{'X-D-Bot-Token':token,...options.headers}})
  let response=await request()
  if(response.status===403){token=(await(await fetch(base+'/api/session')).json()).token;response=await request()}
  if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(typeof body.detail==='string'?body.detail:'Backend HTTP '+response.status)}
  return response
}
function makePet(){
  companion=new Companion({BrowserWindow,screen,directory:__dirname,settings,save,log,secure:windowSecurity,onChange:()=>{if(!companion)return;const closing=panel&&!companion.panel;panel=companion.panel;if(closing)dialogue.cancel();notify();runtimeStatus()}})
  pet=companion.pet;quickChat=companion.chat;companion.load(__dirname);save()
}
function showMain(){if(main&&!main.isDestroyed()){if(main.isMinimized())main.restore();main.show();main.focus()}notify()}
function setPanel(value){companion.setPanel(!!value)}
function makeMain(){
  main=new BrowserWindow({width:1320,height:900,minWidth:860,minHeight:620,show:false,title:'D-bot Assistant',icon:path.join(__dirname,'icon.png'),backgroundColor:'#0b0b0b',autoHideMenuBar:true,webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true}})
  windowSecurity(main)
  main.on('close',event=>{if(!quitting){event.preventDefault();main.hide();companion.visible(true)}})
  main.on('show',notify);main.on('hide',notify)
  main.loadURL(base+'/');main.once('ready-to-show',()=>{splash?.destroy();splash=null;if(!process.argv.includes('--background'))showMain();runtimeStatus()})
}
function makeTray(){
  const png=fs.readFileSync(path.join(__dirname,'icon.png'));tray=new Tray(nativeImage.createFromBuffer(png).resize({width:24,height:24}));tray.setToolTip('D-bot · trợ lý Robotics / AI');tray.on('double-click',showMain);refreshMenu()
}
function refreshMenu(){if(!tray)return;tray.setContextMenu(Menu.buildFromTemplate([
  {label:'Trò chuyện nhanh · Ctrl+Alt+D',click:()=>setPanel(!panel)},
  {label:'Mở D-bot Assistant',click:showMain},
  {label:'Trợ lý nổi',type:'checkbox',checked:settings.petVisible,click:item=>{companion.visible(item.checked);refreshMenu()}},
  {label:'Xuyên chuột toàn bộ (không cản nhấp/cuộn)',type:'checkbox',checked:settings.clickThrough,click:item=>{companion.setClickThrough(item.checked);refreshMenu()}},
  {label:'Đi qua lại trên màn hình',type:'checkbox',checked:settings.roaming,click:item=>{settings.roaming=item.checked;save();refreshMenu();notify()}},
  {type:'separator'},
  {label:'Mở thư mục dự án',click:()=>shell.openPath(root)},
  {label:'Thoát D-bot Desktop',click:()=>app.quit()},
]))}
async function execute(command,resolved=null){
  if(!command)return {handled:false}
  log('User desktop action: '+command.kind+(command.id?' '+command.id:command.url?' '+new URL(command.url).hostname:''))
  if(command.kind==='blocked')return {handled:true,message:command.message}
  if(command.kind==='show_main'){showMain();return {handled:true,message:'Đã mở cửa sổ D-bot.'}}
  if(command.kind==='hide_main'){main.hide();notify();return {handled:true,message:'Đã thu cửa sổ về trợ lý nổi.'}}
  if(command.kind==='roaming'){settings.roaming=command.enabled;save();refreshMenu();notify();return {handled:true,message:command.enabled?'Đã bật đi qua lại.':'Đã dừng di chuyển.'}}
  if(command.kind==='open_web'){await shell.openExternal(safeURL(command.url));return {handled:true,message:'Đã mở '+new URL(command.url).hostname+' trong trình duyệt.'}}
  if(command.kind==='open_app'){
    const target=resolved||await resolver.resolve(command.id)
    if(target.folder){const error=await shell.openPath(target.folder);if(error)throw new Error(error)}
    else{if(!fs.existsSync(target.exe))throw new Error('Chưa tìm thấy phần mềm.');await new Promise((resolve,reject)=>{const child=spawn(target.exe,target.args,{shell:false,detached:true,windowsHide:false,stdio:'ignore'});child.once('error',reject);child.once('spawn',()=>{child.unref();resolve()})})}
    return {handled:true,message:'Đã yêu cầu Windows mở '+command.id+'.'}
  }
  return {handled:false}
}
async function speechBytes(text,speed=settings.voiceSpeed){
  if(typeof text!=='string'||!text.trim()||text.length>4000||!Number.isFinite(speed)||speed<0.65||speed>1.2)throw new Error('Nội dung hoặc tốc độ giọng nói không hợp lệ')
  const key=speed+':'+text
  if(speechCache.has(key)){const bytes=speechCache.get(key);speechCache.delete(key);speechCache.set(key,bytes);return bytes}
  if(speechPending.has(key))return speechPending.get(key)
  const pending=(async()=>{const bytes=new Uint8Array(await(await api('/voice/synthesize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,speed})})).arrayBuffer());if(bytes.byteLength<1024*1024){speechCache.set(key,bytes);while(speechCache.size>12)speechCache.delete(speechCache.keys().next().value)}return bytes})().finally(()=>speechPending.delete(key))
  speechPending.set(key,pending);return pending
}
async function prepareVoice(){
  if(preparingVoice)return preparingVoice
  if(Date.now()-voicePreparedAt<90000)return {ready:true}
  preparingVoice=api('/voice/prepare',{method:'POST'}).then(()=>{voicePreparedAt=Date.now();return {ready:true}}).finally(()=>preparingVoice=null)
  return preparingVoice
}
async function desktopReply(text,context={}){
  const result=await dialogue.respond(text)
  if(result.handled){
    // Prepare fixed replies while the renderer displays them; no language model.
    speechBytes(result.message).catch(()=>{})
    try{
      const receipt=await(await api('/desktop/turn',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,answer:result.message,stage:result.stage,request_id:crypto.randomUUID(),project_id:context.project_id||'general',conversation_id:context.conversation_id||null,source:context.source==='voice'?'voice':'text',private:!!context.private})})).json()
      Object.assign(result,receipt)
    }catch(error){result.history_warning='Chưa ghi được lịch sử: '+error.message}
  }
  return result
}
function registerIPC(){
  const handle=(name,fn,petOnly=false)=>ipcMain.handle('desktop:'+name,(event,...args)=>{trusted(event,petOnly);return fn(...args)})
  handle('state',snapshot);handle('show',()=>{showMain();return snapshot()});handle('hide',()=>{main.hide();notify();return snapshot()})
  handle('toggle-pet',()=>{companion.visible(!settings.petVisible);refreshMenu();return snapshot()})
  handle('panel',value=>{setPanel(!!value);return snapshot()})
  handle('click-through',value=>{companion.setClickThrough(!!value);refreshMenu();return snapshot()})
  handle('pet-mood',value=>{companion.setMood(value);return snapshot()})
  handle('preview-mood',value=>{companion.preview(value);return snapshot()})
  handle('roaming',value=>{settings.roaming=!!value;save();refreshMenu();notify();return snapshot()})
  handle('menu',()=>tray.popUpContextMenu(),true)
  ipcMain.on('desktop:move',(event,{dx,dy}={})=>{trusted(event,true);companion.move(dx,dy)})
  handle('command',(text,context)=>desktopReply(text,context))
  handle('complete-action',async id=>{try{const receipt=await dialogue.complete(id);companion.setMood('happy');return receipt}catch(error){companion.setMood('error');throw error}})
  handle('cancel',()=>{dialogue.cancel();controller?.abort();if(requestId)api('/chat/'+requestId+'/cancel',{method:'POST'}).catch(()=>{});return {ok:true}})
  handle('prepare-voice',prepareVoice,true)
  handle('voice-speed',value=>{if(!Number.isFinite(value)||value<0.65||value>1.2)throw new Error('Tốc độ cần trong khoảng 0,65–1,2');settings.voiceSpeed=value;speechCache.clear();save();notify();return snapshot()})
  handle('transcribe',async(bytes,language)=>{if(!(bytes instanceof Uint8Array)&&!Array.isArray(bytes))throw new Error('Audio không hợp lệ');if(bytes.length>6*1024*1024)throw new Error('Audio quá dài');const form=new FormData();form.append('file',new Blob([new Uint8Array(bytes)],{type:'application/octet-stream'}),'speech.audio');form.append('context',dialogue.pending&&dialogue.pending.expires>Date.now()?'confirmation':'desktop');if(language!==undefined&&!['vi','en','ja','auto'].includes(language))throw new Error('Invalid transcription language');if(dialogue.pending&&dialogue.pending.expires>Date.now())form.append('language','vi');else if(language)form.append('language',language);return (await api('/voice/transcribe',{method:'POST',body:form})).json()})
  handle('speak',speechBytes)
  handle('ask',async(text,source='text')=>{
    if(typeof text!=='string'||!text.trim()||text.length>16000)throw new Error('Câu hỏi không hợp lệ')
    if(controller)throw new Error('D-bot đang trả lời. Bấm Dừng trước khi hỏi tiếp.')
    const handled=await desktopReply(text,{source,conversation_id:conversationId});if(handled.handled){if(handled.conversation_id)conversationId=handled.conversation_id;return handled}
    controller=new AbortController();requestId=crypto.randomUUID();notify()
    try{
      const response=await api('/chat',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:'general',conversation_id:conversationId,text,request_id:requestId,source:source==='voice'?'voice':'text',voice_conversation:true,performance:'fast',use_knowledge:false})})
      let answer='',status='error',buffer='';const decoder=new TextDecoder()
      for await(const chunk of response.body){buffer+=decoder.decode(chunk,{stream:true});const lines=buffer.split('\n');buffer=lines.pop();for(const line of lines){if(!line.trim())continue;const event=JSON.parse(line);if(event.type==='status'&&event.conversation_id)conversationId=event.conversation_id;if(event.type==='token'){answer+=event.text;quickChat.webContents.send('desktop:reply',{text:answer,request_id:requestId})}if(event.type==='replace')answer=event.text;if(event.type==='error')throw new Error(event.message);if(event.type==='done')status=event.status}}
      if(status!=='completed')throw new Error('Lượt trả lời chưa hoàn tất.')
      return {handled:true,message:answer,source:'local_assistant',saved_in_chat:true}
    }finally{controller=null;requestId=null;notify()}
  },true)
}
if(!app.requestSingleInstanceLock()||process.argv.includes('--quit')){app.quit()}else{
  app.on('second-instance',(_event,argv)=>{if(argv.includes('--quit'))app.quit();else showMain()})
  app.whenReady().then(async()=>{
    Menu.setApplicationMenu(null)
    session.defaultSession.setPermissionRequestHandler((contents,permission,callback,details)=>{const url=contents.getURL();callback(permission==='media'&&(url===chatURL||mainURL(url))&&!!details.mediaTypes?.length&&details.mediaTypes.every(t=>t==='audio'))})
    session.defaultSession.setPermissionCheckHandler((contents,permission,_origin,details)=>permission==='media'&&(contents?.getURL()===chatURL||mainURL(contents?.getURL()))&&details.mediaType==='audio')
    try{
      if(!process.argv.includes('--background')){splash=new BrowserWindow({width:440,height:330,frame:false,resizable:false,show:true,backgroundColor:'#0b0b0b',webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true}});splash.loadFile(path.join(__dirname,'splash.html'))}
      await backend();makePet();makeMain();makeTray();registerIPC()
      resolver.refresh().catch(error=>log('App inventory unavailable: '+error.message))
      shortcutReady=globalShortcut.register('CommandOrControl+Alt+D',()=>setPanel(!panel))
      if(!shortcutReady)log('Ctrl+Alt+D unavailable; use tray Quick chat')
      setInterval(()=>companion.tick(),80).unref()
      notify();runtimeStatus()
      log('Desktop ready '+app.getVersion())
    }catch(error){log(error.stack||error.message);dialog.showErrorBox('D-bot chưa mở được',error.message);app.quit()}
  })
  app.on('window-all-closed',()=>{})
  app.on('before-quit',()=>{quitting=true;globalShortcut.unregisterAll();controller?.abort();companion?.shutdown();save();if(backendOwned)fs.writeFileSync(path.join(root,'.runtime','stop-backend'),'desktop quit');if(ollamaOwned)fs.writeFileSync(path.join(root,'.runtime','stop-ollama'),'desktop quit');log('Desktop quit')})
}
