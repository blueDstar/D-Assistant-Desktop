import { useEffect, useState } from 'react'
import { api } from './api'

export default function PersonalProfile({ onError, onSave }: { onError: (text: string) => void; onSave: (config: any) => void }) {
  const [record, setRecord] = useState<any>(null), [form, setForm] = useState<any>(null), [versions, setVersions] = useState<any[]>([]), [notice, setNotice] = useState('')
  async function load() { const [current, history] = await Promise.all([api('/profile'), api('/profile/versions')]); setRecord(current); setForm(current.profile); setVersions(history) }
  useEffect(() => { load().catch(e => onError(e.message)) }, [])
  const change = (key: string, value: any) => setForm({ ...form, [key]: value })
  async function perform(action: () => Promise<any>, message: string) { try { await action(); await load(); onSave(await api('/settings')); setNotice(message) } catch (e: any) { onError(e.message) } }
  if (!form) return <div className="workspace-page">Đang đọc hồ sơ local…</div>
  return <div className="workspace-page"><div className="page-heading"><p className="eyebrow">D-BOT / CÁ NHÂN HÓA</p><h1>Trợ lý của bạn.</h1><p>Hồ sơ được dùng làm ngữ cảnh qua các cuộc trò chuyện. Bạn có thể sửa, tắt, khôi phục hoặc xóa; chưa thay đổi trọng số model, chưa xác thực người nói bằng giọng.</p></div>
    {notice && <p className="notice" role="status">{notice}</p>}
    <div className="panel"><h3>Hồ sơ cá nhân · phiên bản {record.version}</h3><label><input type="checkbox" checked={form.enabled} onChange={e => change('enabled', e.target.checked)} />Dùng hồ sơ này khi trả lời (kể cả phiên chat riêng tư)</label>
      {([['name', 'Tên bạn muốn được gọi', 80, 1], ['address_style', 'Cách xưng hô', 240, 2], ['bio', 'Về bạn', 2000, 5], ['goals', 'Mục tiêu', 1500, 4], ['interests', 'Mối quan tâm', 600, 3], ['response_preferences', 'Cách bạn muốn được hỗ trợ', 1000, 4], ['portfolio_notes', 'Dự án, kinh nghiệm và giới hạn bằng chứng từ portfolio', 12000, 15]] as const).map(([key, label, maxLength, rows]) => <label className="field" key={key}>{label}<textarea value={form[key]} maxLength={maxLength} rows={rows} onChange={e => change(key, e.target.value)} /></label>)}
      <label className="field">Nguồn (mỗi dòng một URL)<textarea rows={3} value={form.source_urls.join('\n')} onChange={e => change('source_urls', e.target.value.split('\n').filter(Boolean))} /></label>
      <p className="muted small">Bản nguồn đọc: {form.source_checked_at || 'Chưa ghi ngày'}. Không tự truy cập lại portfolio. Bản lưu nguồn nằm trong data/profile_sources.</p>
      <div className="row-actions"><button className="primary" onClick={() => perform(() => api('/profile', { method: 'PUT', body: JSON.stringify(form) }), 'Đã lưu. Hồ sơ có hiệu lực ở lượt trả lời tiếp theo.')}>Lưu hồ sơ</button><button onClick={() => { if (confirm('Xóa hồ sơ, các phiên bản và bản nguồn portfolio đã tải? Tên trong Cài đặt, chat, bộ nhớ, export và backup cần quản lý riêng.')) void perform(() => api('/profile', { method: 'DELETE' }), 'Đã xóa hồ sơ và bản nguồn đã tải. Có thể sửa tên trong Cài đặt.') }}>Xóa hồ sơ & bản nguồn</button></div>
    </div>
    {versions.length > 0 && <div className="panel"><h3>Khôi phục phiên bản</h3>{versions.slice().reverse().map(v => <div className="row-actions" key={v.version}><span>v{v.version} · {v.updated_at} · {v.profile.name}</span><button onClick={() => perform(() => api(`/profile/restore/${v.version}`, { method: 'POST' }), 'Đã khôi phục thành phiên bản mới.')}>Khôi phục</button></div>)}</div>}
  </div>
}
