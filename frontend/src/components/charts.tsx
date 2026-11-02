// Tiny dependency-free SVG charts.
const PALETTE: Record<string, string> = {
  Connected: '#3ddc97', Rescheduled: '#6bb8ff', 'Not Received': '#ffc861', 'Not Responded': '#ff9f6b', Ended: '#ff7ad9', Pending: '#6b7399',
}

export function Donut({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data).filter(([, v]) => v > 0)
  const total = entries.reduce((a, [, v]) => a + v, 0)
  const R = 52, C = 2 * Math.PI * R
  let offset = 0
  return (
    <div className="donut">
      <svg viewBox="0 0 140 140" role="img" aria-label="Outcome breakdown">
        <circle cx="70" cy="70" r={R} fill="none" stroke="rgba(255,255,255,.07)" strokeWidth="16" />
        {entries.map(([k, v]) => {
          const len = (v / total) * C
          const el = <circle key={k} cx="70" cy="70" r={R} fill="none" stroke={PALETTE[k] ?? '#8b6cff'} strokeWidth="16"
            strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-offset} transform="rotate(-90 70 70)" />
          offset += len
          return el
        })}
        <text x="70" y="68" textAnchor="middle" className="donut-n">{total}</text>
        <text x="70" y="86" textAnchor="middle" className="donut-l">calls</text>
      </svg>
      <ul className="legend">
        {entries.length === 0 && <li className="muted">No calls in this period.</li>}
        {entries.map(([k, v]) => <li key={k}><i style={{ background: PALETTE[k] ?? '#8b6cff' }} />{k}<b>{v}</b></li>)}
      </ul>
    </div>
  )
}

export function Funnel({ steps }: { steps: { label: string; value: number }[] }) {
  const max = Math.max(1, ...steps.map(s => s.value))
  return (
    <div className="funnel">
      {steps.map((s, i) => (
        <div key={s.label} className="funnel-row">
          <span>{s.label}</span>
          <div className="bar"><div style={{ width: `${(s.value / max) * 100}%`, animationDelay: `${i * 90}ms` }} /></div>
          <b>{s.value}</b>
        </div>
      ))}
    </div>
  )
}

export function HourHeat({ hours }: { hours: { hour: number; calls: number; connected: number }[] }) {
  const max = Math.max(1, ...hours.map(h => h.calls))
  return (
    <div className="heat" role="img" aria-label="Calls by hour of day">
      {hours.map(h => (
        <div key={h.hour} className="heat-cell" title={`${String(h.hour).padStart(2, '0')}:00 · ${h.calls} calls, ${h.connected} connected`}
          style={{ ['--a' as string]: h.calls / max }}>
          <small>{h.hour % 3 === 0 ? String(h.hour).padStart(2, '0') : ''}</small>
        </div>
      ))}
    </div>
  )
}

export function Spark({ points }: { points: { date: string; calls: number; connected: number }[] }) {
  const W = 300, H = 70, max = Math.max(1, ...points.map(p => p.calls))
  const x = (i: number) => (points.length < 2 ? W / 2 : (i / (points.length - 1)) * (W - 8) + 4)
  const y = (v: number) => H - 6 - (v / max) * (H - 14)
  const line = (key: 'calls' | 'connected') => points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="spark" role="img" aria-label="Calls per day">
      <path d={`${line('calls')} L${x(points.length - 1)},${H} L${x(0)},${H} Z`} fill="url(#sg)" opacity=".55" />
      <defs><linearGradient id="sg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#8b6cff" /><stop offset="1" stopColor="#8b6cff" stopOpacity="0" /></linearGradient></defs>
      <path d={line('calls')} fill="none" stroke="#8b6cff" strokeWidth="2" />
      <path d={line('connected')} fill="none" stroke="#2de2c9" strokeWidth="2" />
    </svg>
  )
}
