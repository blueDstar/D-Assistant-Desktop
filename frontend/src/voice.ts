import {useEffect,useState} from 'react'
import {useSpeechQueue} from './speechQueue'
import {useConversation} from './conversation'

type Options={onUtterance:(text:string)=>Promise<void>;onInterrupt:()=>Promise<void>;busy:boolean;performance?:string;mode?:string;projectId?:string;useKnowledge?:boolean;privateMode?:boolean}
export function useVoice(setDraft:(text:string)=>void,setError:(text:string)=>void,config:any,options:Options){
  const [fromVoice,setFromVoice]=useState(false)
  const speech=useSpeechQueue(config,setError)
  const conversation=useConversation({...options,language:config?.stt_language,onUtterance:async text=>{setFromVoice(true);await options.onUtterance(text)}},speech,setDraft,setError)
  useEffect(()=>{const hidden=()=>{if(document.hidden){conversation.stopConversation();speech.stopAudio()}};document.addEventListener('visibilitychange',hidden);return ()=>document.removeEventListener('visibilitychange',hidden)},[])
  return {recording:false,transcribing:conversation.callTranscribing,fromVoice,clearSource:()=>setFromVoice(false),startRecording:conversation.startConversation,stopRecording:conversation.stopConversation,cancelRecording:()=>conversation.stopConversation(false),...speech,...conversation}
}
