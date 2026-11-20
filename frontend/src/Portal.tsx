import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, isFixtureMode } from './api/client'
import { CaseProgress, CaseTimeline, RepairOutcome } from './CaseViews'
import { formatTime, slotLabel, statusLabel } from './caseDisplay'
import type { MaintenanceCase, PartnerAction, PartnerCommand, PartnerInboxJob, RepairInvoiceInput, UnitContext } from './types/domain'
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
  return { ...result, reload: () => { setResult({}); setAttempt((value) => value + 1) } }
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
  const [hotWater, setHotWater] = useState('')
  const [summary, setSummary] = useState('')
  const [current, setCurrent] = useState<MaintenanceCase | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [approved, setApproved] = useState(false)
  const [sendAttempted, setSendAttempted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const resident = home.residents[0]
  const fields = current ? sharingFields(home, current) : []
  const request = current?.sharing_request
  const handoffReady = Boolean(request && fields.every((field) => !field.required || field.value))
  const hotWaterReported = /\bhot[\s-]+water\b/i.test(issue)

  function review(event: FormEvent) {
    event.preventDefault()
    const note = hotWaterReported ? '' : hotWater === 'yes' ? '\nHot water is also affected.'
      : hotWater === 'no' ? '\nHot water still works.' : ''
    setSummary(issue.trim() + note)
    setStep(1)
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (submitting.current) return
    submitting.current = true
    setBusy(true)
    setError('')
    try {
      if (step === 1) {
        const created = await api.createCase({
          unit_id: home.unit_id, resident_id: resident.id, issue_type: 'heating_repair',
          description: summary.trim(), source_channel: 'portal_chat', symptoms: [], urgency: 'normal',
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
    setIssue(''); setHotWater(''); setSummary(''); setCurrent(null); setSelected([])
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
          <label htmlFor="report"><strong>What’s happening with your heating?</strong></label>
          <textarea id="report" value={issue} onChange={(event) => setIssue(event.target.value)}
            placeholder="For example, my radiators have been cold since last night." rows={4} maxLength={1950} />
          <div className="shortcuts" aria-label="Report suggestions">
            {shortcuts.map((text) => <button key={text} type="button" className="secondary chip"
              onClick={() => setIssue((value) => value.trim() ? value.trim() + '\n' + text : text)}
              disabled={issue.trim().length + text.length + 1 > 1950}>{text}</button>)}
          </div>
          {!hotWaterReported && <fieldset>
            <legend>Is hot water also affected? <span className="muted">(optional)</span></legend>
            <div className="radio-group">
              {[['yes', 'Yes'], ['no', 'No'], ['', 'Not sure']].map(([value, label]) =>
                <label key={label}><input type="radio" name="hot-water" value={value}
                  checked={hotWater === value} onChange={() => setHotWater(value)} /> {label}</label>)}
            </div>
          </fieldset>}
          <button disabled={issue.trim().length < 3}>Review summary</button>
        </form>}
        {step === 1 && <form onSubmit={save}>
          <h2 ref={stepHeading} tabIndex={-1}>Review your report</h2>
          <label htmlFor="summary">Issue summary</label>
          <textarea id="summary" value={summary} rows={5} maxLength={2000}
            onChange={(event) => setSummary(event.target.value)} disabled={busy} />
          {error && <p className="error" role="alert">{error}</p>}
          <div className="actions">
            <button type="button" className="secondary" disabled={busy} onClick={() => { setError(''); setStep(0) }}>Back</button>
            <button disabled={busy || summary.trim().length < 3}>{busy ? 'Saving…' : 'Continue to sharing'}</button>
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
      <div className="inbox-heading"><h2>Incoming jobs</h2><button className="secondary" onClick={jobs.reload}>Refresh</button></div>
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
  received: ['accept', 'reject'], accepted: ['offer-slots', 'reject', 'accept'],
  slots_offered: ['offer-slots'], rejected: ['reject'], scheduled: ['start'], in_progress: ['complete', 'start'],
  completed: ['invoice'],
}
const statusForAction: Record<PartnerAction, string> = {
  accept: 'accepted', reject: 'rejected', 'offer-slots': 'slots_offered', start: 'in_progress',
  complete: 'completed', invoice: 'invoice_ready',
}
const repeatLabels: Partial<Record<PartnerAction, string>> = {
  accept: 'Check acceptance', reject: 'Check rejection', 'offer-slots': 'Check slot delivery', start: 'Check repair start',
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
  const submitting = useRef(false)
  const { property, issue, resident } = job.payload
  const actions = retry ? [retry.action] : availableActions[job.status] ?? []
  const invoice = syntheticInvoice(job.id)

  async function act(command: PartnerCommand) {
    if (submitting.current) return
    submitting.current = true
    const { action } = command
    setPending(action)
    setError('')
    try {
      setJob(await api.updatePartnerJob(job.id, command))
      setRetry(null)
      setEditing(null)
    } catch (failure) {
      setRetry(command)
      setError(failure instanceof Error ? failure.message : 'The partner action could not be confirmed.')
    } finally {
      submitting.current = false
      setPending(null)
    }
  }

  function begin(action: PartnerAction) {
    if (retry) void act(retry)
    else if (action === 'complete' || action === 'invoice') setEditing(action)
    else void act({ action })
  }

  return (
    <article className="panel job">
      <div className="inbox-heading"><h3>Heating repair</h3><span className="status" role="status">{statusLabel(job.status)}</span></div>
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
      {actions.length > 0 && (!editing || retry) && <div className="actions" aria-label="Partner job actions">
        {actions.map((action) => {
          const repeat = job.status === statusForAction[action]
          return <button key={action} className={action === 'reject' || repeat ? 'secondary' : undefined}
            disabled={Boolean(pending)} onClick={() => begin(action)}>
            {pending === action ? 'Sending…' : retry?.action === action ? 'Retry ' + labels[action].toLowerCase()
              : repeat ? repeatLabels[action] ?? labels[action]
                : labels[action]}
          </button>
        })}
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
      <div className="inbox-heading"><h3>Case {item.id}</h3><span className="status">{statusLabel(item.status)}</span></div>
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
      <div className="inbox-heading"><h3>Case {item.id}</h3><span className="status">{statusLabel(item.status)}</span></div>
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
