export type CaseStatus =
  | 'REPORTED'
  | 'TRIAGED'
  | 'AWAITING_SHARING_APPROVAL'
  | 'PARTNER_REQUESTED'
  | 'SLOTS_OFFERED'
  | 'SCHEDULED'
  | 'IN_PROGRESS'
  | 'COMPLETED'
  | 'AWAITING_INVOICE_APPROVAL'
  | 'LINKED_TO_BUILDING_REPAIR'
  | 'CLOSED'
  | 'DECLINED'
  | 'NO_PROVIDER_AVAILABLE'
  | 'CANCELLED'
  | 'NEEDS_HUMAN_REVIEW'
  | 'FAILED'

export type Channel = 'portal_chat' | 'voice' | 'email' | 'manager'
export type Urgency = 'low' | 'normal' | 'high'

export type MissingIntakeField = 'heating_symptom' | 'hot_water_affected' | 'availability_preferences'

export interface IntakeRequest {
  report: string
  hot_water_affected: boolean | null
}

export interface IntakeResult {
  symptoms: string[]
  urgency: Urgency | null
  availability_preferences: string[]
  missing_information: MissingIntakeField[]
  safety_signal: 'none' | 'possible_gas_leak'
}

export interface IntakeResponse {
  schema_version: '1.0'
  source: 'model' | 'fallback'
  result: IntakeResult
}

export interface ResidentHomeDetails {
  address: string
  unit: string
  heating: string
}

export interface Resident extends Partial<ResidentHomeDetails> {
  id: string
  unit_id: string
  name: string
  email: string | null
  phone: string | null
  preferred_contact: string | null
  move_in: string | null
}

export type ContactChannel = 'portal' | 'email' | 'phone'

export type ResidentProfileChanges = Partial<ResidentHomeDetails & {
  name: string
  email: string
  phone: string
  preferred_contact: ContactChannel
}>
export type ResidentProfileDraft = Record<keyof ResidentProfileChanges, string>

export interface UnitContext {
  unit_id: string
  property: {
    id: string
    address: string
    building_year: number
    heating: string
    region: string
    access_details: string
  }
  unit: { label: string; floor: number; size_sqm: number }
  residents: Resident[]
  prior_heating_cases: Array<{
    id: string
    issue_type: string
    description: string
    status: CaseStatus
    created_at: string
  }>
}

export interface CreateCaseRequest {
  unit_id: string
  resident_id: string
  issue_type: string
  description: string
  symptoms: string[]
  availability_preferences?: string[]
  urgency: Urgency
  source_channel: Channel
}

export interface SharingApprovalRequest {
  approved_fields: string[]
  channel: Channel
  approved_by: string
  expected_partner_id?: string
}

export interface SharingApproval {
  id: number
  case_id: string
  partner_id: string
  shared_fields: string[]
  channel: Channel
  approved_by: string
  recorded_at: string
}

export interface SharingRequest {
  partner: { id: string; name: string }
  proposed_fields: string[]
  required_fields: string[]
  shareable_fields: string[]
}

export interface AppointmentSlot {
  slot_id: string
  start: string
  end: string
}

export interface RepairReport {
  summary: string
}

export interface RepairInvoiceInput {
  invoice_number: string
  description: string
  amount_cents: number
  currency: 'EUR'
}

interface CaseDocument {
  case_id: string
  unit_id: string
  created_at: string
  filename: string
  url: string
}

export interface CompletionReport extends CaseDocument, RepairReport {
  kind: 'completion_report'
}

export interface RepairInvoice extends CaseDocument, RepairInvoiceInput {
  kind: 'invoice'
}

export interface MaintenanceCase extends CreateCaseRequest {
  id: string
  availability_preferences: string[]
  slots: AppointmentSlot[]
  appointment: (AppointmentSlot & { case_id: string; booked_at: string }) | null
  completion_report: CompletionReport | null
  invoice: RepairInvoice | null
  status: CaseStatus
  partner_id: string | null
  contractor_name?: string | null
  partner_job_id: string | null
  building_repair: {
    outage_id: string
    is_dispatch_case: boolean
    repair_status: CaseStatus | null
    partner_job_id: string | null
    scope_confirmed: boolean
    appointment: Pick<AppointmentSlot, 'start' | 'end'> | null
  } | null
  created_at: string
  updated_at: string
  sharing_approval: SharingApproval | null
  sharing_request?: SharingRequest
}

export interface ManagerRepair {
  case: MaintenanceCase
  address: string
  unit: string
}

export interface ManagerRepairGroup {
  contractor: { id: string; name: string } | null
  repairs: ManagerRepair[]
}

export interface CaseEvent {
  id: number
  case_id: string
  type: string
  actor: string
  timestamp: string
  payload: Record<string, unknown>
}

export interface PartnerJob {
  schema_version: '1.0'
  request_id: string
  idempotency_key: string
  service_type: string
  property: Record<string, string>
  issue: {
    description: string
    symptoms: string[]
    priority: Urgency
    availability_preferences: string[]
    repair_scope?: 'building_heating'
    previous_record?: { source_case_id?: string; date: string; description: string; note: string }
  }
  resident: {
    name?: string
    contact?: Pick<Resident, 'email' | 'phone'>
  }
  sharing: { approved_fields: string[]; approved_at: string }
  callback_url: string
}

export interface ContractorInput {
  name: string
  slug: string
  region: string
}

export interface Contractor {
  name: string
  slug: string
  regions: string[]
}

export interface PartnerInboxJob {
  id: string
  request_id: string
  status: string
  received_at: string
  pending_callback?: { event_id: string; type: string } | null
  payload: PartnerJob
}

export interface TimetableSlot {
  start: string
  end: string
  day: number
  hour: number
  available: boolean
  booked: boolean
  past: boolean
}

export interface TimetableWeek {
  week_start: string
  slots: TimetableSlot[]
}

export interface ContractorTimetableWeek extends TimetableWeek {
  can_book: boolean
  appointment: MaintenanceCase['appointment']
}

export type PartnerAction = 'accept' | 'reject' | 'offer-slots' | 'start' | 'complete' | 'invoice'

export type PartnerCommand =
  | { action: Exclude<PartnerAction, 'complete' | 'invoice'>; body?: never }
  | { action: 'complete'; body: RepairReport }
  | { action: 'invoice'; body: RepairInvoiceInput }
