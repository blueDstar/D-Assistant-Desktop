const path=require('node:path')
const {SIZE,fit,bounce,chatPlacement,robotShape}=require('./pet-geometry.cjs')
const MOODS=new Set(['idle','walking','greeting','listening','thinking','speaking','question','happy','error','sleeping'])
class Companion{
  constructor({BrowserWindow,screen,directory,settings,save,onChange,secure,log,now=Date.now}){
    Object.assign(this,{screen,settings,save,onChange,log,now});this.panel=false;this.direction=1;this.pauseUntil=0;this.activity='idle';this.flash=null;this.lastActivity=now();this.dragging=false;this.ignoring=null;this.quitting=false
    if(typeof settings.clickThrough!=='boolean')settings.clickThrough=true
    const old=settings.position,valid=old&&Number.isFinite(old.x)&&Number.isFinite(old.y),area=valid?screen.getDisplayMatching({x:old.x,y:old.y,...SIZE}).workArea:screen.getPrimaryDisplay().workArea
    const initial=fit({x:valid?old.x:area.x+area.width-SIZE.width-22,y:valid?old.y:area.y+area.height-SIZE.height-10,...SIZE},area)
    const webPreferences={preload:path.join(directory,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true}
    this.pet=new BrowserWindow({...initial,show:false,transparent:true,frame:false,thickFrame:false,hasShadow:false,resizable:false,maximizable:false,minimizable:false,fullscreenable:false,maxWidth:SIZE.width,maxHeight:SIZE.height,focusable:false,alwaysOnTop:true,skipTaskbar:true,backgroundColor:'#00000000',webPreferences:{...webPreferences,backgroundThrottling:false}})
    // The chat is an ordinary, fully painted window. It cannot enlarge the
    // transparent robot's input surface or stay above the user's other apps.
    this.chat=new BrowserWindow({...chatPlacement(initial,area),minWidth:Math.min(340,area.width),minHeight:Math.min(360,area.height),show:false,frame:false,thickFrame:false,transparent:false,resizable:false,maximizable:false,minimizable:false,alwaysOnTop:false,skipTaskbar:true,backgroundColor:'#141414',webPreferences})
    secure(this.pet);secure(this.chat);this.applyShape();this.applyInput()
    this.pet.once('ready-to-show',()=>{this.normalizeSize();if(settings.petVisible)this.pet.showInactive();this.onChange()})
    this.chat.once('ready-to-show',()=>this.onChange())
    this.pet.on('close',event=>{if(!this.quitting){event.preventDefault();this.visible(false)}})
    this.chat.on('close',event=>{if(!this.quitting){event.preventDefault();this.setPanel(false)}})
    this.chat.on('hide',()=>{if(this.panel){this.panel=false;this.onChange()}})
    this.screen.on('display-removed',()=>this.refit());this.screen.on('display-metrics-changed',()=>this.refit())
    this.preview('greeting',2500)
  }
  load(directory){this.pet.loadFile(path.join(directory,'pet.html'),{query:{surface:'pet'}});this.chat.loadFile(path.join(directory,'pet.html'),{query:{surface:'chat'}})}
  applyShape(){try{this.pet.setShape(robotShape())}catch(error){this.log('Native robot shape unavailable: '+error.message)}}
  applyInput(){
    const ignore=this.settings.clickThrough
    if(this.ignoring!==ignore){this.pet.setIgnoreMouseEvents(ignore,{forward:false});this.ignoring=ignore}
  }
  setClickThrough(value){this.settings.clickThrough=!!value;this.applyInput();this.save();this.onChange()}
  visible(value){this.settings.petVisible=!!value;if(value)this.pet.showInactive();else{this.pet.hide();this.setPanel(false)}this.save();this.onChange()}
  setPanel(value){
    this.panel=!!value;this.lastActivity=this.now()
    if(this.panel){const bounds=this.pet.getBounds(),area=this.screen.getDisplayMatching(bounds).workArea;this.chat.setBounds(chatPlacement(bounds,area));this.chat.show();this.chat.focus()}
    else this.chat.hide()
    this.onChange()
  }
  mood(){if(this.flash&&this.flash.until>this.now())return this.flash.name;this.flash=null;if(this.activity!=='idle')return this.activity;if(!this.settings.roaming&&!this.panel&&this.now()-this.lastActivity>45000)return 'sleeping';return this.settings.roaming&&!this.panel?'walking':'idle'}
  setMood(name){if(!MOODS.has(name))throw new Error('Biểu cảm không hợp lệ');this.activity=['happy','error','greeting'].includes(name)?'idle':name;this.lastActivity=this.now();if(['happy','error','greeting'].includes(name))this.preview(name,1600);else this.onChange()}
  preview(name,duration=3000){if(!MOODS.has(name))throw new Error('Biểu cảm không hợp lệ');this.flash={name,until:this.now()+duration};this.onChange()}
  move(dx,dy){
    if(this.settings.clickThrough||!Number.isFinite(dx)||!Number.isFinite(dy)||Math.abs(dx)>200||Math.abs(dy)>200)return
    this.pauseUntil=this.now()+1200;this.lastActivity=this.now();const bounds=this.pet.getBounds(),area=this.screen.getDisplayNearestPoint(this.screen.getCursorScreenPoint()).workArea
    const next=fit({...bounds,x:bounds.x+dx,y:bounds.y+dy},area);this.pet.setPosition(next.x,next.y,false);this.settings.position=this.pet.getBounds()
  }
  normalizeSize(){
    if(this.pet.isDestroyed()||this.resizing)return
    const bounds=this.pet.getBounds();if(Math.abs(bounds.width-SIZE.width)<=8&&Math.abs(bounds.height-SIZE.height)<=8)return
    this.resizing=true
    try{const area=this.screen.getDisplayMatching(bounds).workArea;this.pet.setBounds(fit({...bounds,...SIZE},area));this.applyShape()}finally{this.resizing=false}
  }
  tick(){
    if(this.pet.isDestroyed())return
    this.normalizeSize()
    if(!this.settings.petVisible)return
    this.applyInput()
    const currentMood=this.mood();if(currentMood!==this.sentMood){this.sentMood=currentMood;this.onChange()}
    if(!this.settings.roaming||this.panel||this.now()<this.pauseUntil)return
    const bounds=this.pet.getBounds(),area=this.screen.getDisplayMatching(bounds).workArea
    const next=bounce(bounds,area,this.direction)
    this.pet.setPosition(next.bounds.x,next.bounds.y,false);this.direction=next.direction
    if(next.turned){this.preview('happy',500);this.onChange()}
  }
  refit(){if(this.pet.isDestroyed())return;const bounds=this.pet.getBounds(),area=this.screen.getDisplayMatching(bounds).workArea;this.pet.setBounds(fit({...bounds,...SIZE},area));this.applyShape();if(this.panel)this.chat.setBounds(fit(this.chat.getBounds(),area));this.onChange()}
  shutdown(){this.quitting=true;this.settings.position=this.pet.getBounds()}
}
module.exports={Companion,MOODS}
