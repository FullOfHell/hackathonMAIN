export type CaseStatus =
  | 'REPORTED'
  | 'TRIAGED'
  | 'AWAITING_SHARING_APPROVAL'
  | 'PARTNER_REQUESTED'
  | 'SLOTS_OFFERED'
  | 'SCHEDULED'
  | 'IN_PROGRESS'
  | 'COMPLETED'
  | 'CLOSED'
  | 'DECLINED'
  | 'NO_PROVIDER_AVAILABLE'
  | 'CANCELLED'
  | 'NEEDS_HUMAN_REVIEW'
  | 'FAILED'

export interface PropertyContext {
  id: string
  address: string
  building_year: number
  heating_type: string
}

export interface UnitContext {
  unit_id: string
  property: PropertyContext
  unit: { label: string; floor: number; size_sqm: number; rooms: number }
  resident: {
    id: string
    name: string
    email: string
    phone: string
    preferred_contact: string
  }
  previous_cases: Array<{
    id: string
    issue_type: string
    summary: string
    status: CaseStatus
    closed_at: string
  }>
  access: {
    caretaker_available: boolean
    key_safe_available: boolean
    key_safe_code_shared: boolean
  }
}

export interface CreateCaseRequest {
  unit_id: string
  resident_id: string
  issue_type: 'heating_repair'
  description: string
  symptoms: string[]
  urgency: 'low' | 'normal' | 'high' | 'emergency'
  availability_preferences: string[]
  source_channel: 'portal_chat' | 'voice'
}

export interface CaseEvent {
  id: string
  type: string
  actor: string
  occurred_at: string
}

export interface MaintenanceCase extends CreateCaseRequest {
  id: string
  status: CaseStatus
  created_at: string
  events: CaseEvent[]
}

export interface SharingApprovalRequest {
  approved_fields: string[]
  channel: 'portal' | 'voice'
  approved_by: string
}

export interface PartnerJob {
  schema_version: '1.0'
  request_id: string
  idempotency_key: string
  service_type: 'heating_repair'
  property: { address: string; unit: string; heating_type: string }
  issue: { description: string; symptoms: string[]; priority: string }
  resident: { name: string; contact: string }
  sharing: { approved_fields: string[]; approved_at: string; channel: string }
  callback_url: string
}
