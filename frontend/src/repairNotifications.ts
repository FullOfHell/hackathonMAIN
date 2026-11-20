import type { CaseEvent, PartnerInboxJob } from './types/domain'

const templates = {
  assigned: { title: 'New repair request', message: 'A resident approved sending this request to your team.' },
  accepted: { title: 'Repair request accepted', message: 'Your contractor accepted your repair request.' },
  rejected: { title: 'Repair request declined', message: 'Your contractor declined your repair request.' },
  completed: { title: 'Repair completed', message: 'Your contractor marked your repair as complete.' },
}

export const defaultContractorSlug = 'heatfix'

export function contractorInboxSlug(hash: string): string | undefined {
  if (hash === '#inbox') return defaultContractorSlug
  return /^#inbox\/([a-z0-9][a-z0-9-]*)$/i.exec(hash)?.[1]
}

export function contractorInboxHref(slug: string): string {
  return slug === defaultContractorSlug ? '#inbox' : '#inbox/' + encodeURIComponent(slug)
}

export interface RepairNotification {
  id: string
  caseId: string
  timestamp: string
  title: string
  message: string
}

export function residentNotifications(events: CaseEvent[]): RepairNotification[] {
  return events.flatMap((event) => {
    if (!event.actor.startsWith('partner:')) return []
    const type = event.type === 'partner.accepted' ? 'accepted'
      : event.type === 'case.status_changed' && event.payload.to === 'DECLINED' ? 'rejected'
      : event.type === 'case.status_changed' && event.payload.to === 'COMPLETED' ? 'completed'
      : null

    return type ? [{
      id: 'event:' + event.case_id + ':' + event.id,
      caseId: event.case_id,
      timestamp: event.timestamp,
      ...templates[type],
    }] : []
  }).sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))
}

export function contractorNotifications(jobs: PartnerInboxJob[]): RepairNotification[] {
  return jobs.map((job) => ({
    id: 'job:' + job.id,
    caseId: job.request_id,
    timestamp: job.received_at,
    ...templates.assigned,
  }))
}
