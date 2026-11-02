import { createContext, useContext } from 'react'
import type { Settings } from './api'

export const SettingsContext = createContext<Settings | null>(null)
export const useSettings = () => useContext(SettingsContext)
