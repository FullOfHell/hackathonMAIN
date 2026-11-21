import type { AppointmentSlot, CaseEvent } from './types/domain'

const dateTime = new Intl.DateTimeFormat('en-GB', {
  dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Berlin',
})

export function formatTime(value: string) {
  return dateTime.format(new Date(value))
}

const appointmentDate = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeZone: 'Europe/Berlin' })
const appointmentTime = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'Europe/Berlin',
})

export function repairTimeLocation(address?: string) {
  const parts = address?.split(/[,\n]/).map((part) => part.trim())
    .filter((part) => part && !/^(germany|deutschland|de)$/i.test(part)) ?? []
  const locality = parts.at(-1) ?? ''
  const city = locality.match(/(?:^|\s)\d{5}\s+([\p{L}][\p{L}\p{M} .'’–-]*)$/u)?.[1]
  if (city) return city
  if (parts.length > 1 && /^[\p{L}][\p{L}\p{M} .'’–-]*$/u.test(locality)) return locality
  return 'Germany'
}

export function slotLabel(slot: Pick<AppointmentSlot, 'start' | 'end'>, location = 'Germany') {
  const start = new Date(slot.start)
  const end = new Date(slot.end)
  const startDate = appointmentDate.format(start)
  const endDate = appointmentDate.format(end)
  const endLabel = startDate === endDate ? appointmentTime.format(end)
    : endDate + ', ' + appointmentTime.format(end)
  return `${startDate}, ${appointmentTime.format(start)} → ${endLabel} (${location} time)`
}

export function statusLabel(status: string) {
  return status.toLowerCase().replace(/_/g, ' ')
}

export const noContractorsLabel = 'No contractors available'

export function caseStatusLabel(status: string) {
  if (status === 'DECLINED' || status === 'rejected') return 'Declined by contractor'
  if (status === 'AWAITING_SHARING_APPROVAL') return 'Awaiting tenant permission to share'
  if (status === 'PARTNER_REQUESTED') return 'Waiting for contractor'
  if (status === 'NO_PROVIDER_AVAILABLE') return noContractorsLabel
  if (status === 'SLOTS_OFFERED' || status === 'slots_offered') return 'Appointment times offered'
  const label = statusLabel(status.replace(/[.]/g, '_'))
  return label.charAt(0).toUpperCase() + label.slice(1)
}

const timelineEvents: Record<string, string> = {
  'maintenance.case_created': 'Report submitted',
  'sharing.approved': 'Tenant gave permission to send repair details',
  'partner.job_requested': 'Contractor received the request',
  'partner.accepted': 'Contractor accepted the request',
  'seed.historical_case': 'Past repair',
  'building.outage_detected': 'Possible building-wide heating issue',
}

const timelineStatuses: Record<string, string> = {
  SLOTS_OFFERED: 'Contractor offered appointment times',
  SCHEDULED: 'Appointment confirmed',
  IN_PROGRESS: 'Repair started',
  COMPLETED: 'Repair completed',
  AWAITING_INVOICE_APPROVAL: 'Invoice awaiting manager approval',
  LINKED_TO_BUILDING_REPAIR: 'Added to a building repair',
  CLOSED: 'Case closed',
  DECLINED: 'Contractor declined the request',
  NO_PROVIDER_AVAILABLE: noContractorsLabel,
  CANCELLED: 'Report cancelled',
  NEEDS_HUMAN_REVIEW: 'Property manager review needed',
  FAILED: 'Repair could not proceed',
}

export function timelineEventLabel(event: CaseEvent): string | undefined {
  if (event.type === 'case.status_changed') return timelineStatuses[String(event.payload.to)]
  if (event.type === 'building.repair_updated') return timelineStatuses[String(event.payload.repair_status)]
  return timelineEvents[event.type]
}
