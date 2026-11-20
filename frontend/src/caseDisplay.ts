import type { AppointmentSlot } from './types/domain'

const dateTime = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Berlin',
})

export function formatTime(value: string) {
  return dateTime.format(new Date(value))
}

export function slotLabel(slot: AppointmentSlot) {
  return formatTime(slot.start) + ' to ' + formatTime(slot.end) + ' (Aachen time)'
}

export function statusLabel(status: string) {
  return status.toLowerCase().replace(/_/g, ' ')
}

export function caseStatusLabel(status: string) {
  if (status === 'DECLINED' || status === 'rejected') return 'Declined by contractor'
  const label = statusLabel(status.replace(/[.]/g, '_'))
  return label.charAt(0).toUpperCase() + label.slice(1)
}
