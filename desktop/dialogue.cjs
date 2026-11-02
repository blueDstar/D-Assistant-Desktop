const crypto=require('node:crypto')
const {parseCommand,normalize,APPS}=require('./commands.cjs')
class DesktopDialogue{
  constructor({resolve,execute,now=Date.now}){this.resolve=resolve;this.execute=execute;this.now=now;this.pending=null;this.actions=new Map();this.revision=0}
  cancel(){this.revision++;this.pending=null;this.actions.clear()}
  ticket(command,target=null){const id=crypto.randomUUID();this.actions.set(id,{command,target,expires:this.now()+120000});return id}
  async respond(text){
    if(typeof text!=='string'||!text.trim()||text.length>16000)throw new Error('Yêu cầu không hợp lệ')
    const revision=++this.revision
    const q=normalize(text)
    const yes=/^(co|co a|vang|vang a|da|da co|u|uh|duoc|duoc roi|dung|dung roi|dong y|ok|okay|oke|mo di|mo luon|yes)$/.test(q)
    const no=/^(khong|khong a|khong mo|huy|huy bo|thoi|dung mo|no)$/.test(q)
    const pending=this.pending;this.pending=null;this.actions.clear()
    if(yes&&pending&&pending.expires>=this.now()){
      try{const target=await this.resolve(pending.command.id);if(revision!==this.revision)return {handled:true,message:'Yêu cầu cũ đã dừng.',stage:'cancelled'};return {handled:true,message:'Được, mình sẽ mở '+pending.name+'.',action_id:this.ticket(pending.command,target),stage:'ready'}}
      catch(error){return {handled:true,message:error.code==='INVENTORY_UNAVAILABLE'?'Mình chưa kiểm tra được ứng dụng đã cài. Thử lại sau một chút nhé.':pending.name+' chưa được cài đặt hoặc chưa tìm thấy mục mở ứng dụng trên máy.',stage:'not_installed'}}
    }
    if(yes)return {handled:true,message:'Hiện chưa có yêu cầu mở phần mềm nào chờ xác nhận.',stage:'idle'}
    if(no&&pending)return {handled:true,message:'Được, mình không mở '+pending.name+'.',stage:'cancelled'}
    const command=parseCommand(text)
    if(!command&&pending&&pending.expires>=this.now()&&q.split(' ').length<=3){this.pending=pending;return {handled:true,message:'Mình đang chờ xác nhận mở '+pending.name+'. Bạn nói “có” hoặc “không” nhé.',stage:'confirmation',awaiting_confirmation:true}}
    if(!command)return {handled:false}
    if(command.kind==='blocked')return {handled:true,message:command.message,stage:'blocked'}
    if(command.kind==='open_app'&&command.id!=='workspace'){
      const name=APPS[command.id]?.name||command.name
      this.pending={command,name,expires:this.now()+120000}
      return {handled:true,message:'Bạn muốn mở '+name+' phải không?',stage:'confirmation',awaiting_confirmation:true}
    }
    const message=command.kind==='open_web'?'Mình sẽ mở '+new URL(command.url).hostname+'.':command.kind==='show_main'?'Mình mở cửa sổ D-bot nhé.':command.kind==='hide_main'?'Mình thu cửa sổ về robot nhé.':command.kind==='open_app'?'Mình sẽ mở thư mục dự án.':command.enabled?'Mình bật đi lại nhé.':'Mình dừng đi lại nhé.'
    return {handled:true,message,action_id:this.ticket(command),stage:'ready'}
  }
  async complete(id){
    const action=this.actions.get(id);this.actions.delete(id)
    if(!action||action.expires<this.now())throw new Error('Yêu cầu đã hết hạn hoặc bị dừng. Hãy yêu cầu lại.')
    return this.execute(action.command,action.target)
  }
}
module.exports={DesktopDialogue}
