import { useEffect, useRef, useState } from 'react'
import type { PointerEvent } from 'react'
import { api, isFixtureMode } from './api/client'
import { useActionFeedback } from './actionFeedback'
import { slotLabel } from './caseDisplay'
import { clearSelections, hasAvailableSlot, selectColumn } from './timetableSelection'
import type { ContractorTimetableWeek, TimetableSlot, TimetableWeek } from './types/domain'

const weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
const hours = Array.from({ length: 8 }, (_, index) => index + 9)
const lastWeek = 2
const dayDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
const clock = (hour: number) => String(hour).padStart(2, '0') + ':00'
const dayLabel = (monday: string, day: number) => dayDate.format(Date.parse(monday) + day * 86_400_000)

function WeekNavigation({ week, monday, disabled, onChange }: {
  week: number
  monday?: string
  disabled?: boolean
  onChange: (week: number) => void
}) {
  return <div className="timetable-navigation">
    <button type="button" className="secondary chip" disabled={disabled || week === 0}
      onClick={() => onChange(week - 1)}>Previous week</button>
    <span role="status">{monday ? `${dayLabel(monday, 0)} – ${dayLabel(monday, 4)}` : 'Loading week…'}</span>
    <button type="button" className="secondary chip" disabled={disabled || week >= lastWeek}
      onClick={() => onChange(week + 1)}>Next week</button>
  </div>
}

export function TenantTimetable({ unitId, residentId, location, disabled, onPendingChange, onReadyChange }: {
  unitId: string
  residentId: string
  location: string
  disabled: boolean
  onPendingChange: (pending: boolean) => void
  onReadyChange: (ready: boolean) => void
}) {
  const [week, setWeek] = useState(0)
  const [calendars, setCalendars] = useState<TimetableWeek[]>()
  const calendar = calendars?.[week]
  const [edits, setEdits] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const drag = useRef<{
    pointerId: number
    anchor: TimetableSlot
    endHour: number
    edits: Record<string, boolean>
  } | null>(null)
  const suppressClick = useRef(false)
  const dirty = Object.keys(edits).length > 0
  const hasSelection = calendar && hasAvailableSlot(calendar.slots, edits)
  const hasSavedAvailability = calendars?.some((value) => hasAvailableSlot(value.slots)) ?? false

  useEffect(() => {
    onPendingChange(dirty || saving)
  }, [dirty, saving, onPendingChange])

  useEffect(() => {
    onReadyChange(hasSavedAvailability)
  }, [hasSavedAvailability, onReadyChange])

  useEffect(() => () => onReadyChange(false), [onReadyChange])

  useEffect(() => {
    if (isFixtureMode) return
    let active = true
    Promise.all(Array.from({ length: lastWeek + 1 }, (_, index) => api.getAvailability(unitId, residentId, index))).then(
      (value) => {
        if (!active) return
        setWeek(value[0].slots.every((slot) => slot.past) ? 1 : 0)
        setCalendars(value)
      },
      () => { if (active) setError('Availability could not be loaded. Try again.') },
    )
    return () => { active = false }
  }, [unitId, residentId, revision])

  function changeWeek(nextWeek: number) {
    setError('')
    setNotice('')
    setWeek(nextWeek)
  }

  function startDrag(event: PointerEvent<HTMLTableElement>) {
    if (event.button !== 0) return
    suppressClick.current = false
    drag.current = null
    if (event.pointerType === 'touch' || !(event.target instanceof Element)) return
    const cell = event.target.closest<HTMLTableCellElement>('td[data-slot]')
    const slot = calendar?.slots.find((item) => item.start === cell?.dataset.slot)
    if (slot && !slot.past && !slot.booked && !saving && !disabled) {
      drag.current = { pointerId: event.pointerId, anchor: slot, endHour: slot.hour, edits }
    }
  }

  function moveDrag(event: PointerEvent<HTMLTableElement>) {
    const selection = drag.current
    if (!selection || selection.pointerId !== event.pointerId || !calendar || saving || disabled) return
    if (!(event.buttons & 1)) {
      drag.current = null
      return
    }
    const endHour = hours.find((_, index) => {
      const row = event.currentTarget.tBodies[0]?.rows[index]
      if (!row) return false
      const { top, bottom } = row.getBoundingClientRect()
      return event.clientY >= top && event.clientY < bottom
    })
    if (endHour === undefined || endHour === selection.endHour) return
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.setPointerCapture(event.pointerId)
    }
    selection.endHour = endHour
    suppressClick.current = true
    setNotice('')
    setEdits(selectColumn(calendar.slots, selection.anchor, endHour, selection.edits))
  }

  function updateSlot(slot: TimetableSlot, available: boolean) {
    setNotice('')
    setEdits((previous) => {
      const next = { ...previous }
      if (available === slot.available) delete next[slot.start]
      else next[slot.start] = available
      return next
    })
  }

  async function save() {
    if (!calendar || !dirty || saving || disabled) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const selected = calendar.slots.filter((slot) => edits[slot.start] ?? slot.available)
      const saved = await api.saveAvailability(unitId, residentId, calendar.week_start, selected.map((slot) => slot.start))
      setCalendars((previous) => previous?.map((value) => value.week_start === saved.week_start ? saved : value))
      setEdits({})
      setNotice('Availability saved.')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Availability could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  return <section className="review-timetable" aria-labelledby="review-availability">
    <h3 id="review-availability">Availability</h3>
    {isFixtureMode ? <p className="muted">Connect to FastAPI to select repair times.</p> : <>
      <p className="muted">{hasSavedAvailability
        ? 'Your assigned contractor can book one of your saved times after you approve the request.'
        : 'Choose and save at least one available time to continue to sharing.'}</p>
      <WeekNavigation week={week} monday={calendar?.week_start} disabled={disabled || saving || dirty || !calendar} onChange={changeWeek} />
      {error && <p className="error" role="alert">{error}</p>}
      {!calendar && error && <button type="button" className="secondary" disabled={disabled} onClick={() => {
        setError('')
        setRevision((value) => value + 1)
      }}>Try again</button>}
      {calendar && <>
        <div className="timetable-scroll" tabIndex={0} role="region" aria-label="Weekly timetable grid">
          <table className="timetable-grid" onPointerDown={startDrag} onPointerMove={moveDrag}
            onPointerUp={() => { drag.current = null }}
            onPointerCancel={() => { drag.current = null }}
            onLostPointerCapture={() => { drag.current = null }}
            onClickCapture={(event) => {
              if (suppressClick.current && event.detail > 0) {
                event.preventDefault()
                event.stopPropagation()
                suppressClick.current = false
              }
            }}>
            <caption>One-hour slots · {location} time</caption>
            <thead><tr><th scope="col">Time</th>{weekdays.map((day, index) =>
              <th scope="col" key={day}>{day}<span>{dayLabel(calendar.week_start, index)}</span></th>)}</tr></thead>
            <tbody>{hours.map((hour) => <tr key={hour}>
              <th scope="row">{clock(hour)}</th>
              {calendar.slots.filter((slot) => slot.hour === hour).map((slot) => {
                const checked = edits[slot.start] ?? slot.available
                return <td key={slot.start} data-slot={slot.start} aria-label={slot.past && !slot.booked ? 'Unavailable' : undefined}
                  className={slot.booked ? 'booked' : slot.past ? 'elapsed' : checked ? 'available' : undefined}>
                  {slot.booked ? <strong>Booked</strong> : !slot.past &&
                    <button type="button" className="slot-toggle" aria-pressed={checked} disabled={disabled || saving}
                      aria-label={`${weekdays[slot.day]} ${dayLabel(calendar.week_start, slot.day)} at ${clock(slot.hour)}`}
                      onMouseDown={(event) => {
                        if (event.button !== 0) return
                        event.preventDefault()
                        event.currentTarget.focus({ preventScroll: true })
                      }}
                      onClick={() => updateSlot(slot, !checked)}>
                      {checked ? 'Available' : 'Mark available'}
                    </button>}
                </td>
              })}
            </tr>)}</tbody>
          </table>
        </div>
        <div className="actions">
          <button type="button" disabled={disabled || saving || !dirty} onClick={() => void save()}>{saving ? 'Saving…' : 'Save availability'}</button>
          <button type="button" className="secondary" disabled={disabled || saving || !hasSelection} onClick={() => {
            setEdits(clearSelections(calendar.slots))
            setError('')
            setNotice('')
          }}>Clear selections</button>
          {dirty && <button type="button" className="secondary" disabled={disabled || saving} onClick={() => setEdits({})}>Discard changes</button>}
        </div>
        {notice && <p className="timetable-notice" role="status">{notice}</p>}
      </>}
    </>}
  </section>
}

export function ContractorTimetable({ slug, jobId, location, disabled, onBookingChange, onBooked, onOfferSlots }: {
  slug: string
  jobId: string
  location: string
  disabled: boolean
  onBookingChange: (booking: boolean) => void
  onBooked: () => void
  onOfferSlots?: () => void
}) {
  const notify = useActionFeedback()
  const [weeks, setWeeks] = useState<ContractorTimetableWeek[]>([])
  const [appointment, setAppointment] = useState<ContractorTimetableWeek['appointment']>(null)
  const [refreshing, setRefreshing] = useState(true)
  const [revision, setRevision] = useState(0)
  const [selection, setSelection] = useState('')
  const [booking, setBooking] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [bookingError, setBookingError] = useState('')
  const selected = weeks.flatMap((week) => week.slots).find((slot) => slot.start === selection)
  const canBook = weeks.some((week) => week.can_book)
  const hasSlots = weeks.some((week) => week.slots.length > 0)

  useEffect(() => {
    let active = true
    Promise.all(Array.from({ length: lastWeek + 1 }, (_, week) => api.getJobAvailability(slug, jobId, week))).then(
      (value) => {
        if (!active) return
        setWeeks(value)
        setAppointment(value.find((week) => week.appointment)?.appointment ?? null)
      },
      () => { if (active) setLoadError('The tenant’s availability could not be loaded.') },
    ).finally(() => { if (active) setRefreshing(false) })
    return () => { active = false }
  }, [slug, jobId, revision])

  useEffect(() => {
    if (appointment) onBooked()
  }, [appointment, onBooked])

  function refresh() {
    setWeeks([])
    setRefreshing(true)
    setSelection('')
    setLoadError('')
    setRevision((value) => value + 1)
  }

  async function book() {
    if (!selected || !canBook || booking || refreshing || disabled) return
    setBooking(true)
    onBookingChange(true)
    setBookingError('')
    try {
      setAppointment(await api.bookTenantVisit(slug, jobId, selected.start))
      notify('success', 'Visit booked.')
    } catch (failure) {
      const message = failure instanceof Error ? failure.message : 'The visit could not be confirmed.'
      setBookingError(message)
      notify('error', message)
      refresh()
    } finally {
      setBooking(false)
      onBookingChange(false)
    }
  }

  return <section className="job-timetable" aria-label="Tenant availability">
    {appointment ? <div className="appointment" role="status">
      <strong>Visit scheduled</strong><p>{slotLabel(appointment, location)}</p>
    </div> : <>
      <h4>Tenant availability</h4>
      {refreshing ? <p className="muted" role="status">Loading saved times…</p>
        : loadError ? <p className="error" role="alert">{loadError}</p>
        : !canBook ? <p className="muted" role="status">Booking is unavailable for this repair right now.</p>
        : !hasSlots ? <p role="status">There are no matching saved times in the next three calendar weeks.</p>
        : <fieldset disabled={booking || disabled}>
          <legend>Choose a visit time · {location} time</legend>
          <div className="visit-options">{weeks.flatMap((week) => weekdays.map((day, index) => {
            const slots = week.slots.filter((slot) => slot.day === index)
            return slots.length > 0 && <div key={week.week_start + day}>
              <strong>{day} {dayLabel(week.week_start, index)}</strong>
              {slots.map((slot) => <label key={slot.start}>
                <input type="radio" name={jobId + '-visit'} checked={selection === slot.start}
                  onChange={() => setSelection(slot.start)} />
                {clock(slot.hour)}–{clock(slot.hour + 1)}
              </label>)}
            </div>
          }))}</div>
        </fieldset>}
      {bookingError && <p className="error" role="alert">{bookingError}</p>}
      <div className="actions">
        {canBook && hasSlots && <button type="button" onClick={() => void book()}
          disabled={!selected || booking || refreshing || disabled}>{booking ? 'Booking…' : 'Book visit'}</button>}
        {!refreshing && canBook && !hasSlots && onOfferSlots &&
          <button type="button" disabled={booking || disabled} onClick={onOfferSlots}>Offer times to tenant</button>}
        <button type="button" className="secondary" disabled={booking || refreshing || disabled} onClick={() => {
          setBookingError('')
          refresh()
        }}>{loadError ? 'Try again' : 'Refresh availability'}</button>
      </div>
    </>}
  </section>
}
