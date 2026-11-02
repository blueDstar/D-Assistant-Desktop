import {useEffect,useState} from 'react'
import './desktop.css'

export default function DesktopControls(){
  const desktop=(window as any).dBotDesktop
  const [state,setState]=useState<any>(null),[error,setError]=useState('')
  useEffect(()=>{if(!desktop)return;desktop.state().then(setState).catch((e:any)=>setError(e.message));return desktop.onState(setState)},[])
  if(!desktop)return null
  return <div className="desktop-controls"><button title="Trò chuyện nhanh · Ctrl+Alt+D" onClick={()=>desktop.setPanel(true).catch((e:any)=>setError(e.message))}>Nói với robot</button><button title="Bật/tắt trợ lý nổi trên desktop" onClick={()=>desktop.togglePet().then(setState).catch((e:any)=>setError(e.message))}>{state?.petVisible?'Ẩn trợ lý nổi':'Hiện trợ lý nổi'}</button><button title="Đóng cửa sổ chính cũng thu về trợ lý nổi" onClick={()=>desktop.hideMain().catch((e:any)=>setError(e.message))}>Thu về desktop</button>{error&&<span role="alert">{error}</span>}</div>
}
