import test from 'node:test'
import assert from 'node:assert/strict'
import { encodeWav, rms, TurnDetector, TextBuffer, SpeechSentences } from '../src/voiceCore.ts'

test('WAV encodes actual sample rate, mono PCM and clipping', () => {
  const data = new DataView(encodeWav([new Float32Array([-2, 0, 2])], 48000))
  assert.equal(data.getUint32(24, true), 48000)
  assert.equal(data.getUint32(40, true), 6)
  assert.equal(data.getInt16(44, true), -32768)
  assert.equal(data.getInt16(48, true), 32767)
  assert.equal(rms(new Float32Array([.5, -.5])), .5)
})
test('silence and short noise never submit; speech ends after one second quiet', () => {
  const detector = new TurnDetector(16000,0.006,1000,160), silence = new Float32Array(1600), speech = new Float32Array(1600).fill(.1)
  for (let i=0;i<30;i++) assert.deepEqual(detector.feed(silence), {})
  assert.deepEqual(detector.feed(speech), {})
  assert.deepEqual(detector.feed(silence), {})
  detector.feed(speech); assert.equal(detector.feed(speech).started, true)
  for (let i=0;i<9;i++) assert.equal(detector.feed(silence).audio, undefined)
  assert.ok(detector.feed(silence).audio instanceof ArrayBuffer)
  detector.feed(speech); detector.feed(speech)
  detector.feed(speech, false)
  for (let i=0;i<12;i++) assert.deepEqual(detector.feed(silence), {})
})
test('display batches only complete real words and flushes final text once', async () => {
  const shown: string[] = [], buffer = new TextBuffer(value => shown.push(value), 5)
  buffer.push('Xin'); buffer.push('Xin chào bạ')
  await new Promise(resolve => setTimeout(resolve, 15))
  assert.deepEqual(shown, ['Xin chào '])
  buffer.flush('Xin chào bạn.'); buffer.dispose()
  await new Promise(resolve => setTimeout(resolve, 15))
  assert.deepEqual(shown, ['Xin chào ', 'Xin chào bạn.'])
})
test('automatic conversation accepts a short affirmative and endpoints it without a send click',()=>{
  const detector=new TurnDetector(16000,0.014,850,90)
  assert.equal(detector.feed(new Float32Array(1600).fill(.08)).started,true)
  let result:{audio?:ArrayBuffer}={}
  for(let n=0;n<9;n++)result=detector.feed(new Float32Array(1600))
  assert.ok(result.audio instanceof ArrayBuffer)
})
test('speech waits for sentence boundary, preserves decimals and skips streamed code', () => {
  const sentences = new SpeechSentences()
  assert.deepEqual(sentences.feed('Giá trị này cần kiểm tra: 3.'), [])
  assert.deepEqual(sentences.feed('14 mét. Câu tiếp theo '), ['Giá trị này cần kiểm tra: 3.14 mét.'])
  const output = [...sentences.feed('ở trước mã. ```py\nprint(1)\n``'), ...sentences.feed('`\nĐã xong đoạn mã này rồi. '), ...sentences.flush()]
  assert.ok(output.join(' ').includes('Đã xong'))
  assert.ok(!output.join(' ').includes('print'))
})

test('quiet speech and fan background end automatically without a click',()=>{
 const detector=new TurnDetector(16000),frame=(level:number)=>new Float32Array(1600).fill(level)
 for(let i=0;i<5;i++)detector.feed(frame(.001))
 let started=false
 for(let i=0;i<6;i++)started=!!detector.feed(frame(.008)).started||started
 assert.ok(started,'soft speech below the old fixed threshold must be detected')
 let ended:any
 for(let i=0;i<9&&!ended?.audio;i++)ended=detector.feed(frame(.001))
 assert.ok(ended.audio)
 const fan=new TurnDetector(16000)
 for(let i=0;i<6;i++)fan.feed(frame(.08))
 for(let i=0;i<9;i++){const turn=fan.feed(frame(.02));if(turn.audio){assert.ok(turn.audio);return}}
 assert.fail('background above the old fixed threshold must not hold the turn open')
})
test('steady background never sends; manual finish preserves undetected quiet words',()=>{
 const detector=new TurnDetector(16000),noise=new Float32Array(1600).fill(.015)
 for(let i=0;i<140;i++)assert.equal(detector.feed(noise).audio,undefined)
 detector.feed(new Float32Array(1600).fill(.004))
 assert.ok(detector.finish() instanceof ArrayBuffer)
 assert.equal(detector.finish(),undefined)
})
