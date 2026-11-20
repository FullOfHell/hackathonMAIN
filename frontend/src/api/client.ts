import { caseFixture, partnerJobFixture, unitContextFixture } from './fixtures'
import { defaultContractorSlug } from '../repairNotifications'
import partnerEventFixture from '../../../shared/fixtures/partner-event.json'
import type {
  CaseEvent,
  ContactChannel,
  Contractor,
  ContractorInput,
  CreateCaseRequest,
  IntakeRequest,
  IntakeResponse,
  MaintenanceCase,
  ManagerRepairGroup,
  PartnerCommand,
  PartnerInboxJob,
  Resident,
  ResidentHomeDetails,
  ResidentProfileChanges,
  ResidentProfileDraft,
  SharingApprovalRequest,
  UnitContext,
} from '../types/domain'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '')
export const isFixtureMode = !apiBaseUrl
const demoCases = new Map<string, MaintenanceCase>()
const demoJobs = new Map<string, PartnerInboxJob>()
const demoEvents = new Map<string, CaseEvent[]>()
const demoHome = structuredClone(unitContextFixture)
const profileTextFields = ['name', 'email', 'phone', 'address', 'unit', 'heating'] as const
const profileFields = [...profileTextFields, 'preferred_contact'] as const
const homeDetailLengths = { address: 200, unit: 80, heating: 120 } as const

function fixtureProfileKey(resident: Resident) {
  return 'centrix:fixture:profile:' + resident.unit_id + ':' + resident.id
}

if (isFixtureMode) {
  for (const resident of demoHome.residents) {
    try {
      const stored = JSON.parse(sessionStorage.getItem(fixtureProfileKey(resident)) ?? '{}')
      for (const field of profileFields) {
        if (typeof stored?.[field] === 'string') resident[field] = stored[field]
      }
    } catch { /* The in-memory fixture also works when browser storage is unavailable. */ }
  }
}

export const contactChannels: readonly ContactChannel[] = ['portal', 'email', 'phone']

const profileHints: Record<keyof ResidentProfileChanges, string> = {
  name: 'Enter a name of up to 120 characters.',
  email: 'Enter an email address, for example lena@example.com.',
  phone: 'Enter a phone number with 7 to 15 digits, for example +49 151 00000001.',
  preferred_contact: 'Choose Portal, Email or Phone as your preferred contact channel.',
  address: 'Enter an address of up to 200 characters.',
  unit: 'Enter a unit of up to 80 characters.',
  heating: 'Enter a heating type of up to 120 characters.',
}

const waitForFixture = async <T>(value: T): Promise<T> => {
  await new Promise((resolve) => window.setTimeout(resolve, 250))
  return structuredClone(value)
}

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    cache: init?.method === 'POST' ? 'default' : 'no-store',
    headers: init?.headers ?? (init?.body ? { 'Content-Type': 'application/json' } : undefined),
  })
  if (!response.ok) {
    const failure = await response.json().catch(() => null)
    if (init?.method === 'PATCH' && Array.isArray(failure?.detail)) {
      const hints = failure.detail.map((entry: { loc?: string[] }) =>
        profileHints[entry.loc?.at(-1) as keyof ResidentProfileChanges]).filter(Boolean)
      if (hints.length) throw new Error([...new Set(hints)].join(' '))
    }
    throw new Error(typeof failure?.detail === 'string' ? failure.detail : `API request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

function partnerJobsPath(partnerSlug: string) {
  return '/partners/' + encodeURIComponent(partnerSlug) + '/connector/jobs'
}

export function residentHomeDetails(home: UnitContext, resident: Resident): ResidentHomeDetails {
  return {
    address: resident.address ?? home.property.address,
    unit: resident.unit ?? home.unit.label,
    heating: resident.heating ?? home.property.heating,
  }
}

export function profileChanges(resident: Resident, draft: Partial<ResidentProfileDraft>): ResidentProfileChanges {
  const changes: ResidentProfileChanges = {}
  for (const field of profileTextFields) {
    const value = draft[field]?.trim()
    if (value !== undefined && value !== (resident[field] ?? '')) changes[field] = value
  }
  const channel = draft.preferred_contact
  if (channel !== undefined && (contactChannels as readonly string[]).includes(channel)
    && channel !== resident.preferred_contact) {
    changes.preferred_contact = channel as ContactChannel
  }
  return changes
}

export const api = {
  getUnitContext: async (unitId: string): Promise<UnitContext> =>
    apiBaseUrl
      ? request<UnitContext>(`/api/units/${unitId}/context`)
      : waitForFixture(demoHome),

  async updateResidentProfile(unitId: string, residentId: string, changes: ResidentProfileChanges): Promise<Resident> {
    if (apiBaseUrl) {
      return request('/api/units/' + encodeURIComponent(unitId) + '/residents/' + encodeURIComponent(residentId) + '/profile', {
        method: 'PATCH', body: JSON.stringify({ ...changes, acting_resident_id: residentId }),
      })
    }
    const resident = demoHome.residents.find((item) => item.unit_id === unitId && item.id === residentId)
    if (!resident) throw new Error('Resident not found for this unit.')
    const fields = Object.keys(changes)
    if (!fields.length || fields.some((field) => !Object.hasOwn(profileHints, field))) {
      throw new Error('Supply only editable profile fields.')
    }
    if (changes.phone !== undefined) {
      const groups = changes.phone.replace(/\(\d+\)/g, '0')
      const digits = changes.phone.replace(/\D/g, '')
      if (!/^\+?\d+(?:[ .-]\d+)*$/.test(groups) || digits.length < 7 || digits.length > 15) throw new Error(profileHints.phone)
    }
    if (changes.email !== undefined && !/^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+$/.test(changes.email)) throw new Error(profileHints.email)
    if (changes.name !== undefined && !changes.name) throw new Error(profileHints.name)
    for (const field of ['address', 'unit', 'heating'] as const) {
      const value = changes[field]
      if (value !== undefined && (!value.trim() || value.length > homeDetailLengths[field])) throw new Error(profileHints[field])
    }
    Object.assign(resident, changes)
    try {
      sessionStorage.setItem(fixtureProfileKey(resident), JSON.stringify(
        Object.fromEntries(profileFields.map((field) => [field, resident[field]]))))
    } catch { /* Keep using this page's resident copy. */ }
    return waitForFixture(resident)
  },

  extractIntake: (draft: IntakeRequest): Promise<IntakeResponse> => request('/api/intake/extract', {
    method: 'POST', body: JSON.stringify(draft), signal: AbortSignal.timeout(6500),
  }),

  transcriptionStatus: (): Promise<{ enabled: boolean }> => request('/api/intake/transcription'),

  transcribeRecording: (audio: Blob): Promise<{ text: string }> => request('/api/intake/transcription', {
    method: 'POST', body: audio, headers: { 'Content-Type': audio.type }, signal: AbortSignal.timeout(25000),
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

  listManagerRepairs(): Promise<ManagerRepairGroup[]> {
    if (apiBaseUrl) return request('/api/manager/repairs')

    const repairs = [...demoCases.values()].reverse().map((item) => {
      const property = demoJobs.get(item.partner_job_id ?? '')?.payload.property
      const details = residentHomeDetails(demoHome, demoHome.residents[0])
      return { case: item, address: property?.address ?? details.address, unit: property?.unit ?? details.unit }
    })
    return waitForFixture(repairs.length
      ? [{ contractor: { id: 'p_heatfix', name: 'HeatFix Aachen GmbH' }, repairs }]
      : [])
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

  listContractors: (): Promise<Contractor[]> => request('/api/manager/contractors'),

  addContractor: (body: ContractorInput): Promise<Contractor> => request('/api/manager/contractors', {
    method: 'POST', body: JSON.stringify(body),
  }),

  listPartnerJobs: (partnerSlug: string): Promise<PartnerInboxJob[]> =>
    apiBaseUrl ? request(partnerJobsPath(partnerSlug))
      : waitForFixture(partnerSlug === defaultContractorSlug ? [...demoJobs.values()].reverse() : []),

  updatePartnerJob: (partnerSlug: string, jobId: string, command: PartnerCommand): Promise<PartnerInboxJob> => {
    if (apiBaseUrl) return request(partnerJobsPath(partnerSlug) + '/' + encodeURIComponent(jobId) + '/' + command.action, {
      method: 'POST', body: command.body && JSON.stringify(command.body),
    })
    return partnerSlug === defaultContractorSlug ? updateDemoJob(jobId, command) : Promise.reject(new Error('Job unavailable.'))
  },

  selectSlot: (caseId: string, slotId: string, residentId: string): Promise<MaintenanceCase> =>
    apiBaseUrl ? request('/api/cases/' + encodeURIComponent(caseId) + '/select-slot', {
      method: 'POST', body: JSON.stringify({ slot_id: slotId, resident_id: residentId }),
    }) : bookDemoSlot(caseId, slotId, residentId),
}

export function invoiceUrl(caseId: string) {
  return apiBaseUrl && apiBaseUrl + '/api/cases/' + encodeURIComponent(caseId) + '/documents/invoice'
}

function recordDemoEvent(caseId: string, actor: string, type: string, payload: Record<string, unknown>) {
  const events = demoEvents.get(caseId) ?? []
  demoEvents.set(caseId, [...events, { id: events.length + 3, case_id: caseId,
    actor, type, timestamp: new Date().toISOString(), payload }])
}

async function updateDemoJob(jobId: string, command: PartnerCommand): Promise<PartnerInboxJob> {
  const job = demoJobs.get(jobId)
  const item = job && demoCases.get(job.request_id)
  if (!job || !item) throw new Error('Job unavailable.')
  const action = command.action
  const status = { accept: 'accepted', reject: 'rejected', 'offer-slots': 'slots_offered',
    start: 'in_progress', complete: 'completed', invoice: 'invoice_ready' }[action]
  const allowed = { accept: ['received'], reject: ['received', 'accepted'], 'offer-slots': ['accepted'],
    start: ['scheduled'], complete: ['in_progress'], invoice: ['completed'] }[action]
  if (job.status === status) return waitForFixture(job)
  if (!allowed.includes(job.status)) {
    throw new Error('This action is unavailable for the current job status.')
  }
  const updated = { ...job, status }
  demoJobs.set(jobId, updated)
  if (action === 'accept') {
    recordDemoEvent(item.id, 'partner:heatfix', 'partner.accepted', {})
  } else {
    const nextStatus = { reject: 'DECLINED', 'offer-slots': 'SLOTS_OFFERED', start: 'IN_PROGRESS',
      complete: 'COMPLETED', invoice: 'CLOSED' }[action] as MaintenanceCase['status']
    const now = new Date().toISOString()
    const document = { case_id: item.id, unit_id: item.unit_id, created_at: now }
    demoCases.set(item.id, {
      ...item, status: nextStatus, updated_at: now,
      slots: action === 'offer-slots' ? partnerEventFixture.data.slots : item.slots,
      completion_report: command.action === 'complete'
        ? { ...document, ...command.body, kind: 'completion_report', filename: 'completion_report.json',
            url: '/api/cases/' + item.id + '/documents/completion_report' } : item.completion_report,
      invoice: command.action === 'invoice'
        ? { ...document, ...command.body, kind: 'invoice', filename: 'invoice.json',
            url: '/api/cases/' + item.id + '/documents/invoice' } : item.invoice,
    })
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
  const resident = demoHome.residents.find((item) => item.unit_id === demoCase.unit_id && item.id === demoCase.resident_id)
  if (!resident || resident.id !== body.approved_by) throw new Error('Only the reporting resident can approve sharing.')
  const homeDetails = residentHomeDetails(demoHome, resident)
  demoJobs.set(jobId, {
    id: jobId, request_id: caseId, status: 'received', received_at: now,
    payload: {
      ...partnerJobFixture, request_id: caseId, idempotency_key: caseId + '-heating_repair-v1',
      property: {
        address: homeDetails.address, unit: homeDetails.unit,
        ...(fields.includes('heating_type') && { heating_type: homeDetails.heating }),
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
