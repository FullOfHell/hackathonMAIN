import { useEffect, useRef, useState } from 'react'
import type { PointerEvent } from 'react'
import { api, isFixtureMode } from './api/client'
import { slotLabel } from './caseDisplay'
import { clearSelections, selectColumn } from './timetableSelection'
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

export function TenantTimetable({ unitId, residentId }: { unitId: string; residentId: string }) {
  const [week, setWeek] = useState(0)
  const [calendar, setCalendar] = useState<TimetableWeek>()
  const [edits, setEdits] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const firstLoad = useRef(true)
  const drag = useRef<{
    pointerId: number
    anchor: TimetableSlot
    endHour: number
    edits: Record<string, boolean>
  } | null>(null)
  const suppressClick = useRef(false)
  const dirty = Object.keys(edits).length > 0
  const hasSelection = calendar?.slots.some((slot) => !slot.past && !slot.booked && (edits[slot.start] ?? slot.available))

  useEffect(() => {
    if (isFixtureMode) return
    let active = true
    api.getAvailability(unitId, residentId, week).then(
      (value) => {
        if (!active) return
        const showNextWeek = firstLoad.current && week === 0 && value.slots.every((slot) => slot.past)
        firstLoad.current = false
        if (showNextWeek) setWeek(1)
        else setCalendar(value)
      },
      () => { if (active) setError('Availability could not be loaded. Try again.') },
    )
    return () => { active = false }
  }, [unitId, residentId, week, revision])

  function changeWeek(nextWeek: number) {
    setCalendar(undefined)
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
    if (slot && !slot.past && !slot.booked && !saving) {
      drag.current = { pointerId: event.pointerId, anchor: slot, endHour: slot.hour, edits }
    }
  }

  function moveDrag(event: PointerEvent<HTMLTableElement>) {
    const selection = drag.current
    if (!selection || selection.pointerId !== event.pointerId || !calendar || saving) return
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
    if (!calendar || !dirty || saving) return
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const selected = calendar.slots.filter((slot) => edits[slot.start] ?? slot.available)
      setCalendar(await api.saveAvailability(unitId, residentId, calendar.week_start, selected.map((slot) => slot.start)))
      setEdits({})
      setNotice('Availability saved.')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Availability could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  if (isFixtureMode) return <section className="panel"><p>Connect to FastAPI to manage availability.</p></section>

  return <section className="panel timetable" aria-label="Your availability">
    <h2>Weekly timetable</h2>
    <p className="muted">Tap a slot to mark it available, then save. Only contractors assigned to your approved repairs can see these times.</p>
    <WeekNavigation week={week} monday={calendar?.week_start} disabled={saving || dirty} onChange={changeWeek} />
    {error && <p className="error" role="alert">{error}</p>}
    {!calendar && error && <button type="button" className="secondary" onClick={() => {
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
          <caption>One-hour slots · Aachen time</caption>
          <thead><tr><th scope="col">Time</th>{weekdays.map((day, index) =>
            <th scope="col" key={day}>{day}<span>{dayLabel(calendar.week_start, index)}</span></th>)}</tr></thead>
          <tbody>{hours.map((hour) => <tr key={hour}>
            <th scope="row">{clock(hour)}</th>
            {calendar.slots.filter((slot) => slot.hour === hour).map((slot) => {
              const checked = edits[slot.start] ?? slot.available
              return <td key={slot.start} data-slot={slot.start} aria-label={slot.past && !slot.booked ? 'Unavailable' : undefined}
                className={slot.booked ? 'booked' : slot.past ? 'elapsed' : checked ? 'available' : undefined}>
                {slot.booked ? <strong>Booked</strong> : !slot.past &&
                  <button type="button" className="slot-toggle" aria-pressed={checked} disabled={saving}
                    aria-label={`${weekdays[slot.day]} ${dayLabel(calendar.week_start, slot.day)} at ${clock(slot.hour)}`}
                    onClick={() => updateSlot(slot, !checked)}>
                    {checked ? 'Available' : 'Mark available'}
                  </button>}
              </td>
            })}
          </tr>)}</tbody>
        </table>
      </div>
      <div className="actions">
        <button type="button" disabled={saving || !dirty} onClick={() => void save()}>{saving ? 'Saving…' : 'Save availability'}</button>
        <button type="button" className="secondary" disabled={saving || !hasSelection} onClick={() => {
          setEdits(clearSelections(calendar.slots))
          setError('')
          setNotice('')
        }}>Clear selections</button>
        {dirty && <button type="button" className="secondary" disabled={saving} onClick={() => setEdits({})}>Discard changes</button>}
      </div>
      {notice && <p className="timetable-notice" role="status">{notice}</p>}
    </>}
  </section>
}

export function ContractorTimetable({ slug, jobId, onBooked }: { slug: string; jobId: string; onBooked: () => void }) {
  const [week, setWeek] = useState(0)
  const [calendar, setCalendar] = useState<ContractorTimetableWeek>()
  const [refreshing, setRefreshing] = useState(true)
  const [revision, setRevision] = useState(0)
  const [selection, setSelection] = useState('')
  const [booking, setBooking] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api.getJobAvailability(slug, jobId, week).then(
      (value) => { if (active) setCalendar(value) },
      () => { if (active) setError('The tenant’s availability could not be loaded. Try again.') },
    ).finally(() => { if (active) setRefreshing(false) })
    return () => { active = false }
  }, [slug, jobId, week, revision])

  function refresh() {
    setRefreshing(true)
    setSelection('')
    setRevision((value) => value + 1)
  }

  async function book() {
    if (!selection || booking || refreshing) return
    setBooking(true)
    setError('')
    try {
      const appointment = await api.bookTenantVisit(slug, jobId, selection)
      if (calendar) setCalendar({ ...calendar, appointment })
      onBooked()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'The visit could not be confirmed.')
      refresh()
    } finally {
      setBooking(false)
    }
  }

  return <section className="job-timetable" aria-label="Tenant availability">
    {calendar?.appointment ? <div className="appointment" role="status">
      <strong>Visit scheduled</strong><p>{slotLabel(calendar.appointment)}</p>
    </div> : <>
      <h4>Tenant availability</h4>
      <WeekNavigation week={week} monday={refreshing ? undefined : calendar?.week_start}
        disabled={booking || refreshing} onChange={(value) => {
          setError('')
          setRefreshing(true)
          setSelection('')
          setWeek(value)
        }} />
      {!refreshing && calendar?.can_book && (calendar.slots.length > 0 ? <fieldset disabled={booking}>
        <legend>Choose a visit time · Aachen time</legend>
        <div className="visit-options">{weekdays.map((day, index) => {
          const slots = calendar.slots.filter((slot) => slot.day === index)
          return slots.length > 0 && <div key={day}>
            <strong>{day} {dayLabel(calendar.week_start, index)}</strong>
            {slots.map((slot) => <label key={slot.start}>
              <input type="radio" name={jobId + '-visit'} checked={selection === slot.start}
                onChange={() => setSelection(slot.start)} />
              {clock(slot.hour)}–{clock(slot.hour + 1)}
            </label>)}
          </div>
        })}</div>
      </fieldset> : <p role="status">The tenant has no available slots this week.</p>)}
      {!refreshing && calendar && !calendar.can_book && <p className="muted">Booking is unavailable for this repair right now.</p>}
      <div className="actions">
        {calendar?.can_book && <button type="button" onClick={() => void book()}
          disabled={!selection || booking || refreshing}>{booking ? 'Booking…' : 'Book visit'}</button>}
        <button type="button" className="secondary" disabled={booking || refreshing} onClick={() => {
          setError('')
          refresh()
        }}>Refresh availability</button>
      </div>
    </>}
    {error && <p className="error" role="alert">{error}</p>}
  </section>
}
