const path=require('node:path'),{execFile}=require('node:child_process')
const {resolveApp}=require('./commands.cjs')
class AppResolver{
  constructor(root,{scan=null,now=Date.now}={}){this.root=root;this.rows=[];this.checked=0;this.pending=null;this.now=now;this.scan=scan||(()=>new Promise((resolve,reject)=>execFile('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',path.join(__dirname,'installed-apps.ps1')],{windowsHide:true,encoding:'utf8',timeout:30000,maxBuffer:2*1024*1024},(error,stdout)=>{if(error)return reject(error);try{const parsed=JSON.parse(stdout.replace(/^\uFEFF/,''));resolve(Array.isArray(parsed)?parsed:[parsed])}catch(e){reject(e)}})))}
  async refresh(){if(this.pending)return this.pending;this.pending=this.scan().then(rows=>{this.rows=rows;this.checked=this.now();return rows}).finally(()=>this.pending=null);return this.pending}
  async resolve(id){
    try{return resolveApp(id,this.root,process.env,this.rows)}catch{}
    if(!this.checked||this.now()-this.checked>300000){try{await this.refresh()}catch(error){error.code='INVENTORY_UNAVAILABLE';throw error}}
    return resolveApp(id,this.root,process.env,this.rows)
  }
}
module.exports={AppResolver}
