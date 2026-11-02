import {VoiceActivity} from './voiceActivity.ts'
export function rms(frame: Float32Array): number {
  if (!frame.length) return 0
  let total = 0
  for (const value of frame) total += value * value
  return Math.sqrt(total / frame.length)
}

export function encodeWav(frames: Float32Array[], sampleRate: number): ArrayBuffer {
  const count = frames.reduce((sum, frame) => sum + frame.length, 0)
  const buffer = new ArrayBuffer(44 + count * 2), view = new DataView(buffer)
  const str = (offset: number, value: string) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)) }
  str(0, 'RIFF'); view.setUint32(4, 36 + count * 2, true); str(8, 'WAVE'); str(12, 'fmt ')
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true)
  str(36, 'data'); view.setUint32(40, count * 2, true)
  let offset = 44
  for (const frame of frames) for (const sample of frame) { const value = Math.max(-1, Math.min(1, sample)); view.setInt16(offset, value < 0 ? value * 32768 : value * 32767, true); offset += 2 }
  return buffer
}

export class TurnDetector {
  private pre: Float32Array[] = []
  private frames: Float32Array[] = []
  private manual: Float32Array[] = []
  private manualSamples=0
  private activity: VoiceActivity
  sampleRate: number
  threshold: number
  silenceMs: number
  speechMs: number
  constructor(sampleRate: number, threshold = 0.006, silenceMs = 750, speechMs=90) { this.sampleRate = sampleRate; this.threshold = threshold; this.silenceMs = silenceMs;this.speechMs=speechMs;this.activity=new VoiceActivity({threshold,silenceMs,speechMs}) }
  reset() { this.pre = []; this.frames = [];this.manual=[];this.manualSamples=0;this.activity.reset() }
  finish(): ArrayBuffer|undefined {const frames=this.frames.length?this.frames:this.manual;const audio=frames.length?encodeWav(frames,this.sampleRate):undefined;this.reset();return audio}
  feed(frame: Float32Array, allowed = true): { started?: boolean; audio?: ArrayBuffer } {
    if (!allowed) { this.reset(); return {} }
    const ms = frame.length * 1000 / this.sampleRate
    this.manual.push(frame);this.manualSamples+=frame.length
    while(this.manualSamples>this.sampleRate*25){this.manualSamples-=this.manual.shift()!.length}
    this.pre.push(frame); if (this.pre.length > 6) this.pre.shift()
    const turn=this.activity.feed(rms(frame),ms)
    if(turn?.started){this.frames=[...this.pre];return {started:true}}
    if(this.frames.length)this.frames.push(frame)
    if(turn?.finished)return {audio:this.finish()}
    if(turn?.silence)this.reset()
    return {}
  }
}

/** Only already-generated complete words are shown. No simulated or invented text. */
export class TextBuffer {
  private source = ''
  private shown = ''
  private timer: ReturnType<typeof setTimeout> | null = null
  private output: (text: string) => void
  private interval: number
  constructor(output: (text: string) => void, interval = 100) { this.output = output; this.interval = interval }
  push(text: string) { this.source = text; if (!this.timer) this.timer = setTimeout(() => this.tick(), this.interval) }
  private tick() {
    this.timer = null
    const boundary = this.source.search(/\S+$/u)
    const prefix = boundary >= 0 ? this.source.slice(0, boundary) : this.source
    if (prefix && prefix !== this.shown) { this.shown = prefix; this.output(prefix) }
  }
  flush(text = this.source) { if (this.timer) clearTimeout(this.timer); this.timer = null; this.source = text; this.shown = text; this.output(text) }
  dispose() { if (this.timer) clearTimeout(this.timer); this.timer = null }
}

export class SpeechSentences {
  private buffer = ''
  private code = false
  feed(text: string): string[] {
    this.buffer += text
    const sentences: string[] = []
    while (this.buffer) {
      if (this.code) {
        const end = this.buffer.indexOf('```')
        if (end < 0) { this.buffer = this.buffer.slice(-2); break }
        this.buffer = this.buffer.slice(end + 3); this.code = false; continue
      }
      const fence = this.buffer.indexOf('```')
      if (fence === 0) { this.buffer = this.buffer.slice(3); this.code = true; continue }
      const available = fence < 0 ? this.buffer : this.buffer.slice(0, fence)
      const matches = [...available.matchAll(/[.!?](?=\s)|\n\n/gu)]
      const end = matches.find(match => match.index! + match[0].length >= 24)
      let cut = end ? end.index! + end[0].length : available.length >= 240 ? available.lastIndexOf(' ', 240) : fence > 0 ? fence : -1
      if (cut <= 0) break
      const sentence = this.buffer.slice(0, cut).trim()
      this.buffer = this.buffer.slice(cut)
      if (sentence) sentences.push(sentence)
    }
    return sentences
  }
  flush(): string[] { const rest = this.code ? '' : this.buffer.split('```')[0].trim(); this.buffer = ''; this.code = false; return rest ? [rest] : [] }
}
