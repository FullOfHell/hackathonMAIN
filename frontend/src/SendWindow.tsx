import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { BeforeSend, feedbackDuration } from './actionFeedback'

interface PendingAction {
  id: number
  label: string
  deadline: number
  resolve: (send: boolean) => void
}

export function SendWindow({ children }: { children: ReactNode }) {
  const pending = useRef(new Set<PendingAction>())
  const sequence = useRef(0)
  const [actions, setActions] = useState<PendingAction[]>([])
  const beforeSend = useCallback((label: string) => new Promise<boolean>((resolve) => {
    if ([...pending.current].some((action) => action.label === label)) {
      resolve(false)
      return
    }
    const action = { id: ++sequence.current, label, deadline: Date.now() + feedbackDuration, resolve }
    pending.current.add(action)
    setActions((visible) => [...visible, action])
  }), [])
  const finish = useCallback((action: PendingAction, send: boolean, exit?: Animation) => {
    if (!pending.current.delete(action)) return
    action.resolve(send)
    const remove = () => setActions((visible) => visible.filter((item) => item !== action))
    if (exit) void exit.finished.then(remove, remove)
    else remove()
  }, [])
  useEffect(() => {
    const queue = pending.current
    function cancelAll() {
      for (const action of queue) finish(action, false)
    }
    window.addEventListener('pagehide', cancelAll)
    return () => {
      window.removeEventListener('pagehide', cancelAll)
      for (const action of queue) action.resolve(false)
      queue.clear()
    }
  }, [finish])

  return <BeforeSend.Provider value={beforeSend}>
    {children}
    <div className="send-windows">
      {actions.map((action) => <Countdown key={action.id} action={action} finish={finish} />)}
    </div>
  </BeforeSend.Provider>
}

function Countdown({ action, finish }: {
  action: PendingAction
  finish: (action: PendingAction, send: boolean, exit?: Animation) => void
}) {
  const panel = useRef<HTMLElement>(null)
  const [leaving, setLeaving] = useState(false)
  const [initialRemaining] = useState(() => Math.max(0, action.deadline - Date.now()))
  const [seconds, setSeconds] = useState(() => Math.ceil(initialRemaining / 1000))
  useEffect(() => {
    const remaining = () => Math.max(0, action.deadline - Date.now())
    const timer = window.setTimeout(() => finish(action, true), remaining())
    const tick = window.setInterval(() => setSeconds(Math.ceil(remaining() / 1000)), 200)
    return () => { window.clearTimeout(timer); window.clearInterval(tick) }
  }, [action, finish])
  function finishWithExit(send: boolean) {
    setLeaving(true)
    const exit = window.matchMedia('(prefers-reduced-motion: no-preference)').matches
      ? panel.current?.animate([{ opacity: 0, transform: 'translateY(-1rem)' }],
          { duration: 180, easing: 'ease-in', fill: 'forwards' })
      : undefined
    finish(action, send, exit)
  }
  return <section ref={panel} className="send-window" aria-label={action.label}>
    <span role="status">{action.label} <span className="send-window-sr">Sending in seven seconds.</span></span>
    <span aria-hidden="true">Sending in {seconds}s</span>
    <div>
      <button type="button" disabled={leaving} onClick={() => finishWithExit(false)}>Undo</button>
      <button type="button" disabled={leaving} onClick={() => finishWithExit(true)}>Send now</button>
    </div>
    <span className="send-timer" aria-hidden="true">
      <span style={{ animationDuration: feedbackDuration + 'ms', animationDelay: (initialRemaining - feedbackDuration) + 'ms' }} />
    </span>
  </section>
}
