const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path')
const {DesktopDialogue}=require('../dialogue.cjs')
const settle=async()=>{for(let i=0;i<4;i++)await new Promise(r=>setImmediate(r))}
test('Pet automatically sends speech after silence, listens for yes, and speaks before launching',async()=>{
  const nodes=new Map(),timers=new Map(),later=[],players=[],texts=[],opens=[],tracks=[];let clock=0,level=0,serial=0,transcribed=0
  const element=id=>{if(!nodes.has(id))nodes.set(id,{value:'',hidden:false,checked:true,textContent:'',focus(){},setPointerCapture(){},releasePointerCapture(){}});return nodes.get(id)}
  const engine=new DesktopDialogue({resolve:async()=>({exe:'fake-powerpoint.exe'}),execute:async cmd=>{opens.push(cmd.id);return {message:'Opened synthetic app'}}})
  const desktop={state:async()=>({voiceSpeed:0.85}),onState(){},onReply(){},setPanel:async()=>{},prepareVoice:async()=>{},cancel:async()=>engine.cancel(),transcribe:async()=>({text:['Mở PowerPoint','Có'][transcribed++]}),ask:async text=>{texts.push(text);return engine.respond(text)},speak:async()=>new Uint8Array([1,2]),completeAction:id=>engine.complete(id)}
  class Recorder{static isTypeSupported(){return true}constructor(){this.state='inactive'}start(){this.state='recording'}stop(){this.state='inactive';this.ondataavailable?.({data:new Blob(['synthetic mic'])});this.onstop?.()}}
  class Context{async resume(){}async close(){}createAnalyser(){return {fftSize:1024,getFloatTimeDomainData:array=>array.fill(level),connect(){}}}createMediaStreamSource(){return {connect(){},disconnect(){}}}createGain(){return {gain:{value:0},connect(){}}}}
  class Audio{constructor(src){this.src=src;players.push(this)}async play(){}pause(){}}
  const context=vm.createContext({window:{dBotDesktop:desktop,addEventListener(){}},document:{getElementById:element,body:{classList:{toggle(){},add(){},remove(){}}},addEventListener(){}},navigator:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop:()=>tracks.push('stopped')}]})}},MediaRecorder:Recorder,AudioContext:Context,Audio,Blob,Uint8Array,Float32Array,URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},performance:{now:()=>clock},setInterval:fn=>{timers.set(++serial,fn);return serial},clearInterval:id=>timers.delete(id),setTimeout:fn=>{later.push(fn);return serial++},clearTimeout(){},console})
  for(const name of ['voice-turn.js','turn-flow.js','pet.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'..',name),'utf8'),context)
  await context.panel(true);await element('mic').onclick()
  function utterance(){level=0.07;for(let i=0;i<6;i++){clock+=30;[...timers.values()].forEach(fn=>fn())}level=0.001;for(let i=0;i<30;i++){clock+=30;[...timers.values()].forEach(fn=>fn())}}
  utterance();await settle();assert.equal(transcribed,1);assert.deepEqual(texts,['Mở PowerPoint']);assert.deepEqual(opens,[]);assert.equal(players.length,1)
  players[0].onended();await settle();later.shift()();utterance();await settle()
  assert.deepEqual(texts,['Mở PowerPoint','Có']);assert.deepEqual(opens,[]);assert.equal(players.length,2)
  players[1].onended();await settle();assert.deepEqual(opens,['powerpoint'])
  await element('stop').onclick();assert.ok(tracks.length);assert.equal(timers.size,0)
})
