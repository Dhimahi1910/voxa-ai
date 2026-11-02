import type { ReactNode } from 'react'

export const VeeshaAvatar = ({ size = 34 }: { size?: number }) => <span className="v-avatar" style={{ width: size, height: size }} aria-hidden="true" />

/** Veesha's speech bubble: short friendly tips and empty states. */
export function VeeshaTip({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <div className="v-tip">
      <VeeshaAvatar />
      <div><b>{title ?? 'Veesha'}</b><p>{children}</p></div>
    </div>
  )
}
