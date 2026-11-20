import { caseFixture, unitContextFixture } from './fixtures'
import type {
  CreateCaseRequest,
  MaintenanceCase,
  SharingApprovalRequest,
  UnitContext,
} from '../types/domain'

const waitForFixture = async <T>(value: T): Promise<T> => {
  await new Promise((resolve) => window.setTimeout(resolve, 250))
  return structuredClone(value)
}

export const api = {
  getUnitContext: async (_unitId: string): Promise<UnitContext> =>
    waitForFixture(unitContextFixture),

  createCase: async (request: CreateCaseRequest): Promise<MaintenanceCase> =>
    waitForFixture({ ...caseFixture, ...request }),

  approveSharing: async (
    caseId: string,
    _approval: SharingApprovalRequest,
  ): Promise<MaintenanceCase> =>
    waitForFixture({ ...caseFixture, id: caseId, status: 'PARTNER_REQUESTED' }),
}
