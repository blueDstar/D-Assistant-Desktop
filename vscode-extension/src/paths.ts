import * as path from 'node:path'

export function safeRelative(value:string){
  if(!value||value.includes('\\')||value.includes(':')||path.posix.isAbsolute(value)||value.split('/').some(p=>!p||p==='.'||p==='..'||/[<>"|?*\x00-\x1f]/.test(p)||/[ .]$/.test(p)||/^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?$/i.test(p)))throw new Error('Đường dẫn file không hợp lệ')
  if(value.split('/').some(p=>['.git','.codex','.agents','.aws','.ssh','.vscode','.gnupg','.npmrc','.netrc','.pypirc','id_rsa','id_ed25519','credentials.json'].includes(p.toLowerCase())||p.toLowerCase().startsWith('.env')||/\.(pem|key|p12|pfx)$/i.test(p)))throw new Error('Không truy cập file/thư mục nội bộ')
  return value
}
export function withinRoot(root:string,relative:string){
  const target=path.resolve(root,...safeRelative(relative).split('/')),check=path.relative(path.resolve(root),target)
  if(check.startsWith('..'+path.sep)||check==='..'||path.isAbsolute(check))throw new Error('File ngoài workspace')
  return target
}
