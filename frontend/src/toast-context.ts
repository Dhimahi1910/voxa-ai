import { createContext, useContext } from 'react'

export type ToastKind = 'good' | 'bad' | 'info'
export const ToastContext = createContext<(kind: ToastKind, message: string) => void>(() => {})
export const useToast = () => useContext(ToastContext)
