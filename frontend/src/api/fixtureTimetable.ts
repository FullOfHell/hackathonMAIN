import type { AppointmentSlot, TimetableWeek } from '../types/domain'

const timeZone = 'Europe/Berlin'
const dayMs = 86_400_000
const localDate = new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' })
const offset = new Intl.DateTimeFormat('en-GB', { timeZone, timeZoneName: 'longOffset' })

function currentMonday(now: Date) {
  const parts = localDate.formatToParts(now)
  const field = (type: string) => parts.find((part) => part.type === type)?.value ?? ''
  const date = new Date(Date.UTC(Number(field('year')), Number(field('month')) - 1, Number(field('day'))))
  return date.getTime() - ((date.getUTCDay() + 6) % 7) * dayMs
}

export function fixtureWeekOffset(monday: string) {
  return (Date.parse(monday) - currentMonday(new Date())) / (7 * dayMs)
}

export function fixtureWeek(week: number, saved: Set<string>, visits: AppointmentSlot[]): TimetableWeek {
  const now = new Date()
  const monday = currentMonday(now) + week * 7 * dayMs
  const slots = Array.from({ length: 40 }, (_, index) => {
    const day = Math.floor(index / 8)
    const hour = 9 + index % 8
    const date = new Date(monday + day * dayMs)
    const zone = offset.formatToParts(date).find((part) => part.type === 'timeZoneName')?.value.slice(3) || '+00:00'
    const time = Date.parse(date.toISOString().slice(0, 10) + `T${String(hour).padStart(2, '0')}:00:00${zone}`)
    const start = new Date(time).toISOString()
    return { day, hour, start, end: new Date(time + 3_600_000).toISOString(), past: time <= now.getTime(),
      available: saved.has(start), booked: visits.some((visit) => Date.parse(visit.start) === time) }
  })
  return { week_start: new Date(monday).toISOString().slice(0, 10), slots }
}
