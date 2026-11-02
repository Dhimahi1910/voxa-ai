import { prefersReducedMotion } from './hooks'

const COLORS = ['#8b6cff', '#2de2c9', '#ff7ad9', '#ffc861', '#6bb8ff', '#ffffff']

/** A short, tasteful burst from the top-centre of the screen. Skipped for reduced-motion users. */
export function fireConfetti(count = 110) {
  if (prefersReducedMotion()) return
  const canvas = Object.assign(document.createElement('canvas'), { width: innerWidth, height: innerHeight })
  Object.assign(canvas.style, { position: 'fixed', inset: '0', pointerEvents: 'none', zIndex: '80' })
  document.body.appendChild(canvas)
  const ctx = canvas.getContext('2d')
  if (!ctx) { canvas.remove(); return }
  const parts = Array.from({ length: count }, () => ({
    x: innerWidth / 2 + (Math.random() - 0.5) * 160, y: innerHeight * 0.18,
    vx: (Math.random() - 0.5) * 11, vy: -Math.random() * 9 - 2, r: Math.random() * 5 + 3,
    rot: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4, c: COLORS[Math.floor(Math.random() * COLORS.length)],
  }))
  const t0 = performance.now()
  const frame = (now: number) => {
    const t = now - t0
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    for (const p of parts) {
      p.vy += 0.28; p.x += p.vx; p.y += p.vy; p.rot += p.vr; p.vx *= 0.99
      ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.globalAlpha = Math.max(0, 1 - t / 2600)
      ctx.fillStyle = p.c; ctx.fillRect(-p.r, -p.r / 2, p.r * 2, p.r); ctx.restore()
    }
    if (t < 2600) requestAnimationFrame(frame); else canvas.remove()
  }
  requestAnimationFrame(frame)
}
