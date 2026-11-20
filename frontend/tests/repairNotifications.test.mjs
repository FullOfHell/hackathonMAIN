import assert from 'node:assert/strict'
import test from 'node:test'
import { timelineEventLabel } from '../src/caseDisplay.ts'
import {
  contractorInboxHref, contractorInboxSlug, contractorNotifications, residentNotifications,
} from '../src/repairNotifications.ts'

test('the default inbox is HeatFix and provider inboxes round-trip independently', () => {
  assert.equal(contractorInboxSlug('#inbox'), 'heatfix')
  assert.equal(contractorInboxHref('heatfix'), '#inbox')
  assert.equal(contractorInboxSlug(contractorInboxHref('demo-internet')), 'demo-internet')
  assert.equal(contractorInboxSlug('#cases'), undefined)
  assert.equal(contractorInboxSlug('#inbox/../heatfix'), undefined)
})

test('contractor notifications come from received jobs with stable IDs', () => {
  const job = { id: 'job_other', request_id: 'case_1', received_at: '2026-11-20T20:00:00Z' }
  assert.deepEqual(contractorNotifications([]), [])
  assert.deepEqual(contractorNotifications([job]).map(({ id, caseId, timestamp }) => [id, caseId, timestamp]),
    [['job:job_other', 'case_1', job.received_at]])
})

test('resident notifications are limited to the contractor accepting, declining and completing', () => {
  const event = (id, type, to, actor = 'partner:p_demo_internet') => ({
    id, case_id: 'case_1', type, actor, timestamp: `2026-11-20T20:0${id}:00Z`, payload: { to },
  })
  const notifications = residentNotifications([
    event(1, 'maintenance.case_created', undefined, 'resident:c_202'),
    event(2, 'partner.job_requested', undefined, 'system'),
    event(3, 'case.status_changed', 'DECLINED', 'resident:c_202'),
    event(4, 'partner.accepted'),
    event(5, 'case.status_changed', 'DECLINED'),
    event(6, 'case.status_changed', 'COMPLETED'),
    event(7, 'case.status_changed', 'CLOSED'),
  ])
  assert.deepEqual(notifications.map(({ id, title }) => [id, title]), [
    ['event:case_1:6', 'Repair completed'],
    ['event:case_1:5', 'Repair request declined'],
    ['event:case_1:4', 'Repair request accepted'],
  ])
})

test('the timeline shows permission and repair milestones and omits internal handoff states', () => {
  const state = (to) => ({ type: 'case.status_changed', payload: { to } })
  for (const hidden of ['TRIAGED', 'AWAITING_SHARING_APPROVAL', 'PARTNER_REQUESTED']) {
    assert.equal(timelineEventLabel(state(hidden)), undefined)
  }
  assert.equal(timelineEventLabel({ type: 'sharing.approved' }), 'Tenant gave permission to send repair details')
  assert.equal(timelineEventLabel(state('SLOTS_OFFERED')), 'Contractor offered appointment times')
})
