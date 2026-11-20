import caseCreateJson from '../../../shared/fixtures/case-create.json'
import caseResponseJson from '../../../shared/fixtures/case-response.json'
import partnerJobJson from '../../../shared/fixtures/partner-job.json'
import sharingApprovalJson from '../../../shared/fixtures/sharing-approval.json'
import unitContextJson from '../../../shared/fixtures/unit-context.json'
import type {
  CreateCaseRequest,
  MaintenanceCase,
  PartnerJob,
  SharingApprovalRequest,
  UnitContext,
} from '../types/domain'

export const unitContextFixture = unitContextJson as UnitContext
export const createCaseFixture = caseCreateJson as CreateCaseRequest
export const caseFixture = caseResponseJson as MaintenanceCase
export const sharingApprovalFixture = sharingApprovalJson as SharingApprovalRequest
export const partnerJobFixture = partnerJobJson as PartnerJob
