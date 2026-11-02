// Deterministic desktop actions. Model output and web pages never become commands.
const fs=require('node:fs'),path=require('node:path')
const SITES=Object.freeze({google:'https://www.google.com/',youtube:'https://www.youtube.com/',gmail:'https://mail.google.com/',calendar:'https://calendar.google.com/',portfolio:'https://bluedstar.id.vn/#/'})
const APPS=Object.freeze({
  powerpoint:{name:'PowerPoint',exe:'POWERPNT.EXE',aliases:['powerpoint','power point','power point presentation','microsoft powerpoint','pao poi','bao poi']},
  word:{name:'Word',exe:'WINWORD.EXE',aliases:['word','microsoft word','uot']},
  excel:{name:'Excel',exe:'EXCEL.EXE',aliases:['excel','microsoft excel','exel']},
  outlook:{name:'Outlook',exe:'OUTLOOK.EXE',aliases:['outlook','microsoft outlook']},
  vscode:{name:'VS Code',exe:'Code.exe',aliases:['vscode','vs code','visual studio code']},
  notepad:{name:'Notepad',exe:'notepad.exe',aliases:['notepad','ghi chu']},
  calculator:{name:'Máy tính',exe:'calc.exe',aliases:['may tinh','calculator','calc']},
  chrome:{name:'Google Chrome',exe:'chrome.exe',aliases:['chrome','google chrome']},
  edge:{name:'Microsoft Edge',exe:'msedge.exe',aliases:['edge','microsoft edge']},
  firefox:{name:'Firefox',exe:'firefox.exe',aliases:['firefox','mozilla firefox']},
  zalo:{name:'Zalo',exe:'Zalo.exe',aliases:['zalo']},
  zoom:{name:'Zoom',exe:'Zoom.exe',aliases:['zoom']},
  solidworks:{name:'SOLIDWORKS',exe:'SLDWORKS.exe',aliases:['solidworks','solid works']},
  labview:{name:'LabVIEW',exe:'LabVIEW.exe',aliases:['labview','lab view']},
})
const BLOCKED_APPS=/\b(cmd|powershell|pwsh|wscript|cscript|mshta|rundll32|regsvr32|python|node|taskkill|shutdown|installer|setup)\b/
function normalize(text){return text.toLowerCase().replace(/đ/g,'d').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[.!?,]+$/g,'').trim().replace(/\s+/g,' ')}
function safeURL(input){
  if(typeof input!=='string'||input.length>2000||/[\x00-\x20\\]/.test(input))throw new Error('Đường dẫn web không hợp lệ')
  const u=new URL(input)
  const host=u.hostname.replace(/\.$/,'')
  if(!['https:','http:'].includes(u.protocol)||u.username||u.password||!host||host==='localhost'||host.endsWith('.localhost')||host.endsWith('.local')||!host.includes('.')||/^\[|^\d+(\.\d+){0,3}$/.test(host))throw new Error('Chỉ mở website công khai qua HTTP/HTTPS')
  return u.href
}
function parseCommand(text){
  if(typeof text!=='string'||text.length>16000)return null
  let q=normalize(text).replace(/^(?:d-?bot|d bot|tro ly)(?: oi)?[, ]+/,'').replace(/^(?:ban )?(?:co the |toi muon |hay |vui long )/,'').replace(/^ban /,'')
  for(let n=0;n<3;n++)q=q.replace(/ (giup toi|cho toi|giup minh|cho minh|nhe|nha|di|len|duoc khong|khong)$/,'')
  if(/^mo (rong|ta|dau|khoa)\b/.test(q))return null
  if(/^(mo|bat|hien|mo lai) (d-?bot|d bot|ung dung|phan mem|cua so chinh)( assistant)?( len)?$/.test(q))return {kind:'show_main'}
  if(/^(an|thu nho|dong cua so) (d-?bot|d bot|ung dung|phan mem|cua so chinh)$/.test(q))return {kind:'hide_main'}
  if(/^(dung|tat) (di chuyen|chay qua lai)$/.test(q))return {kind:'roaming',enabled:false}
  if(/^(bat|tiep tuc) (di chuyen|chay qua lai)$/.test(q))return {kind:'roaming',enabled:true}
  const url=text.trim().match(/^(?:mở|mo|open)\s+(?:web\s+)?(https?:\/\/\S+)\s*$/i)
  if(url){try{return {kind:'open_web',url:safeURL(url[1])}}catch{return {kind:'blocked',message:'Chỉ mở địa chỉ website công khai HTTP/HTTPS hợp lệ.'}}}
  const aliases={'trinh duyet':'google','google':'google','youtube':'youtube','gmail':'gmail','lich':'calendar','google calendar':'calendar','calendar':'calendar','portfolio':'portfolio','ho so':'portfolio'}
  const open=q.match(/^(?:mo|bat|khoi dong) (?:(?:phan mem|ung dung) )?(.+)$/)
  if(open){
    if(aliases[open[1]])return {kind:'open_web',url:SITES[aliases[open[1]]]}
    if(['thu muc du an','folder du an'].includes(open[1]))return {kind:'open_app',id:'workspace'}
    if(BLOCKED_APPS.test(open[1])||!/^[a-z0-9][a-z0-9 .+-]{0,79}$/.test(open[1])||open[1].includes('..'))return {kind:'blocked',message:'Mình chỉ mở ứng dụng đã cài, không chạy dòng lệnh hoặc script.'}
    for(const [id,info] of Object.entries(APPS))if(info.aliases.includes(open[1]))return {kind:'open_app',id}
    // A name is looked up in the installed-app inventory, never used as a path/command.
    return {kind:'open_app',id:'installed:'+open[1],name:open[1]}
  }
  return null
}
function resolveApp(id,root,env=process.env,inventory=[]){
  const system=path.join(env.SystemRoot||'C:\\Windows','System32')
  if(id==='notepad'||id==='calculator')return {exe:path.join(system,id==='notepad'?'notepad.exe':'calc.exe'),args:[]}
  if(id==='workspace')return {folder:root}
  if(id==='vscode'){
    const candidates=[path.join(env.LOCALAPPDATA||'','Programs','Microsoft VS Code','Code.exe'),path.join(env.ProgramFiles||'C:\\Program Files','Microsoft VS Code','Code.exe')]
    const exe=candidates.find(p=>fs.existsSync(p));if(exe)return {exe,args:[root]}
  }
  const info=APPS[id]
  if(['powerpoint','word','excel','outlook'].includes(id)){
    for(const dir of [env.ProgramFiles||'C:\\Program Files',env['ProgramFiles(x86)']||'C:\\Program Files (x86)'])
      for(const version of ['root/Office16','Office16','Office15','Office14']){
        const exe=path.join(dir,'Microsoft Office',version,info.exe);if(fs.existsSync(exe))return {exe,args:[]}
      }
  }
  const wanted=id.startsWith('installed:')?id.slice(10):id
  const candidates=inventory.filter(row=>row&&typeof row.name==='string'&&typeof row.exe==='string'&&path.isAbsolute(row.exe)&&/\.exe$/i.test(row.exe)&&!/[\\/]windows[\\/]installer[\\/]/i.test(row.exe)&&!BLOCKED_APPS.test(path.basename(row.exe,'.exe').toLowerCase())&&fs.existsSync(row.exe))
  const found=candidates.find(row=>info?path.basename(row.exe).toLowerCase()===info.exe.toLowerCase()||[id,...info.aliases].includes(normalize(row.name)):normalize(row.name)===wanted||normalize(path.basename(row.exe,'.exe'))===wanted)
  if(found)return {exe:found.exe,args:[]}
  const versionMatches=candidates.filter(row=>normalize(row.name).startsWith(wanted+' ')&&/^(?:20\d{2}|\d{1,2}|x64|x86)\b/.test(normalize(row.name).slice(wanted.length+1)))
  if(versionMatches.length===1)return {exe:versionMatches[0].exe,args:[]}
  throw new Error((info?.name||wanted)+' chưa được cài đặt hoặc chưa có mục ứng dụng hợp lệ trên máy.')
}
function clampBounds(bounds,area){return {...bounds,x:Math.round(Math.max(area.x,Math.min(bounds.x,area.x+area.width-bounds.width))),y:Math.round(Math.max(area.y,Math.min(bounds.y,area.y+area.height-bounds.height)))}}
module.exports={parseCommand,safeURL,resolveApp,clampBounds,normalize,SITES,APPS}
