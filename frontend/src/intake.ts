import safety from '../../shared/intake-safety.json'
import type { IntakeRequest, IntakeResult, MissingIntakeField, Urgency } from './types/domain'

export const reportLimit = 1950
export const availabilityPrefix = 'Availability: '
export const safetyMessage = safety.message
const gasSignal = new RegExp(safety.possible_gas_leak, 'gi')
const gasNegation = new RegExp(safety.negation_prefix, 'i')

export const intakeQuestions: Record<MissingIntakeField, string> = {
  heating_symptom: 'What is happening with your heating?',
  hot_water_affected: 'Is hot water also affected?',
  availability_preferences: 'When are you usually home for a repair visit?',
}

export interface IntakeReview {
  input: IntakeRequest
  description: string
  symptoms: string
  availability: string
  urgency: Urgency | ''
}

const hotWaterNotes = new Map([
  ['hot_water_affected', 'Hot water is also affected.'],
  ['hot_water_working', 'Hot water still works.'],
])

export function possibleGasLeak(report: string) {
  return [...report.matchAll(gasSignal)].some((match) => !gasNegation.test(report.slice(0, match.index)))
}

export function makeIntakeReview(input: IntakeRequest, result?: IntakeResult): IntakeReview {
  const label = input.hot_water_affected === true ? 'hot_water_affected'
    : input.hot_water_affected === false ? 'hot_water_working' : ''
  const note = hotWaterNotes.get(label)
  const symptoms = result?.symptoms ?? (label ? [label] : [])
  return {
    input,
    description: [input.report, note].filter(Boolean).join('\n'),
    symptoms: symptoms.map((item) => hotWaterNotes.get(item) ?? item.replace(/\s+/g, ' ')).join('\n'),
    availability: (result?.availability_preferences ?? []).map((item) => item.replace(/\s+/g, ' ')).join('\n'),
    urgency: result?.urgency ?? '',
  }
}

export function reviewEntries(text: string) {
  return text.split('\n').map((item) => item.trim()).filter(Boolean)
}

export function reviewSymptoms(text: string) {
  return reviewEntries(text).map((item) => [...hotWaterNotes].find(([, note]) => note === item)?.[0] ?? item)
}
