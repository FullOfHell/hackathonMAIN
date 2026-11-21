import { useEffect, useRef, useState } from 'react'
import { api, isFixtureMode } from './api/client'
import { formatTime } from './caseDisplay'
import { contractorNotifications, residentNotifications } from './repairNotifications'
import type { RepairNotification } from './repairNotifications'

interface Props {
  partnerSlug?: string
  unitId: string
}

async function loadNotifications({ partnerSlug, unitId }: Props) {
  if (partnerSlug) return contractorNotifications(await api.listPartnerJobs(partnerSlug))

  const [home, cases] = await Promise.all([api.getUnitContext(unitId), api.listUnitCases(unitId)])
  const residentId = home.residents[0]?.id
  const ownCases = cases.filter((item) => item.resident_id === residentId && item.partner_job_id)
  const events = await Promise.all(ownCases.map((item) => api.getCaseEvents(item.id)))
  return residentNotifications(events.flat())
}

function readStorage() {
  return isFixtureMode ? sessionStorage : localStorage
}

function readIds(key: string): string[] {
  try {
    const stored: unknown = JSON.parse(readStorage().getItem(key) ?? '[]')
    if (Array.isArray(stored)) return stored.filter((value): value is string => typeof value === 'string')
  } catch {
    // Keep the bell usable if browser storage is unavailable.
  }
  return []
}

export function NotificationBell({ partnerSlug, unitId }: Props) {
  const storageKey = 'centrix:notifications:read:' + (partnerSlug ? 'contractor:' + partnerSlug : 'resident:' + unitId)
  const [read, setRead] = useState(() => readIds(storageKey))
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<RepairNotification[]>()
  const [failed, setFailed] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const container = useRef<HTMLDivElement>(null)
  const bell = useRef<HTMLButtonElement>(null)
  const seen = new Set(read)
  const unread = items?.filter((item) => !seen.has(item.id)) ?? []

  useEffect(() => {
    let active = true
    let timer: number | undefined

    async function update() {
      try {
        const next = await loadNotifications({ partnerSlug, unitId })
        if (active) { setItems(next); setFailed(false) }
      } catch {
        if (active) setFailed(true)
      } finally {
        if (active) timer = window.setTimeout(update, 15_000)
      }
    }

    void update()
    return () => { active = false; window.clearTimeout(timer) }
  }, [partnerSlug, unitId, refresh])

  useEffect(() => {
    if (!open) return

    const dismiss = (event: PointerEvent) => {
      if (event.target instanceof Node && !container.current?.contains(event.target)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        bell.current?.focus()
      }
    }
    document.addEventListener('pointerdown', dismiss)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', dismiss)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  function markRead(ids: string[]) {
    const next = [...new Set([...read, ...readIds(storageKey), ...ids])]
    setRead(next)
    try { readStorage().setItem(storageKey, JSON.stringify(next)) } catch { /* Keep the current read state. */ }
  }

  return (
    <div className="repair-notifications" ref={container}>
      <button type="button" className="notification-bell" ref={bell}
        aria-label={unread.length ? `Notifications, ${unread.length} unread` : 'Notifications'}
        aria-expanded={open} aria-controls="repair-notifications-panel"
        onClick={() => {
          if (!open) setRefresh((value) => value + 1)
          setOpen(!open)
        }}>
        <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
        </svg>
        {unread.length > 0 && <span aria-hidden="true" className="notification-count">
          {unread.length > 99 ? '99+' : unread.length}
        </span>}
      </button>
      <section id="repair-notifications-panel" className="notification-panel" hidden={!open}
        aria-labelledby="repair-notifications-title">
        <div className="notification-heading">
          <h2 id="repair-notifications-title">Notifications</h2>
          {unread.length > 0 && <button type="button" className="notification-mark-read" onClick={() => {
            markRead(unread.map((item) => item.id))
            bell.current?.focus()
          }}>Mark all as read</button>}
        </div>
        {failed && <p className="notification-info" role="status">Notifications could not be refreshed.</p>}
        {!items && !failed && <p className="notification-info" role="status">Loading notifications…</p>}
        {items?.length === 0 && !failed && <p className="notification-info">No notifications yet.</p>}
        {!!items?.length && <ul className="notification-list">
          {items.map((item) => (
            <li key={item.id}>
              <button type="button" className="notification-item" data-unread={!seen.has(item.id)}
                onClick={() => markRead([item.id])}>
                <strong>{!seen.has(item.id) && <span className="notification-unread">Unread · </span>}
                  {item.title}</strong>
                <span>{item.message}</span>
                <small>Case {item.caseId} · <time dateTime={item.timestamp}>{formatTime(item.timestamp)}</time></small>
              </button>
            </li>
          ))}
        </ul>}
      </section>
    </div>
  )
}
