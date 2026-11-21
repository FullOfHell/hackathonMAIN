import type { TimetableSlot } from './types/domain'

export function hasAvailableSlot(slots: TimetableSlot[], edits: Record<string, boolean> = {}) {
  return slots.some((slot) => !slot.past && !slot.booked && (edits[slot.start] ?? slot.available))
}

export function clearSelections(slots: TimetableSlot[]): Record<string, boolean> {
  const edits: Record<string, boolean> = {}
  for (const slot of slots) {
    if (slot.available && !slot.past && !slot.booked) edits[slot.start] = false
  }
  return edits
}

export function selectColumn(
  slots: TimetableSlot[], anchor: TimetableSlot, endHour: number, edits: Record<string, boolean>,
) {
  const firstHour = Math.min(anchor.hour, endHour)
  const lastHour = Math.max(anchor.hour, endHour)
  const next = { ...edits }
  for (const slot of slots) {
    if (slot.past || slot.booked || slot.day !== anchor.day
      || slot.hour < firstHour || slot.hour > lastHour) continue
    if (slot.available) delete next[slot.start]
    else next[slot.start] = true
  }
  return next
}
