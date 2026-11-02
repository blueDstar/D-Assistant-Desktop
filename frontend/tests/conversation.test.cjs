const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const ts=require('../node_modules/typescript')
const compile=name=>ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/'+name),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
function setup({late=false}={}){
 const nodes=[],sent=[],drafts=[],errors=[],cleanup=[],requests=[];let clock=0,resolveSTT
 const audio={isAudioBusy:()=>false,stopAudio(){},speaking:false,synthesizing:false},options={busy:false,onInterrupt:async()=>{},onUtterance:async text=>sent.push(text),language:'vi'}
 const globals={ArrayBuffer,DataView,Float32Array,Blob,FormData,AbortController,performance:{now:()=>clock},console}
 const activity={exports:{},...globals};vm.runInNewContext(compile('voiceActivity.ts'),activity)
 const core={exports:{},...globals,require:()=>activity.exports};vm.runInNewContext(compile('voiceCore.ts'),core)
 class Worklet{constructor(){this.port={};nodes.push(this)}connect(){}disconnect(){}}
 class Context{sampleRate=16000;audioWorklet={addModule:async()=>{}};destination={};resume(){return Promise.resolve()}close(){return Promise.resolve()}createMediaStreamSource(){return{connect(){}}}createBiquadFilter(){return{type:'',frequency:{value:0},connect(){}}}createGain(){return{gain:{value:0},connect(){}}}}
 const react={useRef:value=>({current:value}),useState:value=>[value,()=>{}],useEffect:fn=>cleanup.push(fn())}
 const context={exports:{},...globals,AudioContext:Context,AudioWorkletNode:Worklet,window:{AudioWorkletNode:Worklet},navigator:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop(){}}]})}},localStorage:{getItem:()=>null},require:name=>name==='react'?react:name==='./api'?{api:async(route,body)=>{if(route==='/voice/prepare')return {};requests.push(body);return late?new Promise(r=>resolveSTT=r):{text:'Tôi đã nói xong',silence:false}}}:core.exports}
 vm.runInNewContext(compile('conversation.ts'),context)
 const call=context.exports.useConversation(options,audio,value=>drafts.push(value),value=>errors.push(value))
 function feed(level,count){for(let i=0;i<count;i++){clock+=100;nodes[0].port.onmessage({data:new Float32Array(1600).fill(level)})}}
 return{call,options,audio,sent,drafts,errors,requests,feed,finish:()=>resolveSTT({text:'stale words',silence:false})}
}
const settle=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r))}
test('main chat automatically transcribes and submits a soft utterance after silence',async()=>{
 const s=setup();await s.call.startConversation();s.feed(.001,5);s.feed(.008,6);s.feed(.001,9);await settle()
 assert.deepEqual(s.sent,['Tôi đã nói xong']);assert.deepEqual(s.drafts,s.sent)
 assert.equal(s.requests.length,1);assert.equal(s.requests[0].body.get('context'),'desktop')
 s.options.busy=true;s.feed(.08,6);s.feed(.001,9);await settle();assert.equal(s.sent.length,1)
 s.call.stopConversation(false)
})
test('manual finish submits captured speech; ending the session discards a late transcript',async()=>{
 const s=setup({late:true});await s.call.startConversation();s.feed(.001,4);s.feed(.004,8)
 s.call.finishUtterance();await settle();assert.equal(s.requests.length,1)
 s.call.stopConversation(false);s.finish();await settle();assert.deepEqual(s.sent,[]);assert.deepEqual(s.drafts,[])
})
