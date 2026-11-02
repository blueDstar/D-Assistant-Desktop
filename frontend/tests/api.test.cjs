const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const ts=require('typescript');
function client(fetch){const exports={};const source=ts.transpileModule(fs.readFileSync(require.resolve('../src/api.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;vm.runInNewContext(source,{exports,fetch,FormData,TextDecoder,AbortSignal});return exports}
test('web client refreshes restart token once, preserving request body and stopping on real forbidden',async()=>{
 let sessions=0,posts=0;const bodies=[];
 const api=client(async(url,options)=>{if(url==='/api/session')return Response.json({token:'local-session-token-'+(++sessions)});posts++;bodies.push(options.body);return options.headers['X-D-Bot-Token']==='local-session-token-1'?new Response('{}',{status:403}):Response.json({ok:true})});
 const body=JSON.stringify({request_id:'one-request-123',content:'Đã sửa'});
 assert.equal((await api.api('/coding/test',{method:'POST',body})).ok,true);assert.equal(posts,2);assert.equal(sessions,2);assert.deepEqual(bodies,[body,body]);
 let refused=0;const denied=client(async(url)=>url==='/api/session'?Response.json({token:'a-valid-local-token'}):(refused++,Response.json({detail:'Forbidden'},{status:403})));
 await assert.rejects(denied.api('/coding/test',{method:'POST',body}),/Forbidden/);assert.equal(refused,2);
});
test('web stream decodes a split Vietnamese character and closes reader on callback error',async()=>{
 let cancelled=false;const bytes=new TextEncoder().encode('{"type":"token","text":"Đạt"}\n');const split=bytes.findIndex(value=>value===0xc4)+1;
 const api=client(async(url)=>url==='/api/session'?Response.json({token:'a-valid-local-token'}):new Response(new ReadableStream({start(c){c.enqueue(bytes.slice(0,split));c.enqueue(bytes.slice(split));},cancel(){cancelled=true}})));
 const events=[];await assert.rejects(api.streamRequest('/coding/tasks',{},event=>{events.push(event);throw new Error('stop callback')},new AbortController().signal),/stop callback/);
 assert.equal(events[0].text,'Đạt');assert.equal(cancelled,true);
});
