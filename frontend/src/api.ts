let token = ''
let sessionPromise:Promise<void>|null=null
export async function initSession():Promise<void> {
  if(!sessionPromise)sessionPromise=(async()=>{
    const response=await fetch('/api/session')
    if(!response.ok)throw new Error('Không kết nối được phiên D-bot')
    const body=await response.json()
    if(typeof body.token!=='string'||body.token.length<16)throw new Error('Session token không hợp lệ')
    token=body.token
  })().finally(()=>{sessionPromise=null})
  return sessionPromise
}
async function sessionFetch(path:string,options:RequestInit):Promise<Response>{
  if(!token)await initSession()
  const request=()=>fetch('/api'+path,{...options,headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),'X-D-Bot-Token':token,...options.headers}})
  let response=await request()
  // Token rejection happens before server mutations; retry once after restart.
  if(response.status===403){await initSession();response=await request()}
  return response
}
export async function api<T = any>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await sessionFetch(url,options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || body.message || `HTTP ${response.status}`))
  }
  return response.json()
}
export async function streamRequest(path: string, body: unknown, onEvent: (event: any) => void, signal: AbortSignal) {
  const response = await sessionFetch(path, {method:'POST',body:JSON.stringify(body),signal})
  if (!response.ok) { const error = await response.json(); throw new Error(typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail)) }
  if (!response.body) throw new Error('Trình duyệt không hỗ trợ streaming')
  const reader = response.body.getReader(), decoder = new TextDecoder()
  let buffer = ''
  try { while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const lines = buffer.split('\n'); buffer = lines.pop() || ''
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line))
    if (done) break
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer))
  } finally { await reader.cancel().catch(()=>{});reader.releaseLock() }
}
export const streamChat = (body: unknown, onEvent: (event: any) => void, signal: AbortSignal) => streamRequest('/chat', body, onEvent, signal)
export async function audioRequest(text: string, speed: number, signal?: AbortSignal,language='vi'): Promise<Blob> {
  const response = await sessionFetch('/voice/synthesize', {method:'POST',body:JSON.stringify({text,speed,language}),signal})
  if (!response.ok) throw new Error((await response.json()).detail || 'Không tạo được giọng nói')
  return response.blob()
}
