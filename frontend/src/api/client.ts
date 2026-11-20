import { caseFixture, partnerJobFixture, unitContextFixture } from './fixtures'
import partnerEventFixture from '../../../shared/fixtures/partner-event.json'
import type {
  CaseEvent,
  CreateCaseRequest,
  IntakeRequest,
  IntakeResponse,
  MaintenanceCase,
  PartnerAction,
  PartnerInboxJob,
  SharingApprovalRequest,
  UnitContext,
} from '../types/domain'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '')
export const isFixtureMode = !apiBaseUrl
const demoCases = new Map<string, MaintenanceCase>()
const demoJobs = new Map<string, PartnerInboxJob>()
const demoEvents = new Map<string, CaseEvent[]>()

const waitForFixture = async <T>(value: T): Promise<T> => {
  await new Promise((resolve) => window.setTimeout(resolve, 250))
  return structuredClone(value)
}

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  })
  if (!response.ok) {
    const failure = await response.json().catch(() => null)
    throw new Error(typeof failure?.detail === 'string' ? failure.detail : `API request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const api = {
  getUnitContext: async (unitId: string): Promise<UnitContext> =>
    apiBaseUrl
      ? request<UnitContext>(`/api/units/${unitId}/context`)
      : waitForFixture(unitContextFixture),

  extractIntake: (draft: IntakeRequest): Promise<IntakeResponse> => request('/api/intake/extract', {
    method: 'POST', body: JSON.stringify(draft), signal: AbortSignal.timeout(6500),
  }),

  createCase: async (body: CreateCaseRequest): Promise<MaintenanceCase> =>
    apiBaseUrl
      ? request<MaintenanceCase>('/api/cases', {
          method: 'POST',
          body: JSON.stringify(body),
        })
      : createDemoCase(body),

  async getCase(caseId: string): Promise<MaintenanceCase> {
    if (apiBaseUrl) return request('/api/cases/' + encodeURIComponent(caseId))
    const demoCase = demoCases.get(caseId)
    if (!demoCase) throw new Error('Case unavailable.')
    return waitForFixture(demoCase)
  },

  async getCaseEvents(caseId: string): Promise<CaseEvent[]> {
    if (apiBaseUrl) return request('/api/cases/' + encodeURIComponent(caseId) + '/events')
    const demoCase = await api.getCase(caseId)
    const events = [{ id: 1, case_id: caseId, type: 'maintenance.case_created',
      actor: demoCase.resident_id, timestamp: demoCase.created_at, payload: {} }]
    if (demoCase.partner_job_id) {
      events.push({ id: 2, case_id: caseId, type: 'partner.job_requested',
        actor: 'system', timestamp: demoCase.updated_at, payload: {} })
    }
    return [...events, ...(demoEvents.get(caseId) ?? [])]
  },

  listUnitCases: (unitId: string): Promise<MaintenanceCase[]> =>
    apiBaseUrl ? request('/api/units/' + encodeURIComponent(unitId) + '/cases')
      : waitForFixture([...demoCases.values()].filter((item) => item.unit_id === unitId).reverse()),

  approveSharing: async (
    caseId: string,
    body: SharingApprovalRequest,
  ): Promise<MaintenanceCase> =>
    apiBaseUrl
      ? request<MaintenanceCase>(`/api/cases/${caseId}/sharing-approval`, {
          method: 'POST',
          body: JSON.stringify(body),
        })
      : approveDemoCase(caseId, body),

  listPartnerJobs: async (): Promise<PartnerInboxJob[]> =>
    apiBaseUrl ? request('/partners/heatfix/connector/jobs')
      : waitForFixture([...demoJobs.values()].reverse()),

  updatePartnerJob: (jobId: string, action: PartnerAction): Promise<PartnerInboxJob> =>
    apiBaseUrl ? request('/partners/heatfix/connector/jobs/' + encodeURIComponent(jobId) + '/' + action, { method: 'POST' })
      : updateDemoJob(jobId, action),

  selectSlot: (caseId: string, slotId: string, residentId: string): Promise<MaintenanceCase> =>
    apiBaseUrl ? request('/api/cases/' + encodeURIComponent(caseId) + '/select-slot', {
      method: 'POST', body: JSON.stringify({ slot_id: slotId, resident_id: residentId }),
    }) : bookDemoSlot(caseId, slotId, residentId),
}

function recordDemoEvent(caseId: string, actor: string, type: string, payload: Record<string, unknown>) {
  const events = demoEvents.get(caseId) ?? []
  demoEvents.set(caseId, [...events, { id: events.length + 3, case_id: caseId,
    actor, type, timestamp: new Date().toISOString(), payload }])
}

async function updateDemoJob(jobId: string, action: PartnerAction): Promise<PartnerInboxJob> {
  const job = demoJobs.get(jobId)
  const item = job && demoCases.get(job.request_id)
  if (!job || !item) throw new Error('Job unavailable.')
  const status = { accept: 'accepted', reject: 'rejected', 'offer-slots': 'slots_offered' }[action]
  if (job.status === status) return waitForFixture(job)
  if (action === 'offer-slots' ? job.status !== 'accepted'
    : job.status !== 'received' && !(action === 'reject' && job.status === 'accepted')) {
    throw new Error('This action is unavailable for the current job status.')
  }
  const updated = { ...job, status }
  demoJobs.set(jobId, updated)
  if (action === 'accept') {
    recordDemoEvent(item.id, 'partner:heatfix', 'partner.accepted', {})
  } else {
    const nextStatus = action === 'reject' ? 'DECLINED' : 'SLOTS_OFFERED'
    demoCases.set(item.id, { ...item, status: nextStatus,
      slots: action === 'offer-slots' ? partnerEventFixture.data.slots : [], updated_at: new Date().toISOString() })
    recordDemoEvent(item.id, 'partner:heatfix', 'case.status_changed', { to: nextStatus })
  }
  return waitForFixture(updated)
}

async function bookDemoSlot(caseId: string, slotId: string, residentId: string): Promise<MaintenanceCase> {
  const item = demoCases.get(caseId)
  const slot = item?.slots.find((option) => option.slot_id === slotId)
  if (!item || !slot || item.resident_id !== residentId || !item.partner_job_id) throw new Error('Slot unavailable.')
  if (item.appointment?.slot_id === slotId) return waitForFixture(item)
  if (item.status !== 'SLOTS_OFFERED') throw new Error('This case cannot be booked again.')
  const job = demoJobs.get(item.partner_job_id)
  if (!job) throw new Error('Job unavailable.')
  const now = new Date().toISOString()
  const booked: MaintenanceCase = { ...item, status: 'SCHEDULED', updated_at: now,
    appointment: { ...slot, case_id: caseId, booked_at: now } }
  demoCases.set(caseId, booked)
  demoJobs.set(job.id, { ...job, status: 'scheduled' })
  recordDemoEvent(caseId, 'resident:' + residentId, 'case.status_changed', { to: 'SCHEDULED' })
  return waitForFixture(booked)
}

function createDemoCase(body: CreateCaseRequest): Promise<MaintenanceCase> {
  const now = new Date().toISOString()
  const demoCase = {
    ...caseFixture, ...body, id: 'demo-' + crypto.randomUUID(),
    created_at: now, updated_at: now, availability_preferences: body.availability_preferences ?? [],
  }
  demoCases.set(demoCase.id, demoCase)
  return waitForFixture(demoCase)
}

async function approveDemoCase(caseId: string, body: SharingApprovalRequest): Promise<MaintenanceCase> {
  const demoCase = demoCases.get(caseId)
  if (!demoCase) throw new Error('Case unavailable.')
  if (demoCase.partner_job_id) return waitForFixture(demoCase)
  const now = new Date().toISOString()
  const jobId = 'job-' + caseId
  const fields = body.approved_fields
  const resident = unitContextFixture.residents[0]
  const property = unitContextFixture.property
  demoJobs.set(jobId, {
    id: jobId, request_id: caseId, status: 'received', received_at: now,
    payload: {
      ...partnerJobFixture, request_id: caseId, idempotency_key: caseId + '-heating_repair-v1',
      property: {
        address: property.address, unit: unitContextFixture.unit.label,
        ...(fields.includes('heating_type') && { heating_type: property.heating }),
      },
      issue: {
        description: demoCase.description, symptoms: demoCase.symptoms,
        priority: demoCase.urgency, availability_preferences: demoCase.availability_preferences,
      },
      resident: {
        ...(fields.includes('name') && { name: resident.name }),
        ...(fields.includes('contact') && { contact: { email: resident.email, phone: resident.phone } }),
      },
      sharing: { approved_fields: fields, approved_at: now },
    },
  })
  const approved: MaintenanceCase = {
    ...demoCase, status: 'PARTNER_REQUESTED', partner_job_id: jobId, updated_at: now,
    sharing_request: undefined,
    sharing_approval: {
      id: demoJobs.size, case_id: caseId, partner_id: demoCase.partner_id!,
      shared_fields: fields, channel: body.channel, approved_by: body.approved_by, recorded_at: now,
    },
  }
  demoCases.set(caseId, approved)
  return waitForFixture(approved)
}
