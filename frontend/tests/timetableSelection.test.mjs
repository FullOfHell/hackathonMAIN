import assert from 'node:assert/strict'
import { test } from 'node:test'
import { clearSelections, hasAvailableSlot, selectColumn } from '../src/timetableSelection.ts'

test('availability requires a usable saved slot and can count a draft selection separately', () => {
  const slots = [
    { start: 'past', available: true, past: true },
    { start: 'booked', available: true, booked: true },
    { start: 'open', available: false },
  ]
  assert.equal(hasAvailableSlot(slots), false)
  assert.equal(hasAvailableSlot(slots, { open: true }), true)
  assert.equal(hasAvailableSlot([...slots, { start: 'saved', available: true }]), true)
})

test('clearing selections only unmarks saved slots that are still editable', () => {
  const slots = [
    { start: 'open', available: true },
    { start: 'empty', available: false },
    { start: 'booked', available: true, booked: true },
    { start: 'elapsed', available: true, past: true },
  ]
  assert.deepEqual(clearSelections(slots), { open: false })
})

test('dragging selects only the starting day and skips elapsed and booked slots', () => {
  const slot = (day, hour, flags) => ({ day, hour, start: `${day}-${hour}`, ...flags })
  const anchor = slot(2, 10)
  const slots = [anchor, slot(2, 11, { available: true }), slot(2, 12, { booked: true }),
    slot(2, 13), slot(2, 14, { past: true }), slot(3, 13), slot(3, 11)]
  const edits = { '2-11': false, '3-11': true }

  assert.deepEqual(selectColumn(slots, anchor, 14, edits), {
    '2-10': true, '2-13': true, '3-11': true,
  })
  assert.deepEqual(selectColumn(slots, anchor, 10, edits), { ...edits, '2-10': true })
})
