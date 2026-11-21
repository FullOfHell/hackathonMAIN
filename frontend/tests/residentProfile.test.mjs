import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer } from 'vite'

async function loadPortal(t, baseUrl = '') {
  const server = await createServer({
    configFile: false, envDir: false, logLevel: 'error', appType: 'custom',
    server: { middlewareMode: true, hmr: false, watch: null, ws: false },
    define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify(baseUrl) },
  })
  t.after(() => server.close())
  const { api, profileChanges, residentHomeDetails } = await server.ssrLoadModule('/src/api/client.ts')
  const fixtures = await server.ssrLoadModule('/src/api/fixtures.ts')
  return { api, profileChanges, residentHomeDetails, ...fixtures }
}

test('saving a draft sends just the displayed actor and trimmed edits, and uses the API response', async (t) => {
  const { api, profileChanges, unitContextFixture } = await loadPortal(t, 'http://centrix.test')
  const resident = unitContextFixture.residents[0]
  const updated = { ...resident, phone: '+49 151 00000001', unit: '4B rear entrance' }
  assert.deepEqual(profileChanges(resident, { ...resident, name: ' ' + resident.name }), {})
  assert.deepEqual(profileChanges({ ...resident, phone: null }, { ...resident, phone: '' }), {})
  assert.deepEqual(profileChanges(resident, { ...resident, preferred_contact: 'phone' }), { preferred_contact: 'phone' })
  assert.deepEqual(profileChanges(resident, { ...resident, preferred_contact: 'sms' }), {})
  const changes = profileChanges(resident, { ...resident, phone: ' ' + updated.phone + ' ', unit: updated.unit })
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    assert.equal(url, 'http://centrix.test/api/units/unit_4b/residents/c_202/profile')
    assert.equal(init.method, 'PATCH')
    assert.deepEqual(JSON.parse(init.body), { acting_resident_id: resident.id, phone: updated.phone, unit: updated.unit })
    return Response.json(updated)
  })
  assert.deepEqual(await api.updateResidentProfile(resident.unit_id, resident.id, changes), updated)
  globalThis.fetch.mock.mockImplementation(() => Response.json({
    detail: [{ loc: ['body', 'phone'], msg: 'Value error, phone must contain 7 to 15 digits' }],
  }, { status: 422 }))
  await assert.rejects(api.updateResidentProfile(resident.unit_id, resident.id, { phone: 'bad' }), /phone number/)
})

test('fixture context and new consent share one resident while earlier jobs keep the approved values', async (t) => {
  const { api, createCaseFixture, unitContextFixture, residentHomeDetails } = await loadPortal(t)
  const previousWindow = globalThis.window
  globalThis.window = { setTimeout: (callback) => setTimeout(callback, 0) }
  t.after(() => {
    if (previousWindow === undefined) delete globalThis.window
    else globalThis.window = previousWindow
  })
  const resident = structuredClone(unitContextFixture.residents[0])
  const edit = (changes) => api.updateResidentProfile(resident.unit_id, resident.id, changes)
  await assert.rejects(edit({ unit_id: 'different' }), /editable profile fields/)
  const initial = await api.createCase(createCaseFixture)
  const approve = (item, optional) => api.approveSharing(item.id, { approved_by: resident.id,
    approved_fields: [...item.sharing_request.required_fields, ...optional], channel: 'portal_chat' })
  await approve(initial, ['contact'])
  const [originalJob] = await api.listPartnerJobs('heatfix')
  const originalEvents = await api.getCaseEvents(initial.id)
  const changes = { name: 'Lena Beispiel', phone: '+49 151 00000002', preferred_contact: 'email',
    address: 'Demo address 15, Aachen', unit: '4B rear entrance', heating: 'Heat pump' }
  assert.deepEqual(await edit(changes), { ...resident, ...changes })
  assert.deepEqual((await api.getUnitContext(resident.unit_id)).residents[0], { ...resident, ...changes })
  assert.deepEqual(unitContextFixture.residents[0], resident)
  await approve(initial, ['contact'])
  assert.deepEqual(await api.listPartnerJobs('heatfix'), [originalJob])
  assert.deepEqual(await api.getCaseEvents(initial.id), originalEvents)
  assert.equal((await api.listUnitCases(resident.unit_id)).length, 1)
  const next = await api.createCase(createCaseFixture)
  await approve(next, ['contact', 'heating_type'])
  const [newJob, oldJob] = await api.listPartnerJobs('heatfix')
  assert.deepEqual(newJob.payload.resident, { contact: { email: resident.email, phone: changes.phone } })
  assert.deepEqual(oldJob, originalJob)
  assert.deepEqual(residentHomeDetails(unitContextFixture, resident), {
    address: unitContextFixture.property.address, unit: unitContextFixture.unit.label, heating: unitContextFixture.property.heating,
  })
  assert.deepEqual(newJob.payload.property, { address: changes.address, unit: changes.unit, heating_type: changes.heating })
  const [group] = await api.listManagerRepairs()
  assert.equal(group.contractor.name, 'HeatFix Aachen GmbH')
  assert.deepEqual(group.repairs.map((repair) => [repair.case.id, repair.address, repair.unit]), [
    [next.id, changes.address, changes.unit],
    [initial.id, originalJob.payload.property.address, originalJob.payload.property.unit],
  ])

  const week = await api.getAvailability(resident.unit_id, resident.id, 1)
  const [chosen, unchosen] = week.slots
  await api.saveAvailability(resident.unit_id, resident.id, week.week_start, [chosen.start])
  assert.equal((await api.getJobAvailability('heatfix', newJob.id, 1)).can_book, false)
  await api.updatePartnerJob('heatfix', newJob.id, { action: 'accept' })
  assert.deepEqual((await api.getJobAvailability('heatfix', newJob.id, 1)).slots.map((slot) => slot.start), [chosen.start])
  await assert.rejects(api.bookTenantVisit('heatfix', newJob.id, unchosen.start), /no longer available/)
  const appointment = await api.bookTenantVisit('heatfix', newJob.id, chosen.start)
  assert.equal(appointment.start, chosen.start)
  assert.deepEqual((await api.getCase(next.id)).appointment, appointment)
})

test('an intake result without extracted heating symptoms proceeds to the editable summary', async (t) => {
  const server = await createServer({
    configFile: false, envDir: false, logLevel: 'error', appType: 'custom',
    server: { middlewareMode: true, hmr: false, watch: null, ws: false },
  })
  t.after(() => server.close())
  const { makeIntakeReview, nextIntakeFollowUp } = await server.ssrLoadModule('/src/intake.ts')
  const draft = { report: 'All radiators are cold.', hot_water_affected: null }
  assert.equal(makeIntakeReview(draft).urgency, 'normal')
  const reviewed = makeIntakeReview(draft, { urgency: 'high', symptoms: [], availability_preferences: [] })
  assert.equal(reviewed.urgency, 'high')
  assert.equal(reviewed.description, draft.report)
  assert.equal(nextIntakeFollowUp({ missing_information: ['heating_symptom', 'availability_preferences'] }, new Set()), undefined)
  assert.equal(nextIntakeFollowUp({ missing_information: ['availability_preferences'] }, new Set()), undefined)
  assert.equal(nextIntakeFollowUp({ missing_information: ['hot_water_affected'] }, new Set()), 'hot_water_affected')
})
