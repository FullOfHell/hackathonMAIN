import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, invoiceUrl } from './api/client'
import { caseStatusLabel, formatTime, slotLabel } from './caseDisplay'
import type { CaseEvent, MaintenanceCase } from './types/domain'

const eventLabels: Record<string, string> = {
  'maintenance.case_created': 'Report saved',
  'sharing.approved': 'Sharing approved',
  'partner.job_requested': 'Job received by HeatFix',
  'partner.accepted': 'Job accepted by HeatFix',
  'partner.booking_unconfirmed': 'Booking confirmation pending',
  'seed.historical_case': 'Historical repair case',
}

export function CaseTimeline({ caseId, revision = 0 }: { caseId: string; revision?: number }) {
  const [events, setEvents] = useState<CaseEvent[]>()
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    api.getCaseEvents(caseId).then(
      (result) => { if (active) { setEvents(result); setFailed(false) } },
      () => { if (active) setFailed(true) },
    )
    return () => { active = false }
  }, [caseId, revision, attempt])
  return (
    <section aria-label="Case timeline">
      <h3>Case timeline</h3>
      {failed && <p role="alert">Timeline unavailable. <button className="secondary chip"
        onClick={() => { setFailed(false); setAttempt((value) => value + 1) }}>Retry timeline</button></p>}
      {events ? events.length ? <ol className="timeline">{events.map((event) =>
        <li key={event.id}>
          {eventLabels[event.type] ?? caseStatusLabel(String(event.payload.to ?? event.type))}
          <time dateTime={event.timestamp}>{formatTime(event.timestamp)}</time>
        </li>)}</ol> : <p>No case events yet.</p> : !failed && <p role="status">Loading case timeline…</p>}
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
      {item.status === 'IN_PROGRESS' && <p role="status">HeatFix has started the repair.</p>}
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

export function CaseProgress({ initial, active }: { initial: MaintenanceCase; active: boolean }) {
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
          setRefreshResult({ revision: refresh, failed: false })
          setTimelineRevision((revision) => revision + 1)
        }
      },
      () => { if (reading) setRefreshResult({ revision: refresh, failed: true }) },
    )
    return () => { reading = false }
  }, [active, booking, caseId, refresh])

  async function confirm(event: FormEvent) {
    event.preventDefault()
    if (!slot || submitting.current || current.status !== 'SLOTS_OFFERED') return
    submitting.current = true
    setBooking(true)
    setBookingError('')
    setLockedSlot(slot.slot_id)
    try {
      const response = await api.selectSlot(caseId, slot.slot_id, current.resident_id)
      setCurrent(response)
      if (!response.appointment) setBookingError('Appointment confirmation is pending. Retry the same slot.')
    } catch {
      const response = await api.getCase(caseId).catch(() => null)
      if (response) setCurrent(response)
      if (!response?.appointment) setBookingError('We could not confirm the appointment. Retry to check the same slot.')
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
        <button className="secondary chip" disabled={booking || refreshing} onClick={() => setRefresh((value) => value + 1)}>
          {refreshing ? 'Refreshing case…' : 'Refresh case'}
        </button>
      </div>
      {!refreshing && refreshResult?.failed && <p className="error" role="alert">The case could not be refreshed. Try again.</p>}
      {!refreshing && refresh > 0 && !refreshResult?.failed && <p className="muted" role="status">Case updated.</p>}
      {current.appointment ? <div className="appointment" role="status">
        <strong>Appointment confirmed</strong>
        <p>{slotLabel(current.appointment)}</p>
      </div> : current.status === 'SLOTS_OFFERED' ? <form onSubmit={confirm}>
        <fieldset disabled={booking || Boolean(lockedSlot)}>
          <legend>Choose an offered time</legend>
          {current.slots.map((option) => <label className="field-row selectable" key={option.slot_id}>
            <input type="radio" name="appointment-slot" checked={(lockedSlot || selection) === option.slot_id}
              onChange={() => setSelection(option.slot_id)} />
            {slotLabel(option)}
          </label>)}
        </fieldset>
        {bookingError && <p className="error" role="alert">{bookingError}</p>}
        <button disabled={!slot || booking || refreshing}>{booking ? 'Confirming…' : bookingError ? 'Retry confirmation' : 'Confirm appointment'}</button>
      </form> : current.status === 'DECLINED' ? <p role="status"><strong>Declined by HeatFix</strong>. No appointment was booked.</p>
        : current.status === 'NEEDS_HUMAN_REVIEW' || current.status === 'FAILED' || current.status === 'CANCELLED'
          ? <p role="status">{caseStatusLabel(current.status)}. No appointment was confirmed.</p>
          : <p role="status">Waiting for HeatFix to offer appointment times.</p>}
      <RepairOutcome item={current} />
      <CaseTimeline caseId={caseId} revision={timelineRevision} />
    </section>
  )
}
