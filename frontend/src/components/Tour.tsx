import { useEffect, useLayoutEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { VeeshaAvatar } from './Veesha'

export interface TourStep { selector: string; title: string; text: string }

/** Spotlight tour: dims the page, cuts a hole around the target, and explains it. Esc / arrows work. */
export default function Tour({ steps, onClose }: { steps: TourStep[]; onClose: () => void }) {
  const [i, setI] = useState(0)
  const [rect, setRect] = useState<DOMRect | null>(null)
  const step = steps[i]

  useLayoutEffect(() => {
    const el = document.querySelector(step.selector)
    if (!el) { setRect(null); return }
    el.scrollIntoView({ block: 'center', behavior: 'smooth' })
    const update = () => setRect(el.getBoundingClientRect())
    update()
    const t = setTimeout(update, 400)
    window.addEventListener('resize', update); window.addEventListener('scroll', update, true)
    return () => { clearTimeout(t); window.removeEventListener('resize', update); window.removeEventListener('scroll', update, true) }
  }, [step.selector])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowRight') setI(n => Math.min(n + 1, steps.length - 1))
      if (e.key === 'ArrowLeft') setI(n => Math.max(n - 1, 0))
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose, steps.length])

  const pad = 8
  const below = rect ? rect.bottom + 230 < innerHeight : true
  const cardStyle: React.CSSProperties = rect
    ? { top: below ? rect.bottom + pad + 10 : undefined, bottom: below ? undefined : innerHeight - rect.top + pad + 10,
        left: Math.min(Math.max(12, rect.left), innerWidth - 372) }
    : { top: '35%', left: '50%', transform: 'translateX(-50%)' }
  const last = i === steps.length - 1

  return createPortal(
    <div className="tour" role="dialog" aria-label="Product tour">
      {rect
        ? <div className="tour-hole" style={{ top: rect.top - pad, left: rect.left - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 }} />
        : <div className="tour-dim" />}
      <div className="glass tour-card" style={cardStyle}>
        <div className="row" style={{ flexWrap: 'nowrap', alignItems: 'flex-start', gap: '.8rem' }}>
          <VeeshaAvatar size={38} />
          <div><h3>{step.title}</h3><p className="muted" style={{ margin: '.25rem 0 0' }}>{step.text}</p></div>
        </div>
        <div className="row" style={{ justifyContent: 'space-between', marginTop: '.9rem' }}>
          <span className="faint">{i + 1} / {steps.length}</span>
          <div className="row">
            <button className="ghost small" onClick={onClose}>{last ? 'Close' : 'Skip'}</button>
            {i > 0 && <button className="small" onClick={() => setI(i - 1)}>Back</button>}
            <button className="primary small" onClick={() => (last ? onClose() : setI(i + 1))}>{last ? 'Done' : 'Next'}</button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}
