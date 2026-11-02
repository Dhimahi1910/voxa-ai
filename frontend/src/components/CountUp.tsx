import { useEffect, useState } from 'react'
import { prefersReducedMotion } from '../hooks'

export default function CountUp({ value }: { value: number }) {
  const [shown, setShown] = useState(0)
  useEffect(() => {
    if (prefersReducedMotion() || value === 0) { setShown(value); return }
    let raf = 0
    const start = performance.now(), dur = 800
    const tick = (now: number) => {
      const t = Math.min((now - start) / dur, 1)
      setShown(Math.round(value * (1 - Math.pow(1 - t, 3))))
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value])
  return <>{shown}</>
}
