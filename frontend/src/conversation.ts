import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { rms, TurnDetector } from './voiceCore'

type Options = { onUtterance: (text: string) => Promise<void>; onInterrupt: () => Promise<void>; busy: boolean; performance?: string; mode?: string; projectId?: string; useKnowledge?: boolean; privateMode?: boolean; language?: string }
export function useConversation(options: Options, speech: { stopAudio: () => void; isAudioBusy: () => boolean; speaking: boolean; synthesizing: boolean }, setDraft: (value: string) => void, onError: (value: string) => void) {
  const [active, setActive] = useState(false), [warming, setWarming] = useState(false), [transcribing, setTranscribing] = useState(false), [voiceDetected, setVoiceDetected] = useState(false), [level, setLevel] = useState(0), [bargeIn, setBargeIn] = useState(false)
  const current = useRef({ options, speech, onError }); current.current = { options, speech, onError }
  const running = useRef(false), generation = useRef(0), preparing = useRef(false), processing = useRef(false), waiting = useRef(false), forceListen = useRef(false), allowBarge = useRef(false), blockedUntil = useRef(0)
  const turnId = useRef(0)
  const microphone = useRef<MediaStream | null>(null), context = useRef<AudioContext | null>(null), worklet = useRef<AudioWorkletNode | null>(null), detector = useRef<TurnDetector | null>(null), transcription = useRef<AbortController | null>(null)
  const warmup = useRef<AbortController | null>(null)
  function stopConversation(notify = true) {
    const wasActive = running.current
    generation.current++; turnId.current++; running.current = false; preparing.current = false; processing.current = false; waiting.current = false; forceListen.current = false
    transcription.current?.abort(); transcription.current = null
    warmup.current?.abort(); warmup.current = null
    if (worklet.current) { worklet.current.port.onmessage = null; worklet.current.disconnect(); worklet.current = null }
    microphone.current?.getTracks().forEach(track => track.stop()); microphone.current = null
    if (context.current) void context.current.close().catch(() => {}); context.current = null
    detector.current?.reset(); setActive(false); setWarming(false); setTranscribing(false); setVoiceDetected(false); setLevel(0)
    if (wasActive) { current.current.speech.stopAudio(); if (notify) void current.current.options.onInterrupt() }
  }
  async function interrupt() {
    turnId.current++; transcription.current?.abort(); processing.current = false; setTranscribing(false)
    current.current.speech.stopAudio(); forceListen.current = true; waiting.current = false; blockedUntil.current = performance.now() + 250; detector.current?.reset()
    await current.current.options.onInterrupt()
  }
  async function submitAudio(audio: ArrayBuffer, version: number) {
    if (processing.current || !running.current) return
    const turn = ++turnId.current
    processing.current = true; setTranscribing(true); setVoiceDetected(false)
    const control = new AbortController(); transcription.current = control
    try {
      const form = new FormData(); form.append('file', new Blob([audio], { type: 'audio/wav' }), 'conversation.wav')
      if(current.current.options.language)form.append('language',current.current.options.language!)
      form.append('context',['en','ja'].includes(current.current.options.language||'')?'general':'desktop')
      const desktop=(window as any).dBotDesktop
      const result = desktop ? await desktop.transcribe(new Uint8Array(audio),current.current.options.language) : await api('/voice/transcribe', { method: 'POST', body: form, signal: control.signal })
      if (version !== generation.current || turn !== turnId.current || !running.current) return
      processing.current = false
      setTranscribing(false)
      if (result.silence || !result.text?.trim()) return
      setDraft(result.text); waiting.current = true; forceListen.current = false
      await current.current.options.onUtterance(result.text)
    } catch (error: any) { if (version === generation.current && turn === turnId.current && error.name !== 'AbortError') current.current.onError(error.message) }
    finally { if (version === generation.current && turn === turnId.current) { processing.current = false; waiting.current = false; setTranscribing(false); blockedUntil.current = performance.now() + 350 } }
  }
  async function startConversation() {
    if (running.current) return
    current.current.speech.stopAudio(); current.current.onError('')
    const version = ++generation.current
    running.current = true; preparing.current = true; setActive(true); setWarming(true)
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) throw new Error('Hội thoại tự động cần Edge/Chrome hỗ trợ AudioWorklet trên localhost.')
      const device = localStorage.getItem('dbot-mic')
      const media = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, ...(device ? { deviceId: { exact: device } } : {}) } })
      if (version !== generation.current) { media.getTracks().forEach(t => t.stop()); return }
      microphone.current = media
      const ctx = new AudioContext({ sampleRate: 16000 }); context.current = ctx; await ctx.resume()
      await ctx.audioWorklet.addModule('/voice-recorder.worklet.js')
      if (version !== generation.current) return
      const node = new AudioWorkletNode(ctx, 'dbot-recorder'); worklet.current = node
      const source = ctx.createMediaStreamSource(microphone.current), muted = ctx.createGain(); muted.gain.value = 0
      const filter=ctx.createBiquadFilter();filter.type='highpass';filter.frequency.value=120;source.connect(filter);filter.connect(node); node.connect(muted); muted.connect(ctx.destination)
      detector.current = new TurnDetector(ctx.sampleRate)
      running.current = true; preparing.current = true; setActive(true); setWarming(true)
      node.port.onmessage = event => {
        if (!running.current || version !== generation.current) return
        const frame = event.data as Float32Array, amplitude = rms(frame); setLevel(Math.min(1, amplitude * 12))
        const assistant = current.current.options.busy || waiting.current || current.current.speech.isAudioBusy()
        const canListen = !preparing.current && !processing.current && performance.now() >= blockedUntil.current && (!assistant || forceListen.current || allowBarge.current)
        const turn = detector.current!.feed(frame, canListen)
        if (turn.started) { setVoiceDetected(true); if (assistant && allowBarge.current) void interrupt() }
        if (turn.audio) void submitAudio(turn.audio, version)
      }
      warmup.current = new AbortController()
      // Capture the first utterance while engines prepare; never discard words
      // spoken immediately after clicking Nói.
      if (version === generation.current) { preparing.current = false; setWarming(false); blockedUntil.current = performance.now() + 100 }
      void api('/voice/prepare', { method:'POST',signal:warmup.current.signal }).catch(error=>{if(version===generation.current&&error.name!=='AbortError')current.current.onError('Chưa chuẩn bị được voice; lượt nhận giọng nói sẽ thử lại. '+error.message)})
    } catch (error: any) { if (version === generation.current) { stopConversation(false); current.current.onError(error.name === 'NotAllowedError' ? 'Microphone bị chặn. Cho phép microphone cho localhost rồi bắt đầu lại.' : error.message) } }
  }
  function finishUtterance(){
    if(!running.current||processing.current||current.current.options.busy||current.current.speech.isAudioBusy())return
    const audio=detector.current?.finish()
    if(audio)void submitAudio(audio,generation.current)
  }
  useEffect(() => () => { generation.current++; running.current = false; transcription.current?.abort(); warmup.current?.abort(); microphone.current?.getTracks().forEach(t => t.stop()); worklet.current?.disconnect(); if (context.current) void context.current.close().catch(() => {}) }, [])
  const state = !active ? 'Tắt' : warming ? 'Đang chuẩn bị engine local' : speech.speaking ? 'D-bot đang nói' : transcribing ? 'Đang nhận giọng nói' : options.busy || speech.synthesizing ? 'D-bot đang xử lý' : voiceDetected ? 'Đang nghe bạn nói' : 'Đang nghe — nói rồi dừng khoảng 1 giây'
  return { callActive: active, callState: state, callTranscribing: transcribing, micLevel: level, bargeIn, setBargeIn: (value: boolean) => { allowBarge.current = value; setBargeIn(value) }, startConversation, stopConversation, interrupt,finishUtterance }
}
