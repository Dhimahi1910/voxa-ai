import { useRef, type ReactNode } from 'react'
import { prefersReducedMotion } from '../hooks'

/** Glass card that leans toward the pointer (CSS 3D). Disabled for reduced-motion users. */
export default function Tilt({ children, className = '' }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const move = (e: React.PointerEvent) => {
    const el = ref.current
    if (!el || prefersReducedMotion()) return
    const r = el.getBoundingClientRect()
    const px = (e.clientX - r.left) / r.width - 0.5, py = (e.clientY - r.top) / r.height - 0.5
    el.style.setProperty('--ry', `${(px * 9).toFixed(2)}deg`)
    el.style.setProperty('--rx', `${(-py * 9).toFixed(2)}deg`)
  }
  const leave = () => { ref.current?.style.setProperty('--rx', '0deg'); ref.current?.style.setProperty('--ry', '0deg') }
  return <div ref={ref} className={`glass tilt ${className}`} onPointerMove={move} onPointerLeave={leave}>{children}</div>
}
