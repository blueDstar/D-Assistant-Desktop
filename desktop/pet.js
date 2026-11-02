const desktop=window.dBotDesktop,$=id=>document.getElementById(id)
const chatSurface=!window.location?.search?.includes('surface=pet')
if(document.body.dataset)document.body.dataset.surface=chatSurface?'chat':'pet'
const moods=new Set(['idle','walking','greeting','listening','thinking','speaking','question','happy','error','sleeping'])
let opened=false,state={},busy=false,sessionOn=false,epoch=0,phase='idle',stream=null,context=null,analyser=null,sourceNode=null,recorder=null,frames=[],sampleTimer=null,resumeTimer=null,audio=null,playEnd=null,replyId=null
function status(text){$('status').textContent=text}
function mood(name){if(chatSurface)desktop.setPetMood?.(name)?.catch(()=>{})}
function stopAudio(){const finish=playEnd;playEnd=null;if(audio){audio.pause();URL.revokeObjectURL(audio.src);audio=null}finish?.(false)}
function update(next){const wasOpen=opened;state={...state,...next};if(typeof state.panel==='boolean'){opened=state.panel;$('panel').hidden=!chatSurface||!opened;if(chatSurface&&opened&&!wasOpen){$('question').focus();desktop.prepareVoice().catch(()=>{})}}$('roam').textContent=state.roaming?'Dừng đi lại':'Bật đi lại';$('speed').value=String(state.voiceSpeed||0.85);$('speed-value').textContent=Number(state.voiceSpeed||0.85).toFixed(2)+'×';$('click-through').checked=state.clickThrough!==false;$('input-mode').textContent=state.clickThrough===false?'Có thể nhấp/kéo robot':'Xuyên chuột · mở chat bằng Ctrl+Alt+D hoặc khay';const expression=moods.has(state.petMood)?state.petMood:'idle';$('robot-image').src='expressions/'+expression+'.svg';if(document.body.dataset){document.body.dataset.mood=expression;document.body.dataset.direction=state.direction<0?'left':'right'}document.body.classList.toggle('busy',!!state.busy||busy)}
desktop.onState(update);desktop.state().then(update).catch(e=>status(e.message))
desktop.onReply(value=>{if(phase!=='processing')return;if(replyId&&replyId!==value.request_id)return;replyId=value.request_id;$('answer').textContent=value.text})
function clearCapture(){clearInterval(sampleTimer);sampleTimer=null;if(recorder){recorder.onstop=null;if(recorder.state!=='inactive')recorder.stop();recorder=null}frames=[]}
function stopSession(){sessionOn=false;clearTimeout(resumeTimer);clearCapture();stream?.getTracks().forEach(t=>t.stop());stream=null;sourceNode?.disconnect();sourceNode=null;if(context)context.close().catch(()=>{});context=null;analyser=null;document.body.classList.remove('recording');$('mic').textContent='● Nói';$('finish-utterance').hidden=true}
async function cancel(){epoch++;stopSession();stopAudio();phase='idle';busy=false;mood('idle');$('send').disabled=false;$('stop').hidden=true;await desktop.cancel();status('Đã dừng mic và tác vụ đang chờ.')}
async function panel(value){if(!chatSurface){await desktop.setPanel(value);return}opened=value;$('panel').hidden=!value;await desktop.setPanel(value);if(!value)await cancel();else{$('question').focus();desktop.prepareVoice().catch(()=>{})}}
$('close-panel').onclick=()=>panel(false)
$('main').onclick=()=>desktop.showMain()
$('menu').onclick=()=>desktop.menu()
$('roam').onclick=()=>desktop.setRoaming(!state.roaming).then(update)
$('speed').onchange=()=>desktop.setVoiceSpeed(Number($('speed').value)).then(update).catch(e=>status(e.message))
$('click-through').onchange=()=>desktop.setClickThrough($('click-through').checked).then(update).catch(e=>status(e.message))
$('expression').onchange=()=>desktop.previewPetMood($('expression').value).catch(e=>status(e.message))
$('pet').oncontextmenu=event=>{event.preventDefault();desktop.menu()}
let drag=null
$('pet').onpointerdown=e=>{if(e.button!==0)return;drag={x:e.screenX,y:e.screenY,total:0};$('pet').setPointerCapture(e.pointerId)}
$('pet').onpointermove=e=>{if(!drag)return;const dx=e.screenX-drag.x,dy=e.screenY-drag.y;drag.total+=Math.abs(dx)+Math.abs(dy);drag.x=e.screenX;drag.y=e.screenY;if(drag.total>5)desktop.move(dx,dy)}
$('pet').onpointerup=e=>{if(!drag)return;const click=drag.total<=5;drag=null;$('pet').releasePointerCapture(e.pointerId);if(click)panel(!opened)}
$('pet').onpointercancel=()=>{drag=null}
$('question').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('chat-form').requestSubmit()}}
async function speak(text,version){
  if(!$('read-aloud').checked)return true
  status('Đang chuẩn bị giọng nói…')
  const bytes=await desktop.speak(text.slice(0,4000),state.voiceSpeed||0.85)
  if(!opened||version!==epoch)return false
  stopAudio();audio=new Audio(URL.createObjectURL(new Blob([bytes],{type:'audio/wav'})))
  const done=new Promise(resolve=>{playEnd=resolve;audio.onended=()=>{playEnd=null;const current=audio;audio=null;URL.revokeObjectURL(current.src);mood('idle');resolve(true)};audio.onerror=()=>{stopAudio();mood('error');status('Không phát được giọng nói. Chưa mở tác vụ.');resolve(false)}})
  await audio.play();mood('speaking');status('D-bot đang nói · mic tạm ngừng nhận');return done
}
async function submit(text,origin='text'){
  if(busy||!text.trim())return
  clearCapture();stopAudio();const version=++epoch;busy=true;phase='processing';mood('thinking');replyId=null;$('send').disabled=true;$('finish-utterance').hidden=true;$('stop').hidden=false;status('Đang xử lý…')
  try{
    const result=await desktop.ask(text.trim(),origin)
    if(version!==epoch||!opened)return
    $('heard').textContent='Bạn: '+text;$('heard').hidden=false;$('question').value=''
    const completed=await completeSpokenReply(result,{display:text=>$('answer').textContent=text,speak:text=>speak(text,version),isCurrent:()=>version===epoch&&opened,complete:id=>{status('Đang mở tác vụ…');return desktop.completeAction(id)}})
    if(!completed)return
    mood(result.awaiting_confirmation?'question':'happy')
    status(result.awaiting_confirmation?'Nói “có” để mở, hoặc “không” để hủy.':result.history_warning||'Đã trả lời.')
  }catch(e){if(version===epoch){mood('error');status(e.message.includes('abort')?'Đã dừng.':e.message)}}
  finally{if(version===epoch){busy=false;phase='idle';$('send').disabled=false;document.body.classList.remove('busy');$('stop').hidden=!sessionOn;if(sessionOn&&opened)resumeTimer=setTimeout(listen,350)}}
}
$('chat-form').onsubmit=event=>{event.preventDefault();submit($('question').value,'text')}
$('stop').onclick=cancel
$('finish-utterance').onclick=()=>{if(sessionOn&&!busy&&phase==='listening'&&recorder?.state==='recording'){clearInterval(sampleTimer);sampleTimer=null;phase='transcribing';recorder.stop()}}
function listen(){
  if(!sessionOn||!opened||busy||!stream||!analyser)return
  clearCapture();phase='listening';mood('listening');frames=[];status('Đang nghe · nói rồi dừng khoảng 1 giây');$('mic').textContent='■ Kết thúc';$('finish-utterance').hidden=false;$('stop').hidden=false;document.body.classList.add('recording')
  const version=epoch,detector=new VoiceTurnDetector(),samples=new Float32Array(analyser.fftSize)
  const mime=['audio/webm;codecs=opus','audio/webm'].find(type=>MediaRecorder.isTypeSupported(type));recorder=new MediaRecorder(stream,mime?{mimeType:mime}:undefined)
  recorder.ondataavailable=event=>{if(event.data.size)frames.push(event.data)}
  recorder.onstop=async()=>{
    clearInterval(sampleTimer);sampleTimer=null;const captured=frames;frames=[];recorder=null
    if(version!==epoch||!sessionOn||!opened)return
    busy=true;phase='transcribing';$('finish-utterance').hidden=true;mood('thinking');$('send').disabled=true;status('Đang nhận lời nói…')
    try{
      const bytes=new Uint8Array(await new Blob(captured,{type:mime||'audio/webm'}).arrayBuffer()),result=await desktop.transcribe(bytes)
      if(version!==epoch||!sessionOn||!opened)return
      busy=false;$('send').disabled=false
      if(result.silence||!result.text?.trim()){status('Chưa nghe rõ, bạn nói lại nhé.');resumeTimer=setTimeout(listen,350);return}
      await submit(result.text,'voice')
    }catch(e){if(version===epoch){busy=false;phase='idle';$('send').disabled=false;status(e.message);if(sessionOn)resumeTimer=setTimeout(listen,700)}}
  }
  recorder.start();let previous=performance.now()
  sampleTimer=setInterval(()=>{
    if(!recorder||phase!=='listening')return
    analyser.getFloatTimeDomainData(samples);let energy=0;for(const sample of samples)energy+=sample*sample
    const now=performance.now(),turn=detector.feed(Math.sqrt(energy/samples.length),Math.min(150,now-previous));previous=now
    if(turn?.started)status('Đang nghe bạn nói…')
    if(turn?.silence){clearCapture();phase='idle';status('Chưa có tiếng nói · mic vẫn sẵn sàng');resumeTimer=setTimeout(listen,300)}
    else if(turn?.finished){clearInterval(sampleTimer);sampleTimer=null;phase='transcribing';recorder.stop()}
  },30)
}
$('mic').onclick=async()=>{
  if(sessionOn){await cancel();return}
  if(busy)return
  const version=++epoch;sessionOn=true;stopAudio();$('mic').textContent='■ Kết thúc';status('Đang mở mic…')
  desktop.prepareVoice().catch(()=>{})
  try{
    const media=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false})
    if(version!==epoch||!sessionOn||!opened){media.getTracks().forEach(t=>t.stop());return}
    stream=media;context=new AudioContext();await context.resume();if(version!==epoch||!sessionOn)return;analyser=context.createAnalyser();analyser.fftSize=1024;sourceNode=context.createMediaStreamSource(stream);const muted=context.createGain();muted.gain.value=0;if(context.createBiquadFilter){const filter=context.createBiquadFilter();filter.type='highpass';filter.frequency.value=120;sourceNode.connect(filter);filter.connect(analyser)}else sourceNode.connect(analyser);analyser.connect(muted);muted.connect(context.destination);listen()
  }catch(e){if(version===epoch){stopSession();status('Không mở được mic: '+e.message)}}
}
window.addEventListener('beforeunload',()=>{stopSession();stopAudio()})
document.addEventListener('visibilitychange',()=>{if(chatSurface&&document.hidden)cancel()})
