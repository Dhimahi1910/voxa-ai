// Small per-browser conveniences (welcome seen, tour done, milestones seen). Always wrapped: storage can be blocked.
export const readJson = <T,>(key: string, fallback: T): T => {
  try { const v = localStorage.getItem(key); return v ? (JSON.parse(v) as T) : fallback } catch { return fallback }
}
export const writeJson = (key: string, value: unknown) => {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* storage unavailable */ }
}
export const flag = (key: string) => readJson<boolean>(`voxai:${key}`, false)
export const setFlag = (key: string, v = true) => writeJson(`voxai:${key}`, v)
