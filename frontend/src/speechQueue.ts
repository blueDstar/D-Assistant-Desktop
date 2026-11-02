import { useEffect, useRef, useState } from 'react'
import { audioRequest } from './api'

type Item = { text: string; pending?: Promise<{ blob?: Blob; error?: any }>; finished?:(played:boolean)=>void }
function speechParts(text:string){const parts:string[]=[];let rest=text.trim();while(rest.length>1200){const prefix=rest.slice(0,1200);let boundary=Math.max(prefix.lastIndexOf('. '),prefix.lastIndexOf('! '),prefix.lastIndexOf('? '),prefix.lastIndexOf('。'),prefix.lastIndexOf('！'),prefix.lastIndexOf('？'),prefix.lastIndexOf('\n'));if(boundary<400)boundary=prefix.lastIndexOf(' ');const end=boundary>=400?boundary+1:1200;parts.push(rest.slice(0,end));rest=rest.slice(end).trim()}if(rest)parts.push(rest);return parts}
export function useSpeechQueue(config: any, onError: (text: string) => void) {
  const [speaking, setSpeaking] = useState(false), [synthesizing, setSynthesizing] = useState(false)
  const settings = useRef(config); settings.current = config
  const errorHandler = useRef(onError); errorHandler.current = onError
  const queue = useRef<Item[]>([]), pumping = useRef(false), epoch = useRef(0), audio = useRef<HTMLAudioElement | null>(null), controllers = useRef(new Set<AbortController>()), urls = useRef(new Set<string>()), endPlay = useRef<(() => void) | null>(null)
  const activeItem=useRef<Item|null>(null)
  function prepare(item: Item) {
    if (!item.pending) {
      const control = new AbortController(); controllers.current.add(control)
      const preferred=settings.current?.tts_language||'vi'
      const language=preferred==='vi'?'vi':/[\u3040-\u30ff\u4e00-\u9fff]/u.test(item.text)?'ja':/[ăâđêôơưáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]/iu.test(item.text)?'vi':'en'
      item.pending = audioRequest(item.text, settings.current?.tts_speed || 1, control.signal,language).then(blob => ({ blob })).catch(error => ({ error })).finally(() => controllers.current.delete(control))
    }
    return item.pending
  }
  function prefetch() { if (audio.current && queue.current[0]) prepare(queue.current[0]) }
  function stopAudio() {
    epoch.current++; queue.current.forEach(item=>item.finished?.(false));activeItem.current?.finished?.(false);activeItem.current=null;queue.current = []; pumping.current = false
    controllers.current.forEach(control => control.abort()); controllers.current.clear()
    audio.current?.pause(); audio.current = null; endPlay.current?.(); endPlay.current = null
    urls.current.forEach(url => URL.revokeObjectURL(url)); urls.current.clear()
    setSpeaking(false); setSynthesizing(false)
  }
  async function pump() {
    if (pumping.current) return
    pumping.current = true
    const generation = epoch.current
    try {
      while (queue.current.length && generation === epoch.current) {
        const item = queue.current.shift()!
        activeItem.current=item
        setSynthesizing(true)
        const result = await prepare(item)
        if (generation !== epoch.current) return
        if (result.error) throw result.error
        const url = URL.createObjectURL(result.blob!); urls.current.add(url)
        const player = new Audio(url); audio.current = player
        player.volume = Number(localStorage.getItem('dbot-volume') ?? '1')
        const ended = new Promise<void>((resolve, reject) => { endPlay.current = resolve; player.onended = () => resolve(); player.onerror = () => reject(new Error('Không phát được audio local')) })
        await player.play()
        if (generation !== epoch.current) return
        setSpeaking(true); setSynthesizing(false); prefetch()
        await ended
        if (generation !== epoch.current) return
        item.finished?.(true);activeItem.current=null
        audio.current = null; endPlay.current = null; setSpeaking(false)
        URL.revokeObjectURL(url); urls.current.delete(url)
      }
    } catch (error: any) {
      if (generation === epoch.current && error.name !== 'AbortError') { errorHandler.current(error.name === 'NotAllowedError' ? 'Trình duyệt chặn phát giọng. Nhấn Đọc hoặc bắt đầu lại hội thoại để cho phép audio.' : error.message); stopAudio() }
    } finally {
      if (generation === epoch.current) { pumping.current = false; setSpeaking(false); setSynthesizing(false) }
    }
  }
  function enqueueSpeech(text: string) { if (!text.trim()) return; queue.current.push({ text }); if (!pumping.current) void pump(); else prefetch() }
  function speak(text: string,prepared?:Promise<Uint8Array>):Promise<boolean> { stopAudio();if(!text.trim())return Promise.resolve(true);return new Promise(resolve=>{const parts=prepared?[text]:speechParts(text);parts.forEach((part,index)=>queue.current.push({text:part,finished:index===parts.length-1?resolve:undefined,pending:prepared?.then(bytes=>({blob:new Blob([new Uint8Array(bytes)],{type:'audio/wav'})})).catch(error=>({error}))}));void pump()}) }
  useEffect(() => () => { epoch.current++;queue.current.forEach(item=>item.finished?.(false));activeItem.current?.finished?.(false); controllers.current.forEach(c => c.abort()); audio.current?.pause(); endPlay.current?.(); urls.current.forEach(url => URL.revokeObjectURL(url)) }, [])
  return { speaking, synthesizing, stopAudio, enqueueSpeech, speak, isAudioBusy: () => pumping.current || queue.current.length > 0 }
}
