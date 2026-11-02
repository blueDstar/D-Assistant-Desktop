import { Component, Suspense, type ReactNode } from 'react'

/** A failed optional chunk must never take down chat or discard its draft. */
export class ModuleBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

export function DeferredPanel({ children }: { children: ReactNode }) {
  return <ModuleBoundary fallback={<section className="panel" role="alert">
    <h2>Không tải được chức năng</h2>
    <p>Bạn vẫn có thể quay về Trò chuyện. Nếu cần tải lại ứng dụng, hãy sao chép nội dung chưa lưu trước.</p>
  </section>}>
    <Suspense fallback={<section className="panel" role="status" aria-live="polite">Đang mở chức năng…</section>}>
      {children}
    </Suspense>
  </ModuleBoundary>
}
