import { useState } from 'react'
import Modal from './Modal'
import { VeeshaAvatar } from './Veesha'

const SLIDES = [
  { title: "Hi, I'm Veesha", body: 'I make your outbound calls and keep track of every conversation. This console is where you watch, steer and practise.' },
  { title: 'How it works', body: 'Every day I call the customers who are due. Afterwards I read the conversation, pull out what they need, and decide the next step: a retry, a callback, a meeting, or leaving them alone.' },
  { title: 'Safe by default', body: 'Right now calls are simulated and emails are off, so nothing real happens until you flip the switches on the server. The Practice Room lets you rehearse every situation first.' },
]

export default function Welcome({ onTour, onClose }: { onTour: () => void; onClose: () => void }) {
  const [i, setI] = useState(0)
  const last = i === SLIDES.length - 1
  return (
    <Modal title={SLIDES[i].title} onClose={onClose}>
      <div className="row" style={{ alignItems: 'flex-start', gap: '1rem', flexWrap: 'nowrap' }}>
        <VeeshaAvatar size={52} />
        <p className="muted" style={{ margin: 0 }}>{SLIDES[i].body}</p>
      </div>
      <div className="dots" aria-hidden="true">{SLIDES.map((_, n) => <i key={n} className={n === i ? 'on' : ''} />)}</div>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <button className="ghost" onClick={onClose}>Skip</button>
        <div className="row">
          {i > 0 && <button onClick={() => setI(i - 1)}>Back</button>}
          {last ? <button className="primary" onClick={onTour}>Show me around</button> : <button className="primary" onClick={() => setI(i + 1)}>Next</button>}
        </div>
      </div>
    </Modal>
  )
}
