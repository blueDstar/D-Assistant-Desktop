const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto')
const {spawnSync}=require('node:child_process')
const root=path.resolve(__dirname,'..'),source=path.join(root,'desktop'),electron=path.join(source,'node_modules','electron','dist'),release=path.join(root,'artifacts','D-bot-Desktop')
if(!fs.existsSync(path.join(electron,'electron.exe')))throw new Error('Install desktop dependencies first')
fs.mkdirSync(release,{recursive:true})
// Copy/update only the dedicated release tree; never delete user data.
fs.cpSync(electron,release,{recursive:true})
const exe=path.join(release,'D-bot.exe'),upstream=path.join(release,'electron.exe')
fs.copyFileSync(upstream,exe);fs.unlinkSync(upstream)
const app=path.join(release,'resources','app');fs.mkdirSync(app,{recursive:true})
require('./build_pet_moods.cjs')
require('./build_voice_detector.cjs')
const files=fs.readdirSync(source).filter(name=>/\.(cjs|js|html|css|svg|png|ico|ps1)$/.test(name)||name==='package.json')
files.push(...fs.readdirSync(path.join(source,'expressions')).filter(name=>name.endsWith('.svg')).map(name=>'expressions/'+name))
for(const name of files){fs.mkdirSync(path.dirname(path.join(app,name)),{recursive:true});fs.copyFileSync(path.join(source,name),path.join(app,name))}
if(process.platform==='win32'){
  // Read/execute for Windows app sandboxes, on packaged code only. User data
  // and the backend workspace are deliberately outside this permission change.
  const existing=spawnSync('icacls.exe',[release],{windowsHide:true,encoding:'utf8'})
  if(!/(ALL APPLICATION PACKAGES|S-1-15-2-1):[^\r\n]*\([^\r\n]*RX/.test(existing.stdout||'')){
    const acl=spawnSync('icacls.exe',[release,'/grant','*S-1-15-2-1:(OI)(CI)(RX)'],{windowsHide:true,encoding:'utf8'})
    if(acl.status!==0)throw new Error('Cannot grant sandbox access on release directory: '+acl.stderr)
  }
}
const file_hashes=Object.fromEntries(files.map(name=>[name,crypto.createHash('sha256').update(fs.readFileSync(path.join(app,name))).digest('hex')]))
const manifest={version:JSON.parse(fs.readFileSync(path.join(source,'package.json'))).version,electron:fs.readFileSync(path.join(electron,'version'),'utf8').trim(),built_at:new Date().toISOString(),workspace:root,exe_sha256:crypto.createHash('sha256').update(fs.readFileSync(exe)).digest('hex'),files,file_hashes}
fs.writeFileSync(path.join(release,'build-manifest.json'),JSON.stringify(manifest,null,2))
console.log(JSON.stringify({exe,version:manifest.version,electron:manifest.electron,files:files.length}))
