export function validateEndpoint(value:string):string {
  const url=new URL(value)
  if(url.protocol!=='http:'||!['127.0.0.1','localhost','[::1]'].includes(url.hostname)||url.username||url.password||!['','/'].includes(url.pathname)||url.search||url.hash)throw new Error('D-bot endpoint phải là HTTP loopback, không có tài khoản/path/query.')
  return url.origin
}

export class DbotClient {
  private token=''
  readonly endpoint:string
  constructor(endpoint:string){this.endpoint=validateEndpoint(endpoint)}
  private async session(){const response=await fetch(this.endpoint+'/api/session',{signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error('Không kết nối được phiên D-bot');const body=await response.json() as any;if(typeof body.token!=='string'||body.token.length<16)throw new Error('Backend trả session token không hợp lệ');this.token=body.token}
  private async fetch(path:string,options:RequestInit,retry=true):Promise<Response>{
    if(!/^\/coding(?:\/|\?|$)/.test(path))throw new Error('Extension chỉ truy cập API coding')
    if(!this.token)await this.session()
    const response=await fetch(this.endpoint+'/api'+path,{...options,headers:{'Content-Type':'application/json','X-D-Bot-Token':this.token,...options.headers}})
    if(response.status===403&&retry){await this.session();return this.fetch(path,options,false)}
    if(!response.ok){const body=await response.json().catch(()=>({})) as any;throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail||`HTTP ${response.status}`))}
    return response
  }
  async request<T=any>(path:string,options:RequestInit={}):Promise<T>{return (await this.fetch(path,{...options,signal:options.signal||AbortSignal.timeout(25000)})).json() as Promise<T>}
  async stream(body:unknown,onEvent:(event:any)=>void,signal:AbortSignal){
    const response=await this.fetch('/coding/tasks',{method:'POST',body:JSON.stringify(body),signal})
    if(!response.body)throw new Error('Không có luồng phản hồi')
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer=''
    try{
      while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value,{stream:!done});const lines=buffer.split('\n');buffer=lines.pop()||'';for(const line of lines)if(line.trim())onEvent(JSON.parse(line));if(done)break}
      if(buffer.trim())onEvent(JSON.parse(buffer))
    }finally{await reader.cancel().catch(()=>{});reader.releaseLock()}
  }
}
