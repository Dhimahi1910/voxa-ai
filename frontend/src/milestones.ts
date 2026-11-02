import type { Milestones } from './api'

export const MILESTONES: { key: keyof Milestones; title: string; text: string }[] = [
  { key: 'calls', title: 'First call recorded', text: 'Veesha has made her first call.' },
  { key: 'connected', title: 'First real conversation', text: 'Someone picked up and talked. That is the whole point.' },
  { key: 'callbacks', title: 'First callback booked', text: 'A customer asked for a better time and Veesha will honour it.' },
  { key: 'meetings', title: 'First meeting booked', text: 'A conversation turned into a meeting. Time to celebrate.' },
  { key: 'emails', title: 'First email sent', text: 'A customer received a follow-up automatically.' },
]
