const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm')
const ts=require('../node_modules/typescript')
function setup(){
  const requests=[],players=[],revoked=[],states=[]
  const source=ts.transpileModule(fs.readFileSync(require('node:path').join(__dirname,'../src/localPlayback.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
  class Audio{constructor(src){this.src=src;players.push(this)}play(){return Promise.resolve()}pause(){this.paused=true}}
  const context={exports:{},AbortController,Audio,URL:{createObjectURL:()=>`blob:${players.length}`,revokeObjectURL:url=>revoked.push(url)}}
  vm.runInNewContext(source,context)
  const playback=new context.exports.LocalPlayback((text,signal)=>new Promise((resolve,reject)=>requests.push({text,signal,resolve,reject})),state=>states.push(state))
  return {playback,requests,players,revoked,states}
}
test('out-of-order synthesis can only play the newest request',async()=>{
  const s=setup(),old=s.playback.play('old','en'),latest=s.playback.play('new','ja')
  assert.equal(s.requests[0].signal.aborted,true)
  s.requests[1].resolve({});assert.equal(await latest,true)
  s.requests[0].resolve({});assert.equal(await old,false)
  assert.equal(s.players.length,1);assert.equal(s.players[0].paused,undefined)
  s.players[0].onended();assert.equal(s.states.at(-1),'ended');assert.equal(s.revoked.length,1)
})
test('stop cancels synthesis, and stale failures do not interrupt a newer clip',async()=>{
  const s=setup(),old=s.playback.play('old','en'),latest=s.playback.play('new','en')
  s.requests[1].resolve({});await latest
  s.requests[0].reject(new Error('old error'));assert.equal(await old,false)
  assert.equal(s.players[0].paused,undefined)
  const staleEnded=s.players[0].onended;s.playback.stop();staleEnded()
  assert.equal(s.states.at(-1),'idle');assert.equal(s.revoked.length,1)
  const pending=s.playback.play('pending','en');s.playback.stop(false)
  s.requests[2].resolve({});assert.equal(await pending,false);assert.equal(s.players.length,1)
})
test('active synthesis failure resets playback and reaches the caller',async()=>{
  const s=setup(),pending=s.playback.play('failure','en')
  s.requests[0].reject(new Error('voice unavailable'))
  await assert.rejects(pending,/voice unavailable/);assert.equal(s.states.at(-1),'idle')
})
