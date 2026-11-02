const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const ts=require('../node_modules/typescript')
function setup({pending=false}={}){
  const players=[],cleanup=[],requests=[];let finishAudio
  const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/speechQueue.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
  class Audio{constructor(url){this.src=url;players.push(this)}play(){return Promise.resolve()}pause(){this.paused=true}}
  const react={useRef:value=>({current:value}),useState:value=>[value,()=>{}],useEffect:fn=>cleanup.push(fn())}
  const api={audioRequest:(text,speed)=>{requests.push({text,speed});return pending?new Promise(r=>finishAudio=r):Promise.resolve(new Blob(['wav']))}}
  const context={exports:{},require:name=>name==='react'?react:api,Audio,AbortController,Blob,URL:{createObjectURL:()=> 'blob:test',revokeObjectURL:()=>{}},localStorage:{getItem:()=>null},console}
  vm.runInNewContext(source,context)
  return {speech:context.exports.useSpeechQueue({tts_speed:0.85},()=>{}),players,cleanup,requests,finish:()=>finishAudio(new Blob(['wav']))}
}
const tick=()=>new Promise(r=>setImmediate(r))

test('long manual reading preserves the whole reply across bounded audio chunks',async()=>{
  const {speech,players,requests}=setup();const text=('A complete language lesson. ').repeat(180);let completed=false
  const result=speech.speak(text).then(value=>{completed=value})
  let played=0
  for(let i=0;i<12&&!completed;i++){await tick();if(players[played]){players[played++].onended();await tick()}}
  await result
  assert.ok(completed&&requests.length>1)
  assert.ok(requests.every(r=>r.text.length<=1200))
  assert.equal(requests.map(r=>r.text).join('').replace(/\s/g,''),text.replace(/\s/g,''))
})
test('speak resolves only after playback ends, at configured natural speed',async()=>{
  const {speech,players,requests}=setup();let finished=false
  const reply=speech.speak('Được, mình sẽ mở PowerPoint.').then(value=>{finished=value;return value})
  await tick();assert.equal(finished,false);assert.equal(requests[0].speed,0.85);assert.equal(players.length,1)
  players[0].onended();assert.equal(await reply,true)
})
test('Stopping playback or a cold synthesis resolves false and never releases a launch',async()=>{
  const live=setup();const played=live.speech.speak('Opening');await tick();live.speech.stopAudio();assert.equal(await played,false)
  const cold=setup({pending:true});const pending=cold.speech.speak('Opening');cold.speech.stopAudio();assert.equal(await pending,false);cold.finish();await tick();assert.equal(cold.players.length,0)
})
test('Unmount cancels an awaited reply',async()=>{
  const q=setup();const pending=q.speech.speak('Hello');await tick();q.cleanup.forEach(fn=>fn());assert.equal(await pending,false)
})
