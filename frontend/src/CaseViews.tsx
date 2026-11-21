import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, invoiceUrl, isFixtureMode } from './api/client'
import { useActionFeedback } from './actionFeedback'
import { caseStatusLabel, formatTime, slotLabel, timelineEventLabel } from './caseDisplay'
import type { CaseEvent, MaintenanceCase } from './types/domain'

export function CaseTimeline({ caseId, revision = 0 }: { caseId: string; revision?: number }) {
  const notify = useActionFeedback()
  const manual = useRef(false)
  const [events, setEvents] = useState<CaseEvent[]>()
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    api.getCaseEvents(caseId).then(
      (result) => {
        if (!active) return
        setEvents(result)
        setFailed(false)
        if (manual.current) notify('success', 'Timeline refreshed.')
        manual.current = false
      },
      () => {
        if (!active) return
        setFailed(true)
        if (manual.current) notify('error', 'Timeline could not be loaded.')
        manual.current = false
      },
    )
    return () => { active = false }
  }, [caseId, revision, attempt, notify])
  const milestones = events?.flatMap((event) => {
    const label = timelineEventLabel(event)
    return label ? [{ ...event, label }] : []
  })
  return (
    <section className="case-timeline" aria-label="Case timeline">
      <h3>Case timeline</h3>
      {failed && <p role="alert">Timeline unavailable. <button className="secondary chip"
        onClick={() => { manual.current = true; setFailed(false); setAttempt((value) => value + 1) }}>Retry timeline</button></p>}
      {milestones ? milestones.length ? <ol className="timeline" role="list">{milestones.map((event) =>
        <li key={event.id}>
          <strong>{event.label}</strong>
          <time dateTime={event.timestamp}>{formatTime(event.timestamp)}</time>
        </li>)}</ol> : <p>No updates yet.</p> : !failed && <p role="status">Loading case timeline…</p>}
    </section>
  )
}

export function RepairOutcome({ item }: { item: MaintenanceCase }) {
  const { completion_report: report, invoice } = item
  if (!report && !invoice && item.status !== 'IN_PROGRESS') return null
  const fileUrl = invoice && (invoiceUrl(item.id)
    || 'data:application/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(invoice, null, 2)))
  return (
    <section className="repair-outcome" aria-label="Repair outcome">
      <h3>Repair outcome</h3>
      {item.status === 'IN_PROGRESS' && <p role="status">Your contractor has started the repair.</p>}
      {report && <><strong>Repair summary</strong><p className="issue-copy">{report.summary}</p></>}
      {invoice && fileUrl ? <div>
        <p><strong>Invoice {invoice.invoice_number}</strong> · {new Intl.NumberFormat('en-IE', {
          style: 'currency', currency: invoice.currency,
        }).format(invoice.amount_cents / 100)}</p>
        <p>{invoice.description}</p>
        <a className="button secondary" href={fileUrl} download={invoice.filename}>Download synthetic invoice</a>
      </div> : report && <p className="muted" role="status">Invoice pending</p>}
    </section>
  )
}

export function CaseProgress({ initial, active, location }: {
  initial: MaintenanceCase
  active: boolean
  location?: string
}) {
  const notify = useActionFeedback()
  const manual = useRef(false)
  const [current, setCurrent] = useState(initial)
  const [refresh, setRefresh] = useState(0)
  const [refreshResult, setRefreshResult] = useState<{ revision: number; failed: boolean }>()
  const [timelineRevision, setTimelineRevision] = useState(0)
  const refreshing = refresh > 0 && refresh !== refreshResult?.revision
  const [selection, setSelection] = useState('')
  const [lockedSlot, setLockedSlot] = useState('')
  const [bookingError, setBookingError] = useState('')
  const [booking, setBooking] = useState(false)
  const submitting = useRef(false)
  const caseId = initial.id
  const slot = current.slots.find((item) => item.slot_id === (lockedSlot || selection))

  useEffect(() => {
    if (!active || booking) return
    let reading = true
    api.getCase(caseId).then(
      (result) => {
        if (reading) {
          setCurrent(result)
          if (manual.current) notify('success', 'Case refreshed.')
          manual.current = false
          setRefreshResult({ revision: refresh, failed: false })
          setTimelineRevision((revision) => revision + 1)
        }
      },
      () => {
        if (!reading) return
        setRefreshResult({ revision: refresh, failed: true })
        if (manual.current) notify('error', 'The case could not be refreshed.')
        manual.current = false
      },
    )
    return () => { reading = false }
  }, [active, booking, caseId, refresh, notify])

  async function confirm(event: FormEvent) {
    event.preventDefault()
    if (!slot || submitting.current || current.status !== 'SLOTS_OFFERED') return
    submitting.current = true
    setBooking(true)
    setBookingError('')
    try {
      setLockedSlot(slot.slot_id)
      const response = await api.selectSlot(caseId, slot.slot_id, current.resident_id)
        .catch(() => api.getCase(caseId).catch(() => null))
      if (response) setCurrent(response)
      if (response?.appointment?.slot_id === slot.slot_id) notify('success', 'Your appointment is confirmed.')
      else {
        const message = 'We could not confirm that appointment. Check the case before trying again.'
        setBookingError(message)
        notify('error', message)
      }
    } finally {
      submitting.current = false
      setBooking(false)
      setRefresh((revision) => revision + 1)
    }
  }

  return (
    <section className="case-progress" aria-label="Appointment">
      <div className="inbox-heading">
        <h3>Appointment</h3>
        <button className="secondary chip" disabled={booking || refreshing} onClick={() => { manual.current = true; setRefresh((value) => value + 1) }}>
          {refreshing ? 'Refreshing case…' : 'Refresh case'}
        </button>
      </div>
      {!refreshing && refreshResult?.failed && <p className="error" role="alert">The case could not be refreshed. Try again.</p>}
      {!refreshing && refresh > 0 && !refreshResult?.failed && <p className="muted" role="status">Case updated.</p>}
      {current.appointment ? <div className="appointment" role="status">
        <strong>Appointment confirmed</strong>
        <p>{slotLabel(current.appointment, location)}</p>
      </div> : current.status === 'SLOTS_OFFERED' ? <form onSubmit={confirm}>
        <fieldset disabled={booking || Boolean(lockedSlot)}>
          <legend>Choose an offered time</legend>
          {current.slots.map((option) => <label className="field-row selectable" key={option.slot_id}>
            <input type="radio" name="appointment-slot" checked={(lockedSlot || selection) === option.slot_id}
              onChange={() => setSelection(option.slot_id)} />
            {slotLabel(option, location)}
          </label>)}
        </fieldset>
        {bookingError && <p className="error" role="alert">{bookingError}</p>}
        <button disabled={!slot || booking || refreshing}>{booking ? 'Confirming…' : bookingError ? 'Retry confirmation' : 'Confirm appointment'}</button>
      </form> : current.status === 'DECLINED' ? <p role="status"><strong>Declined by contractor</strong>. No appointment was booked.</p>
        : current.status === 'NEEDS_HUMAN_REVIEW' || current.status === 'FAILED' || current.status === 'CANCELLED'
          ? <p role="status">{caseStatusLabel(current.status)}. No appointment was confirmed.</p>
          : isFixtureMode ? <p role="status">Waiting for your contractor to offer appointment times.</p>
            : <p role="status">Your contractor can book one of the times you saved when reviewing your report.</p>}
      <RepairOutcome item={current} />
      <CaseTimeline caseId={caseId} revision={timelineRevision} />
    </section>
  )
}
