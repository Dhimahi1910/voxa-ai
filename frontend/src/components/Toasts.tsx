import { useCallback, useState, type ReactNode } from 'react'
import { ToastContext, type ToastKind } from '../toast-context'

interface Item { id: number; kind: ToastKind; message: string }

export default function Toasts({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Item[]>([])
  const push = useCallback((kind: ToastKind, message: string) => {
    const id = Date.now() + Math.random()
    setItems(list => [...list, { id, kind, message }])
    setTimeout(() => setItems(list => list.filter(i => i.id !== id)), 5000)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">{items.map(i => <div key={i.id} className={`toast ${i.kind}`}>{i.message}</div>)}</div>
    </ToastContext.Provider>
  )
}
