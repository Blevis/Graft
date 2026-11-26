import { useState, type FormEvent } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useRecordTraining } from '@/lib/api'
import { useWorkspace } from './context'
import type { Action } from './model'

export default function PlanningDialog({
  open,
  onOpenChange,
  add,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  add: (item: Action) => void
}) {
  const w = useWorkspace(),
    session = w.screen.id === 16
  const [ref, setRef] = useState(w.person?.ref ?? w.data.people[0]?.ref ?? ''),
    [title, setTitle] = useState(''),
    [owner, setOwner] = useState(''),
    [date, setDate] = useState(w.date),
    [message, setMessage] = useState('')
  const training = useRecordTraining(ref)
  const save = (e: FormEvent) => {
    e.preventDefault()
    if (!title.trim() || !ref) return
    if (w.demo) {
      try {
        add({ title: title.trim(), ref, owner: owner.trim() || 'Unconfirmed', date, done: false })
        onOpenChange(false)
      } catch {
        setMessage('This browser could not save the plan.')
      }
    } else if (session && w.detail?.permissions.can_record_training) {
      training.mutate(
        {
          kind: 'plan',
          title: title.trim(),
          activity_date: date,
          notes: owner.trim() ? 'Proposed facilitator: ' + owner.trim() : '',
        },
        { onSuccess: () => onOpenChange(false), onError: (e) => setMessage(e.message) },
      )
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{session ? 'Plan a KT session' : 'Schedule a follow-up'}</DialogTitle>
          <DialogDescription>
            {w.demo
              ? 'Save an illustrative plan in this browser tab.'
              : 'Add a dated plan to the case training log.'}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={save} className="ow-fields">
          <label>
            Case
            <select value={ref} disabled={!w.demo} onChange={(e) => setRef(e.target.value)}>
              {w.data.people.map((p) => (
                <option key={p.ref} value={p.ref}>
                  {p.name} · {p.ref}
                </option>
              ))}
            </select>
          </label>
          <label>
            {session ? 'Session objective' : 'Action'}
            <input
              required
              minLength={3}
              maxLength={300}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={session ? 'Activity to observe' : 'Follow-up to coordinate'}
            />
          </label>
          <label>
            {session ? 'Proposed facilitator' : 'Responsible role'}
            <input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="Name or role" />
          </label>
          <label>
            Proposed date
            <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          {message && <p role="alert">{message}</p>}
          <button
            disabled={training.isPending}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white"
          >
            {w.demo ? 'Save illustrative plan' : 'Record plan'}
          </button>
        </form>
      </DialogContent>
    </Dialog>
  )
}
