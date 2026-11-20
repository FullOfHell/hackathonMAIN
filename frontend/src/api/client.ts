import { caseFixture, partnerJobFixture, unitContextFixture } from './fixtures'
import type {
  CaseEvent,
  CreateCaseRequest,
  MaintenanceCase,
  PartnerInboxJob,
  SharingApprovalRequest,
  UnitContext,
} from '../types/domain'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '')
export const isFixtureMode = !apiBaseUrl
const demoCases = new Map<string, MaintenanceCase>()
const demoJobs = new Map<string, PartnerInboxJob>()

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
    throw new Error(`API request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const api = {
  getUnitContext: async (unitId: string): Promise<UnitContext> =>
    apiBaseUrl
      ? request<UnitContext>(`/api/units/${unitId}/context`)
      : waitForFixture(unitContextFixture),

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
    return events
  },

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
