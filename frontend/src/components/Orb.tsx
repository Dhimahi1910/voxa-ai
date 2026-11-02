import { lazy, Suspense } from 'react'

// Three.js is large, so the orb loads as its own chunk and the page renders immediately.
const Orb3D = lazy(() => import('./Orb3D'))

export default function Orb({ intensity }: { intensity?: number }) {
  return (
    <Suspense fallback={<div className="orb-wrap" aria-hidden="true"><div className="orb-fallback" /></div>}>
      <Orb3D intensity={intensity} />
    </Suspense>
  )
}
