import type { AppointmentSlot, CaseEvent } from './types/domain'

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
