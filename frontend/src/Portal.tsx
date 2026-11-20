import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, isFixtureMode } from './api/client'
import { VoiceDraft } from './VoiceDraft'
import { CaseProgress, CaseTimeline, RepairOutcome } from './CaseViews'
import { caseStatusLabel, formatTime, slotLabel, statusLabel } from './caseDisplay'
import { availabilityPrefix, intakeQuestions, makeIntakeReview, possibleGasLeak, reportLimit, reviewEntries, reviewSymptoms, safetyMessage } from './intake'
import type { IntakeReview } from './intake'
import type {
  IntakeRequest, MaintenanceCase, MissingIntakeField, PartnerAction, PartnerCommand,
  PartnerInboxJob, RepairInvoiceInput, UnitContext,
} from './types/domain'
import './Portal.css'

const shortcuts = ['No heat at all', 'Radiators are lukewarm', 'Some radiators are cold']
const steps = ['Describe', 'Review', 'Approve']

function useLoad<T>(load: () => Promise<T>) {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{ data?: T; failed?: boolean }>({})
  useEffect(() => {
    let active = true
    load().then(
      (data) => { if (active) setResult({ data }) },
      () => { if (active) setResult({ failed: true }) },
    )
    return () => { active = false }
  }, [load, attempt])
  return {
    ...result,
    refreshing: attempt > 0 && !result.data && !result.failed,
    refreshed: attempt > 0 && Boolean(result.data),
    reload: () => { setResult({}); setAttempt((value) => value + 1) },
  }
}

const unitId = 'unit_4b'
const loadHome = () => api.getUnitContext(unitId)
const loadUnitCases = () => api.listUnitCases(unitId)
const views = {
  '#report': 'Report broken heating', '#cases': 'My cases',
  '#inbox': 'HeatFix Aachen inbox', '#manager': 'Property manager',
}

function currentView(): keyof typeof views {
  const hash = location.hash
  return hash === '#cases' || hash === '#inbox' || hash === '#manager' ? hash : '#report'
}

function App() {
  const [view, setView] = useState(currentView)
  useEffect(() => {
    const navigate = () => setView(currentView())
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])
  return (
    <>
      <header className="masthead">
        <div className="masthead-inner">
          <nav aria-label="Demo views">
            <a className="brand" href="#report">centrix</a>
            <div className="nav-links">
              <a href="#report" aria-current={view === '#report' ? 'page' : undefined}>Report</a>
              <a href="#cases" aria-current={view === '#cases' ? 'page' : undefined}>My cases</a>
              <a href="#inbox" aria-current={view === '#inbox' ? 'page' : undefined}>HeatFix inbox</a>
              <a href="#manager" aria-current={view === '#manager' ? 'page' : undefined}>Manager</a>
            </div>
          </nav>
          <h1>{views[view]}</h1>
        </div>
      </header>
      <main>
        <div hidden={view !== '#report'}><ResidentPortal active={view === '#report'} /></div>
        {view === '#cases' && <ResidentCases />}
        {view === '#inbox' && <Inbox />}
        {view === '#manager' && <Manager />}
      </main>
      <footer>{isFixtureMode ? 'Fixture mode. Reports are simulated and reset on reload.' : 'Hackathon demo using fictional properties and a simulated contractor.'}</footer>
    </>
  )
}

function ResidentPortal({ active }: { active: boolean }) {
  const home = useLoad(loadHome)
  if (home.failed) {
    return <section className="panel"><p role="alert">Your home details could not be loaded.</p><button onClick={home.reload}>Try again</button></section>
  }
  if (!home.data) return <section className="panel"><p role="status">Loading your home details…</p></section>
  if (!home.data.residents.length) return <section className="panel"><p role="alert">No resident is configured for this unit.</p></section>
  return <Report home={home.data} active={active} />
}

function sharingFields(home: UnitContext, current: MaintenanceCase) {
  const resident = home.residents[0]
  const values: Record<string, { label: string; value: string }> = {
    address: { label: 'Address', value: home.property.address },
    unit: { label: 'Unit', value: home.unit.label },
    issue: { label: 'Issue summary', value: [current.description,
      ...current.symptoms, ...current.availability_preferences,
      'Priority: ' + current.urgency].join('\n') },
    name: { label: 'Your name', value: resident.name },
    contact: { label: 'Email and phone', value: [resident.email, resident.phone].filter(Boolean).join(' · ') },
    heating_type: { label: 'Heating type', value: home.property.heating },
  }
  const request = current.sharing_request
  if (!request) return []
  return [...new Set([...request.required_fields, ...request.shareable_fields])]
    .map((key) => ({ key, ...values[key], required: request.required_fields.includes(key) }))
    .filter((field) => field.required || field.value)
}

function Report({ home, active }: { home: UnitContext; active: boolean }) {
  const [step, setStep] = useState(0)
  const [issue, setIssue] = useState('')
  const [hotWater, setHotWater] = useState<boolean | null>(null)
  const [question, setQuestion] = useState<MissingIntakeField | null>(null)
  const [followUp, setFollowUp] = useState('')
  const [reviewed, setReviewed] = useState<IntakeReview | null>(null)
  const [safety, setSafety] = useState(false)
  const [current, setCurrent] = useState<MaintenanceCase | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [approved, setApproved] = useState(false)
  const [sendAttempted, setSendAttempted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const resolvedQuestions = useRef(new Set<MissingIntakeField>())
  const resident = home.residents[0]
  const fields = current ? sharingFields(home, current) : []
  const request = current?.sharing_request
  const handoffReady = Boolean(request && fields.every((field) => !field.required || field.value))
  const hotWaterReported = /\bhot[\s-]+water\b/i.test(issue)

  async function inspectDraft(input: IntakeRequest) {
    if (submitting.current || input.report.length < 3) return
    setError('')
    setQuestion(null)
    if (possibleGasLeak(input.report)) {
      setSafety(true)
      return
    }
    if (reviewed?.input.report === input.report && reviewed.input.hot_water_affected === input.hot_water_affected) {
      setStep(1)
      return
    }

    submitting.current = true
    setBusy(true)
    try {
      const extraction = isFixtureMode ? null : await api.extractIntake(input).catch(() => null)
      const result = extraction?.result
      if (result?.safety_signal === 'possible_gas_leak') {
        setSafety(true)
        return
      }
      const next = result?.missing_information.find((field) => {
        if (resolvedQuestions.current.has(field)) return false
        if (field === 'hot_water_affected') return true
        if (field === 'availability_preferences' && result.missing_information.includes('heating_symptom')) return false
        const prefixLength = field === 'availability_preferences' ? availabilityPrefix.length : 0
        return input.report.length + prefixLength + 2 <= reportLimit
      })
      if (next) {
        setQuestion(next)
        return
      }
      setReviewed(makeIntakeReview(input, result))
      setStep(1)
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  function answerQuestion(answer: string | boolean | null) {
    if (!question || submitting.current) return
    resolvedQuestions.current.add(question)
    const prefix = question === 'availability_preferences' ? availabilityPrefix : ''
    const report = typeof answer === 'string' ? `${issue.trim()}\n${prefix}${answer.trim()}` : issue.trim()
    const hotWaterAnswer = typeof answer === 'boolean' ? answer : hotWater
    setIssue(report)
    setHotWater(hotWaterAnswer)
    setFollowUp('')
    void inspectDraft({ report, hot_water_affected: hotWaterAnswer })
  }

  function review(event: FormEvent) {
    event.preventDefault()
    if (safety) return
    if (question && followUp.trim()) answerQuestion(followUp)
    else if (!question) void inspectDraft({
      report: issue.trim(), hot_water_affected: isFixtureMode && hotWaterReported ? null : hotWater,
    })
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (submitting.current) return
    if (step === 1 && reviewed && possibleGasLeak([reviewed.description, reviewed.symptoms, reviewed.availability].join('\n'))) {
      setSafety(true)
      return
    }
    submitting.current = true
    setBusy(true)
    setError('')
    try {
      if (step === 1 && reviewed) {
        const created = await api.createCase({
          unit_id: home.unit_id, resident_id: resident.id, issue_type: 'heating_repair',
          description: reviewed.description.trim(), source_channel: 'portal_chat',
          symptoms: reviewSymptoms(reviewed.symptoms), availability_preferences: reviewEntries(reviewed.availability),
          urgency: reviewed.urgency || 'normal',
        })
        setCurrent(created)
        setStep(2)
      } else if (current && request && handoffReady && approved) {
        setSendAttempted(true)
        const result = await api.approveSharing(current.id, {
          approved_by: resident.id, channel: 'portal_chat',
          approved_fields: [...request.required_fields, ...selected],
        })
        setCurrent(result)
        if (!result.partner_job_id) setError('The contractor has not confirmed receipt. Check this case before trying again.')
      }
    } catch {
      if (current) {
        const latest = await api.getCase(current.id).catch(() => null)
        if (latest?.partner_job_id || latest?.status === 'NEEDS_HUMAN_REVIEW') {
          setCurrent(latest)
        } else {
          setError('HeatFix receipt could not be confirmed. You can retry sending this same case.')
        }
      } else {
        setError('Your case could not be saved. Your report is still here.')
      }
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  function reset() {
    setIssue(''); setHotWater(null); setReviewed(null); setQuestion(null); setFollowUp(''); setSafety(false)
    resolvedQuestions.current.clear()
    setCurrent(null); setSelected([])
    setApproved(false); setSendAttempted(false); setError(''); setStep(0)
  }

  const sent = Boolean(current?.partner_job_id)
  const stepHeading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    if (step > 0) stepHeading.current?.focus()
  }, [step, sent])

  return (
    <div className="report-layout">
      <section className="panel report-panel" aria-label="Heating report">
        {!sent && <ol className="steps" aria-label="Report progress">
          {steps.map((label, index) => <li key={label} aria-current={step === index ? 'step' : undefined}>{label}</li>)}
        </ol>}
        {step === 0 && <form onSubmit={review}>
          {question === 'hot_water_affected' ? <fieldset disabled={busy}>
            <legend>{intakeQuestions[question]}</legend>
            <div className="actions">
              <button type="button" onClick={() => answerQuestion(true)}>Yes</button>
              <button type="button" onClick={() => answerQuestion(false)}>No</button>
              <button type="button" className="secondary" onClick={() => answerQuestion(null)}>Skip</button>
            </div>
          </fieldset> : question ? <>
            <label htmlFor="intake-follow-up"><strong>{intakeQuestions[question]}</strong></label>
            <textarea id="intake-follow-up" value={followUp} onChange={(event) => setFollowUp(event.target.value)} rows={3}
              maxLength={reportLimit - issue.trim().length - 1 - (question === 'availability_preferences' ? availabilityPrefix.length : 0)} disabled={busy} />
            <div className="actions">
              <button disabled={busy || !followUp.trim()}>Continue</button>
              {question === 'availability_preferences' && <button type="button" className="secondary"
                onClick={() => answerQuestion(null)}>Skip</button>}
            </div>
          </> : <>
            <label htmlFor="report"><strong>What’s happening with your heating?</strong></label>
            <textarea id="report" value={issue} onChange={(event) => { setIssue(event.target.value); setSafety(false) }}
              placeholder="For example, my radiators have been cold since last night." rows={4} maxLength={reportLimit} disabled={busy} />
            <div className="shortcuts" aria-label="Report suggestions">
              {shortcuts.map((text) => <button key={text} type="button" className="secondary chip"
                onClick={() => { setIssue((value) => value.trim() ? value.trim() + '\n' + text : text); setSafety(false) }}
                disabled={busy || issue.trim().length + text.length + 1 > reportLimit}>{text}</button>)}
            </div>
            {active && !isFixtureMode && <VoiceDraft remaining={reportLimit - issue.trim().length - Number(Boolean(issue.trim()))}
              disabled={busy} onAdd={(text) => {
                setIssue((draft) => [draft.trim(), text].filter(Boolean).join('\n'))
                setSafety(false)
              }} />}
            {isFixtureMode && !hotWaterReported && <fieldset>
              <legend>Is hot water also affected? <span className="muted">(optional)</span></legend>
              <div className="radio-group">
                {([[true, 'Yes'], [false, 'No'], [null, 'Not sure']] as const).map(([value, label]) =>
                  <label key={label}><input type="radio" name="hot-water" checked={hotWater === value}
                    onChange={() => setHotWater(value)} /> {label}</label>)}
              </div>
            </fieldset>}
            <div className="actions"><button disabled={busy || safety || issue.trim().length < 3}>
              {busy ? 'Checking report…' : 'Review summary'}
            </button></div>
          </>}
          {question && <div className="actions"><button type="button" className="secondary" onClick={() => {
            setQuestion(null); setFollowUp('')
          }}>Edit report</button></div>}
          {safety && <p className="error" role="alert">{safetyMessage}</p>}
        </form>}
        {step === 1 && reviewed && <form onSubmit={save}>
          <h2 ref={stepHeading} tabIndex={-1}>Review your report</h2>
          <label htmlFor="summary">Issue summary</label>
          <textarea id="summary" value={reviewed.description} rows={5} maxLength={2000}
            onChange={(event) => { setReviewed({ ...reviewed, description: event.target.value }); setSafety(false) }} disabled={busy} />
          <label htmlFor="symptoms">Symptoms (one per line)</label>
          <textarea id="symptoms" value={reviewed.symptoms} rows={3}
            onChange={(event) => { setReviewed({ ...reviewed, symptoms: event.target.value }); setSafety(false) }} disabled={busy} />
          <label htmlFor="availability">Availability (optional, one preference per line)</label>
          <textarea id="availability" value={reviewed.availability} rows={2}
            onChange={(event) => { setReviewed({ ...reviewed, availability: event.target.value }); setSafety(false) }} disabled={busy} />
          <label htmlFor="urgency">Priority </label>
          <select id="urgency" value={reviewed.urgency} disabled={busy} onChange={(event) =>
            setReviewed({ ...reviewed, urgency: event.target.value as IntakeReview['urgency'] })}>
            <option value="">Normal (default)</option><option value="low">Low</option>
            <option value="normal">Normal</option><option value="high">High</option>
          </select>
          {safety && <p className="error" role="alert">{safetyMessage}</p>}
          {error && <p className="error" role="alert">{error}</p>}
          <div className="actions">
            <button type="button" className="secondary" disabled={busy} onClick={() => { setError(''); setSafety(false); setStep(0) }}>Back</button>
            <button disabled={busy || safety || reviewed.description.trim().length < 3}>{busy ? 'Saving…' : 'Continue to sharing'}</button>
          </div>
        </form>}
        {step === 2 && current && !sent && (request ? <form onSubmit={save}>
          <h2 ref={stepHeading} tabIndex={-1}>Share with {request.partner.name}</h2>
          <p className="muted">Choose which extra details to include with the repair request.</p>
          <fieldset>
            <legend>Required details</legend>
            {fields.filter((field) => field.required).map((field) =>
              <div className="field-row" key={field.key}><strong>{field.label || field.key}</strong><span>{field.value || 'Unavailable'}</span></div>)}
          </fieldset>
          {fields.some((field) => !field.required) && <fieldset disabled={busy || sendAttempted}>
            <legend>Optional details</legend>
            {fields.filter((field) => !field.required).map((field) =>
              <label className="field-row selectable" key={field.key}>
                <input type="checkbox" checked={selected.includes(field.key)} onChange={(event) => {
                  setSelected(event.target.checked ? [...selected, field.key] : selected.filter((key) => key !== field.key))
                  setApproved(false)
                }} />
                <span><strong>{field.label}</strong><span>{field.value}</span></span>
              </label>)}
          </fieldset>}
          <label className="confirmation"><input type="checkbox" checked={approved}
            disabled={busy || sendAttempted || !handoffReady} onChange={(event) => setApproved(event.target.checked)} />
            I approve sharing these details with {request.partner.name}.
          </label>
          {!handoffReady && <p className="error" role="alert">Some required details are unavailable. The report cannot be sent.</p>}
          {error && <p className="error" role="alert">{error}</p>}
          <button disabled={!approved || busy || !handoffReady}>{busy ? 'Sending…' : error ? 'Retry sending' : 'Approve and send'}</button>
        </form> : <div>
          <h2 ref={stepHeading} tabIndex={-1}>{current.status === 'NO_PROVIDER_AVAILABLE' ? 'No repair partner available' : 'Report saved for review'}</h2>
          <p>Case {current.id}. Contractor receipt has not been confirmed.</p>
          <p>{current.description}</p>
          <CaseTimeline caseId={current.id} />
          <button className="secondary" onClick={reset} disabled={busy}>Report another issue</button>
        </div>)}
        {sent && current && <div>
          <h2 ref={stepHeading} tabIndex={-1}>{isFixtureMode ? 'Demo job created' : 'HeatFix has your report'}</h2>
          <p>Case {current.id} · Job {current.partner_job_id}</p>
          <CaseProgress key={current.id} initial={current} active={active} />
          <div className="actions">
            <a className="button" href="#inbox">View HeatFix inbox</a>
            <button className="secondary" disabled={busy} onClick={reset}>Report another issue</button>
          </div>
        </div>}
      </section>
      <aside className="panel">
        <h2>Your home</h2>
        <p className="muted">Already on file</p>
        <dl className="home-details">
          <dt>Resident</dt><dd>{resident.name}</dd>
          <dt>Address</dt><dd>{home.property.address}</dd>
          <dt>Unit</dt><dd>{home.unit.label}</dd>
          <dt>Heating</dt><dd>{home.property.heating}</dd>
        </dl>
      </aside>
    </div>
  )
}

function Inbox() {
  const jobs = useLoad(api.listPartnerJobs)
  return (
    <section className="inbox" aria-label="Incoming repair jobs">
      <div className="inbox-heading"><h2>Incoming jobs</h2>
        <button className="secondary" disabled={jobs.refreshing} onClick={jobs.reload}>
          {jobs.refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>
      {jobs.refreshed && <p className="muted" role="status">Inbox updated.</p>}
      {jobs.failed ? <p className="panel error" role="alert">The HeatFix inbox could not be loaded. Try refreshing.</p>
        : !jobs.data ? <p className="panel" role="status">Loading jobs…</p>
          : !jobs.data.length ? <p className="panel">No jobs yet. Approved reports will appear here.</p>
            : jobs.data.map((job) => <JobCard key={job.id} job={job} />)}
    </section>
  )
}

const labels: Record<PartnerAction, string> = {
  accept: 'Accept', reject: 'Reject', 'offer-slots': 'Offer slots',
  start: 'Start repair', complete: 'Complete repair', invoice: 'Submit demo invoice',
}
const availableActions: Record<string, PartnerAction[]> = {
  received: ['accept', 'reject'], accepted: ['offer-slots', 'reject'],
  scheduled: ['start'], in_progress: ['complete'],
  completed: ['invoice'],
}
const jobChecks: Record<string, {
  action: 'accept' | 'reject' | 'offer-slots' | 'start'
  label: string
  confirmation: string
  missing: string
  target?: string
}> = {
  accepted: {
    action: 'accept', label: 'Check acceptance', confirmation: 'Acceptance confirmed on the resident case.',
    missing: 'Acceptance is still missing from the resident case.',
  },
  rejected: {
    action: 'reject', label: 'Check rejection', confirmation: 'Rejection confirmed on the resident case.',
    missing: 'Rejection is still missing from the resident case.', target: 'DECLINED',
  },
  slots_offered: {
    action: 'offer-slots', label: 'Check slot delivery', confirmation: 'The offered slots reached the resident case.',
    missing: 'The offered slots have not reached the resident case.', target: 'SLOTS_OFFERED',
  },
  in_progress: {
    action: 'start', label: 'Check repair start', confirmation: 'Repair start confirmed on the resident case.',
    missing: 'Repair start is still missing from the resident case.', target: 'IN_PROGRESS',
  },
}

function syntheticInvoice(jobId: string): RepairInvoiceInput {
  return { invoice_number: 'HF-DEMO-' + jobId, description: 'Heating repair and labour', amount_cents: 12500, currency: 'EUR' }
}

function JobCard({ job: initial }: { job: PartnerInboxJob }) {
  const [job, setJob] = useState(initial)
  const [pending, setPending] = useState<PartnerAction | null>(null)
  const [retry, setRetry] = useState<PartnerCommand | null>(null)
  const [editing, setEditing] = useState<'complete' | 'invoice' | null>(null)
  const [summary, setSummary] = useState('')
  const [error, setError] = useState('')
  const [checking, setChecking] = useState(false)
  const [confirmation, setConfirmation] = useState('')
  const submitting = useRef(false)
  const { property, issue, resident } = job.payload
  const actions = retry ? [retry.action] : availableActions[job.status] ?? []
  const check = jobChecks[job.status]
  const invoice = syntheticInvoice(job.id)

  async function act(command: PartnerCommand) {
    if (submitting.current) return
    submitting.current = true
    const { action } = command
    setPending(action)
    setError('')
    setConfirmation('')
    try {
      const updated = await api.updatePartnerJob(job.id, command)
      setJob(updated)
      setRetry(null)
      setEditing(null)
      const acknowledged = jobChecks[updated.status]
      if (acknowledged?.action === action) setConfirmation(acknowledged.confirmation)
    } catch (failure) {
      setRetry(command)
      setError(failure instanceof Error ? failure.message : 'The partner action could not be confirmed.')
    } finally {
      submitting.current = false
      setPending(null)
    }
  }

  async function checkDelivery() {
    if (!check || submitting.current) return
    submitting.current = true
    setChecking(true)
    setConfirmation('')
    setError('')
    try {
      const events = await api.getCaseEvents(job.request_id)
      const confirmed = events.some((event) => check.target
        ? event.type === 'case.status_changed' && event.payload.to === check.target
        : event.type === 'partner.accepted')
      if (confirmed) {
        setConfirmation(check.confirmation)
      } else {
        setRetry({ action: check.action })
        setError(check.missing + ' Retry sending it.')
      }
    } catch {
      setError('The resident case could not be checked. Try again.')
    } finally {
      submitting.current = false
      setChecking(false)
    }
  }

  function begin(action: PartnerAction) {
    if (retry) void act(retry)
    else if (action === 'complete' || action === 'invoice') setEditing(action)
    else void act({ action })
  }

  return (
    <article className="panel job">
      <div className="inbox-heading"><h3>Heating repair</h3><span className="status" role="status">{caseStatusLabel(job.status)}</span></div>
      <p>{property.address} · Unit {property.unit}</p>
      <p className="issue-copy">{issue.description}</p>
      {property.heating_type && <p>Heating · {property.heating_type}</p>}
      {resident.name && <p>Resident · {resident.name}</p>}
      {resident.contact && <p>Contact · {[resident.contact.email, resident.contact.phone].filter(Boolean).join(' · ')}</p>}
      <p className="muted">{job.id} · {job.request_id} · <time dateTime={job.received_at}>{formatTime(job.received_at)}</time></p>
      {job.status === 'invoice_ready' && <p role="status">Repair and invoice saved.</p>}
      {editing && !retry && <form className="repair-outcome" onSubmit={(event) => {
        event.preventDefault()
        if (editing === 'complete' && summary.trim()) void act({ action: 'complete', body: { summary: summary.trim() } })
        if (editing === 'invoice') void act({ action: 'invoice', body: invoice })
      }}>
        {editing === 'complete' ? <label>Repair summary
          <textarea rows={3} maxLength={2000} required value={summary}
            onChange={(event) => setSummary(event.target.value)} disabled={Boolean(pending)} />
        </label> : <p>Demo invoice {invoice.invoice_number} · €125.00 · {invoice.description}</p>}
        <div className="actions">
          <button type="submit" disabled={Boolean(pending) || (editing === 'complete' && !summary.trim())}>
            {pending ? 'Saving…' : editing === 'complete' ? 'Save completion' : 'Confirm demo invoice'}
          </button>
          <button type="button" className="secondary" disabled={Boolean(pending)} onClick={() => setEditing(null)}>Back</button>
        </div>
      </form>}
      {error && <p className="error" role="alert">{error}</p>}
      {check && !retry && !editing && <div className="actions">
        <button className="secondary" disabled={checking || Boolean(pending)} onClick={() => void checkDelivery()}>
          {checking ? 'Checking resident case…' : check.label}
        </button>
      </div>}
      {confirmation && <p className="muted" role="status">{confirmation}</p>}
      {actions.length > 0 && (!editing || retry) && <div className="actions" aria-label="Partner job actions">
        {actions.map((action) => (
          <button key={action} className={action === 'reject' ? 'secondary' : undefined}
            disabled={checking || Boolean(pending)} onClick={() => begin(action)}>
            {pending === action ? 'Sending…' : retry?.action === action ? 'Retry ' + labels[action].toLowerCase()
              : labels[action]}
          </button>
        ))}
      </div>}
    </article>
  )
}

function Manager() {
  const home = useLoad(loadHome)
  const cases = useLoad(loadUnitCases)
  return (
    <section className="inbox" aria-label="Unit cases">
      <div className="inbox-heading">
        <div><h2>{home.data ? 'Unit ' + home.data.unit.label : 'Unit cases'}</h2>
          {home.data && <p>{home.data.property.address}</p>}
          {home.failed && <p role="alert">Unit details unavailable.</p>}</div>
        <button className="secondary" onClick={() => { home.reload(); cases.reload() }}>Refresh unit</button>
      </div>
      {cases.failed ? <p className="panel error" role="alert">Cases could not be loaded. Try refreshing.</p>
        : !cases.data ? <p className="panel" role="status">Loading cases…</p>
          : !cases.data.length ? <p className="panel">No cases for this unit yet.</p>
            : cases.data.map((item) => <ManagerCase key={item.id} item={item} />)}
    </section>
  )
}

function ResidentCases() {
  const home = useLoad(loadHome)
  const cases = useLoad(loadUnitCases)
  const residentId = home.data?.residents[0]?.id
  const ownCases = cases.data?.filter((item) => item.resident_id === residentId)

  return (
    <section className="inbox" aria-label="Resident cases">
      <div className="inbox-heading">
        <h2>Heating cases</h2>
        <button className="secondary" onClick={() => { home.reload(); cases.reload() }}>Refresh cases</button>
      </div>
      {home.failed || cases.failed ? <p className="panel error" role="alert">Your cases could not be loaded. Try refreshing.</p>
        : !home.data || !ownCases ? <p className="panel" role="status">Loading your cases…</p>
          : !ownCases.length ? <p className="panel">No heating reports yet.</p>
            : ownCases.map((item) => <ResidentCase key={item.id} item={item} />)}
    </section>
  )
}

function ResidentCase({ item }: { item: MaintenanceCase }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <article className="panel job">
      <div className="inbox-heading"><h3>Case {item.id}</h3><span className="status">{caseStatusLabel(item.status)}</span></div>
      <p className="issue-copy">{item.description}</p>
      <button className="secondary" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
        {expanded ? 'Hide case details' : 'View case details'}
      </button>
      {expanded && (item.partner_job_id ? <CaseProgress initial={item} active /> : <CaseTimeline caseId={item.id} />)}
    </article>
  )
}

function ManagerCase({ item }: { item: MaintenanceCase }) {
  const [showTimeline, setShowTimeline] = useState(false)
  const contractor = item.sharing_request?.partner.name ?? (item.partner_id === 'p_heatfix' ? 'HeatFix Aachen GmbH' : item.partner_id)
  return (
    <article className="panel job">
      <div className="inbox-heading"><h3>Case {item.id}</h3><span className="status">{caseStatusLabel(item.status)}</span></div>
      <p className="issue-copy">{item.description}</p>
      <dl className="home-details">
        <dt>Contractor</dt><dd>{contractor ?? 'Unassigned'}</dd>
        <dt>Sharing approval</dt><dd>{item.sharing_approval
          ? item.sharing_approval.shared_fields.map(statusLabel).join(', ') + ' · ' + formatTime(item.sharing_approval.recorded_at)
          : 'No approval recorded'}</dd>
        <dt>Appointment</dt><dd>{item.appointment ? slotLabel(item.appointment) : 'No confirmed appointment'}</dd>
      </dl>
      <RepairOutcome item={item} />
      <button className="secondary" aria-expanded={showTimeline} onClick={() => setShowTimeline(!showTimeline)}>
        {showTimeline ? 'Hide timeline' : 'Show timeline'}
      </button>
      {showTimeline && <CaseTimeline caseId={item.id} />}
    </article>
  )
}

export default App
