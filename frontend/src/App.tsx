import { lazy, memo, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { api, initSession, streamChat } from './api'
import { useVoice } from './voice'
import { SpeechSentences, TextBuffer } from './voiceCore'
import { VoiceBar } from './VoiceBar'
import DesktopControls from './DesktopControls'
import Sidebar from './Sidebar'
import { DeferredPanel, ModuleBoundary } from './DeferredPanel'

const WorkspacePanel = lazy(() => import('./WorkspacePanel').then(module => ({ default: module.WorkspacePanel })))
const PersonalProfile = lazy(() => import('./PersonalProfile'))
const Careers = lazy(() => import('./Careers'))
const Coding = lazy(() => import('./Coding'))
const LanguageLearning = lazy(() => import('./LanguageLearning'))
const MarkdownRenderer = lazy(() => import('./Markdown'))

export type Message = { id: string; role: string; content: string; status: string; metadata?: string; citations?: any[]; no_learning?: number; tools?: any[]; truncated?: boolean; continuationQuestion?: string }
const tabs = [{ id: 'chat', name: 'Trò chuyện', icon: 'chat' }, { id: 'research', name: 'Nghiên cứu', icon: 'asterisk' }, { id: 'knowledge', name: 'Tài liệu', icon: 'search' }, { id: 'coding', name: 'Lập trình', icon: 'asterisk' }, { id: 'careers', name: 'Ứng tuyển', icon: 'search' }, { id: 'profile', name: 'Hồ sơ của bạn', icon: 'asterisk' }, { id: 'memory', name: 'Bộ nhớ', icon: 'copy' }, { id: 'training', name: 'Training Studio', icon: 'reset' }, { id: 'settings', name: 'Cài đặt', icon: 'menu' }]
tabs.splice(1, 0, {id:'languages',name:'Học Anh–Nhật',icon:'chat'})
export function Icon({ name, ...props }: { name: string; [key: string]: any }) { return <img src={`/brand/icons/${name}.svg`} alt="" width="20" height="20" {...props} /> }
export const Markdown = memo(function Markdown({ text }: { text: string }) {
  const plainText = <div className="streaming-text">{text}</div>
  return <ModuleBoundary fallback={plainText}><Suspense fallback={plainText}><MarkdownRenderer text={text} /></Suspense></ModuleBoundary>
})
export function ToolResults({ message }: { message: Message }) {
  let events = message.tools || []
  let truncated = message.truncated || false
  if (message.metadata) { try { const data = JSON.parse(message.metadata); if (!events.length) events = data.tools || []; truncated = truncated || data.metrics?.output_truncated } catch { /* legacy metadata */ } }
  return <>{truncated && <div className="notice">Câu trả lời dài đã hết ngân sách của phần này. Nhấn Tiếp tục phần đang dở để viết tiếp; không có hạn mức số lượt hỏi.</div>}{events.filter(e => e.type === 'tool_result').map((event, i) => <details className="tool-receipt" key={i}><summary>Công cụ {event.tool} · {event.status || 'completed'}</summary><pre className="diagnostics">{JSON.stringify(event.result, null, 2)}</pre></details>)}</>
}

export default function App() {
  const [ready, setReady] = useState(false), [tab, setTab] = useState('chat'), [sidebar, setSidebar] = useState(false)
  const [health, setHealth] = useState<any>(null), [config, setConfig] = useState<any>(null)
  const [projectsOpen,setProjectsOpen]=useState(false)
  const [projects, setProjects] = useState<any[]>([]), [projectId, setProjectId] = useState('general')
  const [conversations, setConversations] = useState<any[]>([]), [conversationId, setConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([]), [draft, setDraft] = useState(() => localStorage.getItem('dbot-draft') || '')
  const [busy, setBusy] = useState(false), [stage, setStage] = useState(''), [error, setError] = useState('')
  const [privateMode, setPrivate] = useState(false), [useKnowledge, setUseKnowledge] = useState(true), [mode, setMode] = useState('chat')
  const [selection, setSelection] = useState<any>(null), [feedback, setFeedback] = useState<any>(null), [correction, setCorrection] = useState('')
  const [metrics, setMetrics] = useState<any>(null), [sourceIds, setSourceIds] = useState<string[]>([])
  const [documents, setDocuments] = useState<any[]>([])
  const [performance, setPerformance] = useState('auto'), [activeModel, setActiveModel] = useState('')
  const [responseLength,setResponseLength]=useState('standard'),[tutor,setTutor]=useState<any>(null)
  const busyRef = useRef(false),listVersion=useRef(0),openingVersion=useRef(0)
  const abort = useRef<AbortController | null>(null), activeRequest = useRef(''), bottom = useRef<HTMLDivElement>(null), composer = useRef<HTMLTextAreaElement>(null)
  const voice = useVoice(setDraft, setError, {...config,stt_language:tutor?.language||config?.stt_language,tts_language:tutor?.language||'vi'}, { onUtterance: text => send(text, true), onInterrupt: stop, busy, performance, mode, projectId, useKnowledge, privateMode })
  useEffect(()=>{const desktop=(window as any).dBotDesktop;if(desktop?.setPetMood)desktop.setPetMood(voice.speaking?'speaking':busy?'thinking':voice.callActive?'listening':'idle').catch(()=>{})},[busy,voice.speaking,voice.callActive])
  useEffect(() => { if (tab !== 'chat') { voice.stopConversation(); voice.cancelRecording() } }, [tab])
  useEffect(() => { voice.stopConversation(); voice.cancelRecording() }, [projectId, privateMode])

  const refreshHealth = useCallback(async () => { try { setHealth(await api('/health')) } catch { setHealth(null) } }, [])
  const refreshLists = useCallback(async () => { const version=++listVersion.current;const [chats, sources, projects] = await Promise.all([api('/conversations?all_projects=true'), api(`/sources?project_id=${projectId}`), api('/projects')]);if(version!==listVersion.current)return; setConversations(chats); setDocuments(sources); setProjects(projects) }, [projectId])
  useEffect(() => { initSession().then(async () => { setConfig(await api('/settings')); setProjects(await api('/projects')); setReady(true); await refreshHealth() }).catch(e => setError(e.message)) }, [refreshHealth])
  useEffect(() => { if (!ready) return; refreshLists().catch(e => setError(e.message)) }, [ready, refreshLists])
  useEffect(() => { if (!ready || !(window as any).dBotDesktop) return; const focus = () => { if (!busyRef.current) refreshLists().catch(e => setError(e.message)) }; window.addEventListener('focus', focus); return () => window.removeEventListener('focus', focus) }, [ready, refreshLists])
  useEffect(() => { if (!ready) return; const timer = setInterval(refreshHealth, 15000); return () => clearInterval(timer) }, [ready, refreshHealth])
  useEffect(() => { if (!privateMode) localStorage.setItem('dbot-draft', draft) }, [draft, privateMode])
  useEffect(() => { if (busy) bottom.current?.scrollIntoView({ behavior: 'instant', block: 'end' }) }, [messages, busy])
  useEffect(() => { const close = (event: KeyboardEvent) => { if (event.key === 'Escape') { setSelection(null); setFeedback(null); setSidebar(false) } }; window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close) }, [])

  const newChat = () => { if (busy) return;openingVersion.current++; voice.stopConversation(); voice.cancelRecording(); setConversationId(null); setMessages([]); setMetrics(null); setError(''); setSidebar(false); setTab('chat'); voice.stopAudio();setTutor(null);setMode('chat');if(tutor){setPerformance('auto');setResponseLength('standard')} }
  async function openConversation(id: string, projectOverride?:string) { if (busy) return;const version=++openingVersion.current; voice.stopConversation(); voice.cancelRecording(); const target=projectOverride||conversations.find(row=>row.id===id)?.project_id;const loaded=await api(`/conversations/${id}/messages`);if(version!==openingVersion.current)return;if(target&&target!==projectId){setProjectId(target);setSourceIds([])}setMessages(loaded);let restored=null;for(const row of [...loaded].reverse()){try{restored=JSON.parse(row.metadata||'{}').tutor;if(restored)break}catch{}}setTutor(restored);setMode(restored?'tutor':'chat');if(!restored&&tutor){setPerformance('auto');setResponseLength('standard')}setConversationId(id); setPrivate(false); setTab('chat'); setSidebar(false); setMetrics(null) }
  async function stop() { voice.stopAudio(); abort.current?.abort(); await (window as any).dBotDesktop?.cancel().catch(()=>{}); if (activeRequest.current) await api(`/chat/${activeRequest.current}/cancel`, { method: 'POST' }).catch(() => {}) }

  async function send(text = draft, voiceTurn = false, continueResponse = false) {
    if (!text.trim() || busyRef.current || !ready) return
    busyRef.current = true
    setError(''); setBusy(true); setMetrics(null); voice.stopAudio()
    const requestId = crypto.randomUUID(), assistantId = crypto.randomUUID(), userId = crypto.randomUUID()
    const previous = messages.map(({ role, content }) => ({ role, content }))
    const continuationQuestion = continueResponse ? messages.at(-1)?.continuationQuestion || [...previous].reverse().find(m=>m.role==='user')?.content : undefined
    activeRequest.current = requestId; abort.current = new AbortController()
    setMessages(current => [...current, { id: userId, role: 'user', content: text, status: 'completed' }, { id: assistantId, role: 'assistant', content: '', status: 'running', citations: [], continuationQuestion }])
    let answer = '', serverId = assistantId, userServerId = userId, completed = false
    const buffer = new TextBuffer(content => setMessages(current => current.map(m => m.id === assistantId ? { ...m, content } : m)))
    const sentences = new SpeechSentences()
    const autoRead = voiceTurn || config?.auto_speak
    try {
      const desktop=(window as any).dBotDesktop
      if(desktop){
        const result=await desktop.command(text,{project_id:projectId,conversation_id:conversationId,private:privateMode,source:voiceTurn?'voice':'text'})
        if(result.handled){
          answer=result.message;buffer.flush(answer);setActiveModel('Desktop · lệnh trực tiếp')
          if(result.conversation_id)setConversationId(result.conversation_id)
          if(result.user_message_id)setMessages(current=>current.map(m=>m.id===userId?{...m,id:result.user_message_id}:m))
          setStage('Đang đọc xác nhận')
          const played=await voice.speak(answer,desktop.speak(answer))
          if(!played&&result.action_id)setError('Đã dừng giọng nói; tác vụ chưa được mở. Bạn có thể yêu cầu lại.')
          if(played&&!abort.current?.signal.aborted&&result.action_id){const receipt=await desktop.completeAction(result.action_id);answer+='\n'+receipt.message;buffer.flush(answer)}
          completed=!abort.current?.signal.aborted
          setMessages(current=>current.map(m=>m.id===assistantId?{...m,id:result.message_id||assistantId,status:completed?'completed':'cancelled',metadata:JSON.stringify({answer_source:'desktop_rules'})}:m))
          if(completed){setDraft(current=>current===text?'':current);voice.clearSource()}
          return
        }
      }
      await streamChat({ text, request_id: requestId, project_id: projectId, conversation_id: conversationId, private: privateMode, history: previous.slice(-24), source: voiceTurn || voice.fromVoice ? 'voice' : 'text', use_knowledge: useKnowledge, source_ids: sourceIds, mode, performance, voice_conversation: voiceTurn, response_length:responseLength,continue_response:continueResponse,continuation_question:continuationQuestion,tutor }, event => {
        if (event.request_id !== requestId) return
        if (event.type === 'status') {
          if (event.model) setActiveModel(event.model)
          if (event.status === 'queued') {
            if (event.conversation_id) setConversationId(event.conversation_id)
            serverId = event.message_id; userServerId = event.user_message_id
            setMessages(current => current.map(m => m.id === userId ? { ...m, id: userServerId } : m))
          }
          setStage(({ queued: 'Đang chờ tài nguyên', generating: 'Đang trả lời', warning: event.detail } as any)[event.status] || event.status)
        }
        if (event.type === 'citation') setMessages(current => current.map(m => m.id === assistantId ? { ...m, citations: [...(m.citations || []), event.citation] } : m))
        if (event.type === 'token') { answer += event.text; buffer.push(answer); if (autoRead) sentences.feed(event.text).forEach(voice.enqueueSpeech) }
        if (event.type === 'replace') { answer = event.text; buffer.flush(answer); if (autoRead) voice.stopAudio() }
        if (event.type === 'error') throw new Error(event.message)
        if (event.type === 'tool_proposed') setStage('Đang chạy công cụ: ' + event.tool)
        if (event.type === 'tool_result') { setStage(event.tool === 'manage_memory' ? 'Đã lưu bộ nhớ: ' + event.result.content : 'Công cụ ' + event.tool + ': ' + event.status); setMessages(current => current.map(m => m.id === assistantId ? { ...m, tools: [...(m.tools || []), event] } : m)) }
        if (event.type === 'done') { buffer.flush(answer); completed = event.status === 'completed'; if (completed && autoRead) sentences.flush().forEach(voice.enqueueSpeech); else if (!completed) voice.stopAudio(); setMetrics(event.metrics); setMessages(current => current.map(m => m.id === assistantId ? { ...m, id: serverId, status: event.status, truncated: event.metrics?.output_truncated } : m)) }
      }, abort.current.signal)
      if (completed) { setDraft(current => current === text ? '' : current); voice.clearSource() }
    } catch (e: any) { buffer.flush(answer); voice.stopAudio(); if (e.name !== 'AbortError') setError(e.message); setMessages(current => current.map(m => m.id === assistantId ? { ...m, id: serverId, status: e.name === 'AbortError' ? 'cancelled' : 'error' } : m)) }
    finally { buffer.dispose(); busyRef.current = false; setBusy(false); activeRequest.current = ''; setStage(''); await refreshLists().catch(() => {}); refreshHealth() }
  }

  async function action(kind: string, message: Message) {
    try {
      if (kind === 'copy') { await navigator.clipboard.writeText(message.content); setStage('Đã sao chép'); return }
      if (kind === 'speak') { await voice.speak(message.content); return }
      if (privateMode || !config?.save_history) { setError('Phiên riêng tư/không lưu lịch sử không tạo bộ nhớ, ghi chú hoặc dữ liệu học.'); return }
      if (kind === 'note') { await api('/notes', { method: 'POST', body: JSON.stringify({ project_id: projectId, title: 'Ghi chú từ hội thoại', content: message.content, operation_id: 'message-' + message.id }) }); setStage('Đã lưu ghi chú trong Nghiên cứu'); return }
      if (kind === 'memory') { setFeedback({ kind: 'memory', message }); setCorrection(message.content); return }
      if (kind === 'exclude') { await api(`/messages/${message.id}/exclude-learning`, { method: 'POST' }); setMessages(current => current.map(m => m.id === message.id ? { ...m, no_learning: 1 } : m)); setStage('Đã loại tin nhắn khỏi nguồn dữ liệu học'); return }
      const index = messages.findIndex(m => m.id === message.id)
      setFeedback({ kind, message, question: messages[index - 1]?.content || '' }); setCorrection(kind === 'correct' ? message.content : '')
    } catch (e: any) { setError(e.message) }
  }
  async function saveFeedback() {
    try {
      if (feedback.kind === 'memory') await api('/memories', { method: 'POST', body: JSON.stringify({ project_id: projectId, kind: 'project_fact', content: correction, source_message_id: feedback.message.id, approved: false }) })
      else await api('/feedback', { method: 'POST', body: JSON.stringify({ message_id: feedback.message.id, rating: feedback.kind === 'good' ? 'useful' : 'incorrect', reason: feedback.kind === 'correct' ? 'Bản sửa được người dùng cung cấp' : correction, correction: feedback.kind === 'correct' ? correction : '', question: feedback.question, project_id: projectId }) })
      setFeedback(null); setStage('Đã lưu vào hàng chờ Training Studio')
    } catch (e: any) { setError(e.message) }
  }
  function selectProject(id:string){if(busy)return;voice.stopConversation();voice.stopAudio();newChat();setProjectId(id);setSourceIds([])}
  async function createProject(name:string){const project=await api('/projects',{method:'POST',body:JSON.stringify({name})});setProjects(await api('/projects'));selectProject(project.id)}
  async function updateConversation(id:string,changes:any){
    const row=await api('/conversations/'+id,{method:'PUT',body:JSON.stringify(changes)})
    setConversations(current=>current.map(item=>item.id===id?row:item));setProjects(await api('/projects'))
    if(changes.project_id&&changes.project_id!==projectId){voice.stopConversation();voice.stopAudio();setProjectId(changes.project_id);setSourceIds([])}
    await openConversation(id,changes.project_id)
  }
  async function deleteConversation(id:string){
    if(!confirm('Xóa hội thoại này? Ví dụ và bộ nhớ dẫn nguồn được xử lý theo chính sách dữ liệu.'))return
    await api('/conversations/'+id,{method:'DELETE'});if(conversationId===id)newChat();await refreshLists()
  }
  const currentProject = projects.find(p => p.id === projectId)
  return <div className="app">
    <aside className={`sidebar ${sidebar ? 'open' : ''}`} aria-label="Điều hướng chính">
      <Sidebar tabs={tabs} tab={tab} busy={busy} userName={config?.user_name||'Bạn'} projects={projects} projectId={projectId} conversations={conversations} conversationId={conversationId} projectsOpen={projectsOpen} setProjectsOpen={setProjectsOpen} onNew={newChat} onTab={value=>{setTab(value);setSidebar(false);setError('')}} onProject={selectProject} onCreateProject={createProject} onOpen={openConversation} onUpdate={updateConversation} onDelete={deleteConversation} onError={setError}/>
    </aside>
    {sidebar && <button aria-label="Đóng menu" className="scrim" onClick={() => setSidebar(false)} />}
    <main>
      <header className="topbar"><button className="mobile-menu" aria-label="Mở menu" onClick={() => setSidebar(!sidebar)}><Icon name="menu" /></button><div className="breadcrumb"><span>KHÔNG GIAN LÀM VIỆC</span><span>/</span><button className="current-project" aria-label="Mở danh sách dự án" onClick={()=>{setProjectsOpen(true);setSidebar(true)}}>{currentProject?.name||'Dự án'} <span>▾</span></button></div><DesktopControls /><button className="local-status" onClick={() => setTab('settings')}><span className={`status-dot ${health?.model_ready ? 'online' : ''}`} />{health?.model_ready ? 'LOCAL SẴN SÀNG' : health ? 'CẦN THIẾT LẬP' : 'ĐANG KẾT NỐI'}</button></header>
      {error && <div className="error-banner" role="alert"><strong>Không thể hoàn tất.</strong> {error}<button aria-label="Đóng thông báo" onClick={() => setError('')}><Icon name="close" /></button></div>}
      {tab !== 'chat' ? <DeferredPanel key={tab}>{tab === 'languages' ? <LanguageLearning projectId={projectId} onError={setError} onStart={(context,text)=>{if(busy)return;voice.stopConversation();voice.stopAudio();setTutor(context);setMode('tutor');setResponseLength('long');setPerformance('quality');setUseKnowledge(false);setConversationId(null);setMessages([]);setDraft(text);setTab('chat')}} /> : tab === 'coding' ? <Coding onError={setError} /> : tab === 'careers' ? <Careers onError={setError} /> : tab === 'profile' ? <PersonalProfile onError={setError} onSave={setConfig} /> : <WorkspacePanel tab={tab} projectId={projectId} config={config} setConfig={setConfig} health={health} refresh={() => { refreshLists(); refreshHealth() }} onError={setError} />}</DeferredPanel> : <>
        {tutor && <div className="study-session"><strong>{tutor.language==='ja'?'日本語':'English'} · {tutor.level} · {tutor.exam} · {tutor.activity}</strong><span>Nhập hoặc nói bài làm để gia sư sửa.</span><button onClick={()=>{setTutor(null);setMode('chat');setPerformance('auto');setResponseLength('standard')}}>Kết thúc buổi học</button></div>}
        <div className="chat-scroll">
          {!messages.length ? <section className="welcome"><div className="eyebrow"><span className="hairline" /> OBSERVE / QUESTION / BUILD / REFINE</div><h1>Từ một câu hỏi,<br />đến điều <em>có thể kiểm chứng.</em></h1><p>Chào {config?.user_name || 'Bạn'}. Mình là D-bot, cùng bạn đọc hiểu,<br className="desktop-break" /> phân tích và phát triển những ý tưởng nghiên cứu.</p><div className="suggestions">{[{ tag: '01 / ĐỌC HIỂU', title: 'Đi sâu vào tài liệu', desc: 'Tóm tắt phương pháp, giả định và giới hạn.', text: 'Hãy giúp tôi đọc một tài liệu nghiên cứu. Tôi cần cung cấp những gì?' }, { tag: '02 / KỸ THUẬT', title: 'Gỡ một nút thắt', desc: 'Phân tích hệ thống, code và thuật toán.', text: 'Khi hệ điều khiển PID bị dao động, tôi nên kiểm tra theo thứ tự nào?' }, { tag: '03 / KHÁM PHÁ', title: 'Lên kế hoạch thử nghiệm', desc: 'Từ giả thuyết đến phép đo có ý nghĩa.', text: 'Giúp tôi lập khung kế hoạch thử nghiệm robot: câu hỏi, baseline, biến và chỉ số cần đo.' }].map(item => <button key={item.tag} onClick={() => { setDraft(item.text); composer.current?.focus() }}><small>{item.tag}</small><strong>{item.title}<Icon name="arrow-up-right" /></strong><span>{item.desc}</span></button>)}</div><div className="welcome-foot"><Icon name="asterisk" /><span>Dữ kiện rõ ràng. Giả định minh bạch. Luôn có bước kiểm chứng.</span></div></section> : <div className="messages" aria-live="polite" aria-busy={busy}>{messages.map(message => { let refs = message.citations; if (!refs && message.metadata) { try { refs = JSON.parse(message.metadata).citations } catch { /* older records */ } } return <article key={message.id} className={`message ${message.role}`}><div className="message-label">{message.role === 'user' ? config?.user_name || 'Bạn' : <><Icon name="asterisk" /> D-bot</>}<small>{message.status === 'cancelled' ? 'Đã dừng' : message.status === 'error' ? 'Có lỗi' : message.status === 'interrupted' ? 'Gián đoạn do khởi động lại' : ''}</small></div><div className="message-content">{message.role === 'user' ? <p>{message.content}</p> : message.content ? message.status === 'running' ? <div className="streaming-text">{message.content}</div> : <Markdown text={message.content} /> : <div className="thinking">{stage || 'Đang chuẩn bị'}<span>…</span></div>}{!!refs?.length && <div className="citations">{refs.map((c: any) => <button key={c.label} onClick={() => setSelection(c)}>[{c.label}] {c.filename} · {c.active === false ? 'nguồn đã xóa/đổi · ' : ''}{c.location}</button>)}</div>}<ToolResults message={message} />{message.role==='assistant' && message.id===messages.at(-1)?.id && (message.truncated || (()=>{try{return JSON.parse(message.metadata||'{}').metrics?.output_truncated}catch{return false}})()) && <button disabled={busy} onClick={()=>send('Tiếp tục câu trả lời đang dở.',false,true)}>Tiếp tục phần đang dở</button>}{message.role === 'assistant' && message.content && message.status !== 'running' && <div className="message-actions"><button onClick={() => action('copy', message)} title="Sao chép"><Icon name="copy" /></button><button onClick={() => action('speak', message)} title="Đọc bằng giọng local"><Icon name="play" /></button><button onClick={() => action('good', message)}>Hữu ích</button><button onClick={() => action('bad', message)}>Chưa đúng</button><button onClick={() => action('correct', message)}>Sửa</button><button onClick={() => action('note', message)}>Lưu ghi chú</button><button onClick={() => action('memory', message)}>Đề xuất nhớ</button><button disabled={!!message.no_learning} onClick={() => action('exclude', message)}>{message.no_learning ? 'Đã loại học' : 'Không dùng học'}</button></div>}</div></article> })}<div ref={bottom} /></div>}
        </div>
        <div className="composer-wrap"><VoiceBar voice={voice} disabled={!ready || busy || voice.recording || voice.transcribing} /><div className="chat-options"><select aria-label="Ưu tiên phản hồi" disabled={busy} value={performance} onChange={e => setPerformance(e.target.value)}><option value="auto">Tự động: chat nhanh / nghiên cứu mạnh</option><option value="fast">Model chat · {config?.fast_model}</option><option value="quality">Chuyên sâu · {config?.model}</option></select><select aria-label="Độ dài trả lời" value={responseLength} onChange={e=>setResponseLength(e.target.value)}><option value="short">Ngắn gọn</option><option value="standard">Đầy đủ</option><option value="long">Giải thích dài / bài học</option></select><select aria-label="Chế độ nghiên cứu" value={mode} onChange={e => setMode(e.target.value)}><option value="chat">Chat thường</option><option value="tutor">Gia sư Anh–Nhật</option><option value="read">Đọc hiểu tài liệu</option><option value="technical">Hỗ trợ kỹ thuật</option><option value="compare">So sánh nghiên cứu</option><option value="planner">Research Planner</option><option value="log">Research Log</option></select><label><input type="checkbox" checked={useKnowledge} onChange={e => setUseKnowledge(e.target.checked)} />Dùng tài liệu</label><label className="private-switch"><input type="checkbox" checked={privateMode} disabled={busy} onChange={e => { setPrivate(e.target.checked); setMessages([]); setConversationId(null); setDraft(''); localStorage.removeItem('dbot-draft'); voice.stopAudio() }} />Phiên riêng tư</label>{documents.length > 0 && <select aria-label="Phạm vi tài liệu" value={sourceIds[0] || ''} onChange={e => setSourceIds(e.target.value ? [e.target.value] : [])}><option value="">Tất cả tài liệu dự án</option>{documents.filter(d => d.status === 'ready').map(d => <option key={d.id} value={d.id}>{d.filename}</option>)}</select>}</div>
          <div className={`composer ${voice.callActive ? 'recording' : ''}`}><textarea ref={composer} aria-label="Tin nhắn cho D-bot" placeholder={voice.callActive ? 'Nói rồi dừng khoảng 1 giây để tự gửi.' : 'Đặt câu hỏi, chia sẻ một ý tưởng, hoặc bắt đầu nghiên cứu…'} value={draft} onChange={e => setDraft(e.target.value)} rows={2} maxLength={16000} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) { e.preventDefault(); send() } }} /><div className="composer-tools"><div><button title="Thêm tài liệu" onClick={() => setTab('knowledge')}><Icon name="plus" /></button><span className="model-name">{activeModel || (performance === 'quality' || mode !== 'chat' ? config?.model : config?.fast_model) || 'Model local'}</span></div><div>{(voice.speaking || voice.synthesizing) && <button onClick={voice.stopAudio}>Ngắt giọng</button>}<button className={voice.callActive ? 'mic active' : 'mic'} disabled={!ready || (busy || voice.transcribing) && !voice.callActive} onClick={voice.callActive ? () => voice.stopConversation() : voice.startConversation} aria-label={voice.callActive ? 'Kết thúc trò chuyện' : 'Bắt đầu trò chuyện tự động'}>{voice.callActive ? '■ Kết thúc' : voice.transcribing ? 'Đang chép lời…' : '♩ Mic'}</button>{busy ? <button className="send" onClick={stop} aria-label="Dừng trả lời">■</button> : <button className="send" onClick={() => send()} disabled={!draft.trim() || !ready} aria-label="Gửi tin nhắn"><Icon name="arrow-right" /></button>}</div></div></div>
          <div className="composer-caption"><span>{voice.callActive ? 'Mic đang bật · tự gửi transcript · Kết thúc để tắt mic' : privateMode ? 'Riêng tư: không lưu chat, bộ nhớ hay dữ liệu học. Transcript mic được sửa trước gửi.' : voice.fromVoice ? 'Transcript đã sẵn sàng. Sửa lại trước khi gửi.' : 'Enter để gửi · Shift + Enter xuống dòng'}</span><span>{metrics?.first_token_seconds != null ? `Token đầu: ${metrics.first_token_seconds.toFixed(1)}s · Tổng: ${metrics.elapsed_seconds.toFixed(1)}s` : busy ? stage : 'LOCAL · KHÔNG CÓ TÌM WEB'}</span></div></div>
      </>}
      <footer className="statusbar"><span><span className="status-dot" /> blueDStar Research Studio</span><span>{currentProject?.name} <i>/</i> {health?.offline ? 'OFFLINE MODE' : 'LOCAL PROVIDER'} <i>/</i> {busy ? 'ĐANG XỬ LÝ' : 'SẴN SÀNG'}</span></footer>
    </main>
    {selection && <div className="modal-backdrop" onClick={() => setSelection(null)}><section className="modal" role="dialog" aria-modal="true" aria-label="Đoạn nguồn được truy xuất" onClick={e => e.stopPropagation()}><button className="modal-close" onClick={() => setSelection(null)} aria-label="Đóng"><Icon name="close" /></button><p className="section-label">NGUỒN [{selection.label}]</p><h2>{selection.filename}</h2><p>{selection.location} · v{selection.version} · {selection.hash?.slice(0, 12)}</p><pre className="source-excerpt">{selection.text}</pre><button onClick={async () => { try { const data = await api(`/sources/${selection.source_id}`); setSelection({ ...selection, text: data.excerpts.map((e: any) => `${e.location}\n${e.content}`).join('\n\n') }) } catch (e: any) { setError('Nguồn đã bị xóa/đổi: ' + e.message) } }}>Kiểm tra nguồn còn hoạt động</button></section></div>}
    {feedback && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-label="Phản hồi và chỉnh sửa"><button className="modal-close" onClick={() => setFeedback(null)} aria-label="Đóng"><Icon name="close" /></button><p className="section-label">DẠY D-BOT / {currentProject?.name}</p><h2>{feedback.kind === 'correct' ? 'Câu trả lời bạn mong muốn' : feedback.kind === 'memory' ? 'Đề xuất bộ nhớ' : 'Phản hồi của bạn'}</h2><p>Đưa vào hàng chờ duyệt. Chưa thay đổi trọng số mô hình.</p><textarea aria-label="Nội dung phản hồi" rows={10} value={correction} onChange={e => setCorrection(e.target.value)} /><button className="primary" onClick={saveFeedback}>Lưu vào hàng chờ</button></section></div>}
  </div>
}
