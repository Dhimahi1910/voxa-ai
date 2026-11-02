import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

/** Accessible dialog: Escape and backdrop click close it; focus moves inside on open. */
export default function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    box.current?.querySelector<HTMLElement>('input, button')?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('keydown', onKey); prev?.focus() }
  }, [onClose])
  // Rendered into <body>: an ancestor with backdrop-filter would otherwise trap this fixed overlay inside its own box.
  return createPortal(
    <div className="backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="glass modal" role="dialog" aria-modal="true" aria-label={title} ref={box}>
        <h2>{title}</h2>
        {children}
      </div>
    </div>,
    document.body,
  )
}

export function Confirm({ title, children, confirmLabel, danger, busy, onConfirm, onClose }: {
  title: string; children: ReactNode; confirmLabel: string; danger?: boolean; busy?: boolean
  onConfirm: () => void; onClose: () => void
}) {
  return (
    <Modal title={title} onClose={onClose}>
      <div className="muted">{children}</div>
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button onClick={onClose} disabled={busy}>Cancel</button>
        <button className={danger ? 'danger' : 'primary'} onClick={onConfirm} disabled={busy}>{busy ? 'Working…' : confirmLabel}</button>
      </div>
    </Modal>
  )
}
