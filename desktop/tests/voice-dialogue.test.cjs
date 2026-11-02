const {test}=require('node:test'),assert=require('node:assert/strict')
const {DesktopDialogue}=require('../dialogue.cjs'),{VoiceTurnDetector}=require('../voice-turn.js'),{completeSpokenReply}=require('../turn-flow.js')
test('PowerPoint confirmation is exact, spoken first, and executes only once after yes',async()=>{
  const executed=[],engine=new DesktopDialogue({resolve:async id=>({exe:id+'.exe',args:[]}),execute:async c=>{executed.push(c.id);return {message:'Opened'}}})
  const question=await engine.respond('Mở PowerPoint');assert.equal(question.message,'Bạn muốn mở PowerPoint phải không?');assert.equal(question.action_id,undefined)
  const ready=await engine.respond('Có');assert.equal(ready.stage,'ready');assert.deepEqual(executed,[])
  const order=[];let finish
  const playing=new Promise(r=>finish=r)
  const flow=completeSpokenReply(ready,{display:()=>order.push('display'),speak:async()=>{order.push('speech');return playing},complete:id=>{order.push('launch');return engine.complete(id)}})
  await Promise.resolve();assert.deepEqual(order,['display','speech']);assert.deepEqual(executed,[])
  finish(true);assert.equal(await flow,true);assert.deepEqual(executed,['powerpoint']);assert.equal(order.indexOf('launch'),2)
  await assert.rejects(engine.complete(ready.action_id))
})
test('No, stale yes, unrelated turn and cancellation cannot open the old application',async()=>{
  let time=1,opens=0;const engine=new DesktopDialogue({resolve:async()=>({exe:'fake.exe'}),execute:()=>opens++,now:()=>time})
  await engine.respond('Mở Word');assert.equal((await engine.respond('không')).stage,'cancelled');assert.equal((await engine.respond('có')).stage,'idle')
  await engine.respond('Mở Excel');time+=120001;assert.equal((await engine.respond('có')).stage,'idle')
  await engine.respond('Mở PowerPoint');await engine.respond('Hôm nay tôi làm gì?');assert.equal((await engine.respond('có')).stage,'idle')
  await engine.respond('Mở Word');const ready=await engine.respond('vâng');engine.cancel();await assert.rejects(engine.complete(ready.action_id));assert.equal(opens,0)
})
test('Missing software gets a factual reply without invoking a language model',async()=>{
  const engine=new DesktopDialogue({resolve:async()=>{throw Error('not installed')},execute:()=>assert.fail()})
  await engine.respond('Mở PowerPoint');const reply=await engine.respond('có');assert.equal(reply.stage,'not_installed');assert.match(reply.message,/PowerPoint chưa được cài đặt/);assert.equal(reply.action_id,undefined)
})
test('Unclear short ASR replies keep confirmation pending and never count as yes',async()=>{
  const engine=new DesktopDialogue({resolve:async()=>({exe:'fake'}),execute:()=>assert.fail()})
  await engine.respond('Mở PowerPoint');const unclear=await engine.respond('Câu.');assert.equal(unclear.stage,'confirmation');assert.equal(unclear.action_id,undefined)
  assert.equal((await engine.respond('có')).stage,'ready')
})
test('Stopping speech or closing the panel prevents opening an acknowledged action',async()=>{
  let opens=0
  assert.equal(await completeSpokenReply({message:'Opening',action_id:'ticket'},{display:()=>{},speak:async()=>false,complete:()=>opens++}),false)
  assert.equal(await completeSpokenReply({message:'Opening',action_id:'ticket'},{display:()=>{},speak:async()=>true,isCurrent:()=>false,complete:()=>opens++}),false)
  assert.equal(opens,0)
})
test('A cancelled slow inventory resolution cannot recreate a launch ticket',async()=>{
  let resolve;const engine=new DesktopDialogue({resolve:()=>new Promise(r=>resolve=r),execute:()=>assert.fail()})
  await engine.respond('Mở PowerPoint');const pending=engine.respond('có');engine.cancel();resolve({exe:'fake.exe'});assert.equal((await pending).stage,'cancelled');assert.equal(engine.actions.size,0)
})
test('Voice endpoint waits for a real short yes, then ends on silence; noise alone never submits',()=>{
  const silent=new VoiceTurnDetector();let result
  for(let n=0;n<400;n++)result=silent.feed(0.001,30)
  assert.equal(result.silence,true);assert.equal(result.finished,false)
  const yes=new VoiceTurnDetector();for(let n=0;n<5;n++)yes.feed(0.06,30)
  for(let n=0;n<24;n++)result=yes.feed(0.001,30)
  assert.equal(result.finished,undefined)
  result=yes.feed(0.001,30);assert.equal(result.finished,true);assert.equal(result.silence,false)
  const click=new VoiceTurnDetector();click.feed(0.1,30);for(let n=0;n<400;n++)result=click.feed(0.001,30)||result;assert.equal(result.silence,true)
})
