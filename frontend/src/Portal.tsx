import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, isFixtureMode, residentHomeDetails } from './api/client'
import { VoiceDraft } from './VoiceDraft'
import { ResidentProfileEditor } from './ResidentProfileEditor'
import { NotificationBell } from './NotificationBell'
import { ManagerContractors } from './ManagerContractors'
import { ActionFeedback, feedbackDuration, useActionFeedback, useBeforeSend } from './actionFeedback'
import { SendWindow } from './SendWindow'
import type { ActionResult } from './actionFeedback'
import { contractorInboxHref, contractorInboxSlug, defaultContractorSlug } from './repairNotifications'
import { CaseProgress, CaseTimeline, RepairOutcome } from './CaseViews'
import { caseStatusLabel, formatTime, slotLabel, statusLabel } from './caseDisplay'
import { availabilityPrefix, intakeQuestions, makeIntakeReview, nextIntakeFollowUp, possibleGasLeak, reportLimit, reviewEntries, reviewSymptoms, safetyMessage } from './intake'
import type { IntakeFollowUp, IntakeReview } from './intake'
import type {
  Contractor, IntakeRequest, MaintenanceCase, ManagerRepair, PartnerAction, PartnerCommand,
  PartnerInboxJob, RepairInvoiceInput, Resident, ResidentProfileChanges, SharingApprovalRequest, SharingRequest, UnitContext,
} from './types/domain'
import './Portal.css'

const shortcuts = ['No heat at all', 'Radiators are lukewarm', 'Some radiators are cold']
const steps = ['Describe', 'Review', 'Approve']

function useLoad<T>(load: () => Promise<T>, label: string) {
  const notify = useActionFeedback()
  const manual = useRef(false)
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{ data?: T; failed?: boolean }>({})
  useEffect(() => {
    let active = true
    load().then(
      (data) => {
        if (!active) return
        setResult({ data })
        if (manual.current) notify('success', label + ' refreshed.')
        manual.current = false
      },
      () => {
        if (!active) return
        setResult({ failed: true })
        if (manual.current) notify('error', label + ' could not be loaded.')
        manual.current = false
      },
    )
    return () => { active = false }
  }, [load, attempt, label, notify])
  function reload(silent = false) {
    manual.current = !silent
    setResult({})
    setAttempt((value) => value + 1)
  }
  return {
    ...result,
    refreshing: attempt > 0 && !result.data && !result.failed,
    refreshed: attempt > 0 && Boolean(result.data),
    reload: () => reload(), reloadSilently: () => reload(true),
  }
}

const unitId = 'unit_4b'
const loadHome = () => api.getUnitContext(unitId)
const loadUnitCases = () => api.listUnitCases(unitId)
const loadResidentCases = async () => {
  const [home, cases] = await Promise.all([loadHome(), loadUnitCases()])
  return cases.filter((item) => item.resident_id === home.residents[0]?.id)
}
const defaultInbox = { slug: defaultContractorSlug, name: 'HeatFix Aachen' }
const views = {
  '#report': 'Report broken heating', '#cases': 'My cases',
  '#manager': 'Property manager',
}

function App() {
  const [notice, setNotice] = useState<{ result: ActionResult; message: string }>()
  const notify = useCallback((result: ActionResult, message: string) => setNotice({ result, message }), [])
  useEffect(() => {
    if (!notice) return
    const timeout = window.setTimeout(() => setNotice(undefined), feedbackDuration)
    return () => window.clearTimeout(timeout)
  }, [notice])
  const [hash, setHash] = useState(() => location.hash)
  const partnerSlug = contractorInboxSlug(hash)
  const view = partnerSlug ? '#inbox' : (hash === '#cases' || hash === '#manager' ? hash : '#report')
  const [contractors, setContractors] = useState<Contractor[]>()
  const [contractorLoadFailed, setContractorLoadFailed] = useState(false)
  const inboxes = contractors ?? [defaultInbox]
  const inbox = inboxes.find((contractor) => contractor.slug === partnerSlug)
  const inboxTitle = partnerSlug === defaultContractorSlug ? 'HeatFix Aachen inbox'
    : inbox ? inbox.name + ' inbox' : 'Contractor inbox'

  useEffect(() => {
    if (isFixtureMode) return
    let active = true
    api.listContractors().then(
      (list) => { if (active) { setContractors(list); setContractorLoadFailed(false) } },
      () => { if (active) setContractorLoadFailed(true) },
    )
    return () => { active = false }
  }, [])
  useEffect(() => {
    const navigate = () => setHash(location.hash)
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])
  return (
    <ActionFeedback.Provider value={notify}><SendWindow>
      <header className="masthead">
        <div className="masthead-inner">
          <nav aria-label="Demo views">
            <a className="brand" href="#report">centrix</a>
            <div className="nav-links">
              <a href="#report" aria-current={view === '#report' ? 'page' : undefined}>Report</a>
              <a href="#cases" aria-current={view === '#cases' ? 'page' : undefined}>My cases</a>
              <span className="contractor-inbox-picker">
                <span aria-hidden="true">{inbox?.name ?? 'Contractors'}</span>
                <select className="contractor-inbox-select" aria-label="Contractor inbox" title="Choose a contractor inbox"
                  value={inbox?.slug ?? ''}
                  onChange={(event) => { location.hash = contractorInboxHref(event.target.value) }}>
                  <option value="" disabled>Contractor inbox</option>
                  {inboxes.map(({ slug, name }) => <option key={slug} value={slug}>{name}</option>)}
                </select>
              </span>
              <a href="#manager" aria-current={view === '#manager' ? 'page' : undefined}>Manager</a>
            </div>
            {view !== '#manager' && <NotificationBell key={partnerSlug ? 'contractor:' + partnerSlug : 'resident'} partnerSlug={partnerSlug} unitId={unitId} />}
          </nav>
          <h1>{view === '#inbox' ? inboxTitle : views[view]}</h1>
        </div>
      </header>
      <main>
        <div hidden={view !== '#report'}><ResidentPortal active={view === '#report'} /></div>
        {view === '#cases' && <ResidentCases />}
        {partnerSlug && <Inbox key={partnerSlug} partnerSlug={partnerSlug} />}
        {view === '#manager' && <Manager contractors={contractors} loadError={contractorLoadFailed}
          onAdded={(contractor) => setContractors((list) => [...(list ?? []), contractor])} />}
      </main>
      <div className="action-feedback" data-result={notice?.result}>
        <span role="status" aria-atomic="true">{notice?.message}</span>
        {notice && <button type="button" aria-label="Dismiss message" onClick={() => setNotice(undefined)}>×</button>}
      </div>
      <footer>{isFixtureMode ? 'Fixture mode. Reports are simulated and reset on reload.' : 'Hackathon demo using fictional properties and a simulated contractor.'}</footer>
    </SendWindow></ActionFeedback.Provider>
  )
}

function ResidentPortal({ active }: { active: boolean }) {
  const home = useLoad(loadHome, 'Home details')
  if (home.failed) {
    return <section className="panel"><p role="alert">Your home details could not be loaded.</p><button onClick={home.reload}>Try again</button></section>
  }
  if (!home.data) return <section className="panel"><p role="status">Loading your home details…</p></section>
  if (!home.data.residents.length) return <section className="panel"><p role="alert">No resident is configured for this unit.</p></section>
  return <Report home={home.data} active={active} />
}

function sharingFields(home: UnitContext, current: MaintenanceCase, resident: Resident) {
  const details = residentHomeDetails(home, resident)
  const values: Record<string, { label: string; value: string }> = {
    address: { label: 'Address', value: details.address },
    unit: { label: 'Unit', value: details.unit },
    issue: { label: 'Issue summary', value: [current.description,
      ...current.symptoms, ...current.availability_preferences,
      'Priority: ' + current.urgency].join('\n') },
    name: { label: 'Your name', value: resident.name },
    contact: { label: 'Email and phone', value: [resident.email, resident.phone].filter(Boolean).join(' · ') },
    heating_type: { label: 'Heating type', value: details.heating },
  }
  const request = current.sharing_request
  if (!request) return []
  return [...new Set([...request.required_fields, ...request.shareable_fields])]
    .map((key) => ({ key, ...values[key], required: request.required_fields.includes(key) }))
    .filter((field) => field.required || field.value)
}

function Report({ home, active }: { home: UnitContext; active: boolean }) {
  const beforeSend = useBeforeSend()
  const notify = useActionFeedback()
  const [step, setStep] = useState(0)
  const [issue, setIssue] = useState('')
  const [hotWater, setHotWater] = useState<boolean | null>(null)
  const [question, setQuestion] = useState<IntakeFollowUp | null>(null)
  const [followUp, setFollowUp] = useState('')
  const [reviewed, setReviewed] = useState<IntakeReview | null>(null)
  const [safety, setSafety] = useState(false)
  const [current, setCurrent] = useState<MaintenanceCase | null>(null)
  const [selected, setSelected] = useState<string[]>(['heating_type'])
  const [approved, setApproved] = useState(false)
  const [dispatch, setDispatch] = useState<{
    fields: ReturnType<typeof sharingFields>
    request: SharingRequest
    body: SharingApprovalRequest
  } | null>(null)
  const [resident, setResident] = useState(home.residents[0])
  const [profileSaving, setProfileSaving] = useState(false)
  const profileSave = useRef<Promise<boolean> | null>(null)
  const verifyProfile = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submitting = useRef(false)
  const resolvedQuestions = useRef(new Set<IntakeFollowUp>())
  const fields = dispatch?.fields ?? (current ? sharingFields(home, current, resident) : [])
  const isShared = (field: (typeof fields)[number]) => field.required || selected.includes(field.key)
  const sharedFields = fields.filter(isShared)
  const request = current?.sharing_request ?? (current?.status === 'PARTNER_REQUESTED' ? dispatch?.request : undefined)
  const awaitingConsentReceipt = Boolean(dispatch && !current?.sharing_approval)
  const handoffReady = Boolean(request && fields.every((field) => !field.required || field.value))
  const hotWaterReported = /\bhot[\s-]+water\b/i.test(issue)

  const draftId = !dispatch && current && !current.sharing_approval && step === 2 ? current.id : undefined
  const draftPartnerId = current?.partner_id

  useEffect(() => {
    if (!active || !draftId || !resident.address) return
    let reading = true
    api.getCase(draftId).then((latest) => {
      if (reading && !submitting.current) {
        setCurrent(latest)
        if (latest.partner_id !== draftPartnerId) setApproved(false)
      }
    }).catch(() => { /* The approval endpoint checks the recipient again before sending. */ })
    return () => { reading = false }
  }, [active, draftId, draftPartnerId, resident.address])

  function applyResident(updated: Resident) {
    const updatedFields = current && !dispatch ? sharingFields(home, current, updated).filter(isShared) : sharedFields
    const changedConsent = updatedFields.length !== sharedFields.length
      || sharedFields.some((field, index) => field.value !== updatedFields[index]?.value || field.key !== updatedFields[index]?.key)
    setResident(updated)
    if (changedConsent) setApproved(false)
    return changedConsent
  }

  function saveProfile(changes: ResidentProfileChanges) {
    if (profileSave.current) return profileSave.current
    setProfileSaving(true)
    profileSave.current = beforeSend('Save your profile edits').then(async (send) => {
      if (!send) return false
      const updated = await api.updateResidentProfile(home.unit_id, resident.id, changes)
      applyResident(updated)
      notify('success', 'Your details were saved.')
      verifyProfile.current = false
      return true
    }).catch((failure: unknown) => {
      // A lost PATCH response can follow a successful write. Recheck before granting new consent.
      verifyProfile.current = true
      notify('error', 'Your profile update could not be confirmed.')
      throw failure
    }).finally(() => {
      profileSave.current = null
      setProfileSaving(false)
    })
    return profileSave.current
  }

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
      const extraction = isFixtureMode ? null : await api.extractIntake(input).catch(() => {
        notify('error', 'Automatic review is unavailable. You can review your report manually.')
        return null
      })
      const result = extraction?.result
      if (result?.safety_signal === 'possible_gas_leak') {
        setSafety(true)
        return
      }
      const next = nextIntakeFollowUp(result, resolvedQuestions.current, input.report.length)
      if (next) {
        setQuestion(next)
        return
      }
      setReviewed(makeIntakeReview(input, result))
      if (extraction) notify('success', 'Your summary is ready to review.')
      setStep(1)
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  function answerQuestion(answer: string | boolean | null) {
    if (!question || submitting.current) return
    resolvedQuestions.current.add(question)
    const report = typeof answer === 'string' ? `${issue.trim()}\n${availabilityPrefix}${answer.trim()}` : issue.trim()
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
    function showError(message: string) {
      setError(message)
      notify('error', message)
    }
    event.preventDefault()
    if (submitting.current || (step === 2 && profileSave.current)) return
    if (step === 1 && reviewed && possibleGasLeak([reviewed.description, reviewed.symptoms, reviewed.availability].join('\n'))) {
      setSafety(true)
      return
    }
    submitting.current = true
    setBusy(true)
    setError('')
    try {
      if (step === 1 && reviewed) {
        if (!await beforeSend('Save your heating report')) return
        const created = await api.createCase({
          unit_id: home.unit_id, resident_id: resident.id, issue_type: 'heating_repair',
          description: reviewed.description.trim(), source_channel: 'portal_chat',
          symptoms: reviewSymptoms(reviewed.symptoms), availability_preferences: reviewEntries(reviewed.availability),
          urgency: reviewed.urgency || 'normal',
        })
        setCurrent(created)
        notify('success', 'Your heating report was saved.')
        setStep(2)
      } else if (current && request && handoffReady && approved) {
        if (!await beforeSend('Send repair request to ' + request.partner.name)) return
        if (!dispatch && verifyProfile.current) {
          const context = await api.getUnitContext(home.unit_id).catch(() => null)
          const latest = context?.residents.find((item) => item.id === resident.id)
          if (!latest) {
            showError('Your saved details could not be checked. Please try again.')
            return
          }
          verifyProfile.current = false
          if (applyResident(latest)) {
            showError('Your saved details changed. Review them and approve sharing again.')
            return
          }
        }
        const attempt = dispatch ?? { fields, request, body: {
          approved_by: resident.id, channel: 'portal_chat' as const, approved_fields: sharedFields.map((field) => field.key),
          expected_partner_id: request.partner.id,
        } }
        setDispatch(attempt)
        const result = await api.approveSharing(current.id, attempt.body)
        setCurrent(result)
        if (result.partner_job_id) notify('success', 'The contractor received your repair request.')
        else showError('The contractor has not confirmed receipt. Check this case before trying again.')
      }
    } catch {
      if (current) {
        const latest = await api.getCase(current.id).catch(() => null)
        if (latest?.partner_job_id || latest?.status === 'NEEDS_HUMAN_REVIEW') {
          setCurrent(latest)
          if (latest.partner_job_id) notify('success', 'The contractor received your repair request.')
          else notify('error', 'Dispatch needs manager review.')
        } else if (latest && !latest.sharing_approval && latest.partner_id !== current.partner_id) {
          const context = await api.getUnitContext(home.unit_id).catch(() => null)
          const updated = context?.residents.find((item) => item.id === resident.id)
          if (updated) applyResident(updated)
          setCurrent(latest)
          setApproved(false)
          setDispatch(null)
          showError(latest.sharing_request ? 'The contractor changed. Review and approve sharing again.'
            : 'No contractor covers the saved repair address.')
        } else {
          if (latest?.sharing_approval) setCurrent(latest)
          showError('The contractor’s receipt could not be confirmed. You can retry sending this same case.')
        }
      } else {
        showError('Your case could not be saved. Your report is still here.')
      }
    } finally {
      submitting.current = false
      setBusy(false)
    }
  }

  function reset() {
    setIssue(''); setHotWater(null); setReviewed(null); setQuestion(null); setFollowUp(''); setSafety(false)
    resolvedQuestions.current.clear()
    setCurrent(null); setSelected(['heating_type'])
    setApproved(false); setDispatch(null); setError(''); setStep(0)
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
              maxLength={reportLimit - issue.trim().length - 1 - availabilityPrefix.length} disabled={busy} />
            <div className="actions">
              <button disabled={busy || !followUp.trim()}>Continue</button>
              <button type="button" className="secondary" onClick={() => answerQuestion(null)}>Skip</button>
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
          {fields.some((field) => !field.required) && <fieldset disabled={busy || profileSaving || Boolean(dispatch)}>
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
            disabled={busy || profileSaving || Boolean(dispatch) || !handoffReady} onChange={(event) => setApproved(event.target.checked)} />
            I approve sharing these details with {request.partner.name}.
          </label>
          {!handoffReady && <p className="error" role="alert">Some required details are unavailable. The report cannot be sent.</p>}
          {error && <p className="error" role="alert">{error}</p>}
          <button disabled={!approved || busy || profileSaving || !handoffReady}>{busy ? 'Sending…' : dispatch ? 'Retry sending' : 'Approve and send'}</button>
        </form> : <div>
          <h2 ref={stepHeading} tabIndex={-1}>{current.status === 'NO_PROVIDER_AVAILABLE' ? 'No contractors are available in this location' : 'Report saved for review'}</h2>
          <p>{current.status === 'NO_PROVIDER_AVAILABLE'
            ? 'Your report was saved.'
            : `Case ${current.id}. Contractor receipt has not been confirmed.`}</p>
          <p>{current.description}</p>
          <CaseTimeline caseId={current.id} />
          <button className="secondary" onClick={reset} disabled={busy}>Report another issue</button>
        </div>)}
        {sent && current && <div>
          <h2 ref={stepHeading} tabIndex={-1}>{isFixtureMode ? 'Demo job created' : 'Your contractor has your report'}</h2>
          <p>Case {current.id} · Job {current.partner_job_id}</p>
          <CaseProgress key={current.id} initial={current} active={active} />
          <div className="actions">
            <button className="secondary" disabled={busy} onClick={reset}>Report another issue</button>
          </div>
        </div>}
      </section>
      <aside className="panel">
        <h2>Your home</h2>
        <ResidentProfileEditor resident={resident} homeDetails={residentHomeDetails(home, resident)} saving={profileSaving} blocked={awaitingConsentReceipt || (step === 2 && busy)}
          onSave={saveProfile} />
        {awaitingConsentReceipt && !busy && <p className="muted">Retry the handoff to confirm consent before editing your details.</p>}
      </aside>
    </div>
  )
}

function Inbox({ partnerSlug }: { partnerSlug: string }) {
  const loadJobs = useCallback(() => api.listPartnerJobs(partnerSlug), [partnerSlug])
  const jobs = useLoad(loadJobs, 'Contractor inbox')
  return (
    <section className="inbox" aria-label="Incoming repair jobs">
      <div className="inbox-heading"><h2>Incoming jobs</h2>
        <button className="secondary" disabled={jobs.refreshing} onClick={jobs.reload}>
          {jobs.refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>
      {jobs.refreshed && <p className="muted" role="status">Inbox updated.</p>}
      {jobs.failed ? <p className="panel error" role="alert">The contractor inbox could not be loaded. Try refreshing.</p>
        : !jobs.data ? <p className="panel" role="status">Loading jobs…</p>
          : !jobs.data.length ? <p className="panel">No jobs yet. Approved reports will appear here.</p>
            : jobs.data.map((job) => <JobCard key={job.id} job={job} partnerSlug={partnerSlug} />)}
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

function JobCard({ job: initial, partnerSlug }: { job: PartnerInboxJob; partnerSlug: string }) {
  const beforeSend = useBeforeSend()
  const notify = useActionFeedback()
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
      if (!await beforeSend(labels[action] + ' · ' + job.id)) return
      const updated = await api.updatePartnerJob(partnerSlug, job.id, command)
      setJob(updated)
      setRetry(null)
      setEditing(null)
      const acknowledged = jobChecks[updated.status]
      if (acknowledged?.action === action) setConfirmation(acknowledged.confirmation)
      notify('success', {
        accept: 'Repair assignment accepted.', reject: 'Repair assignment declined.',
        'offer-slots': 'Appointment times sent to the resident.', start: 'Repair start recorded.',
        complete: 'Completion report saved.', invoice: 'Invoice submitted.',
      }[action])
    } catch (failure) {
      setRetry(command)
      notify('error', labels[action] + ' could not be confirmed. You can retry.')
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
        notify('success', check.confirmation)
      } else {
        setRetry({ action: check.action })
        setError(check.missing + ' Retry sending it.')
        notify('error', check.missing)
      }
    } catch {
      setError('The resident case could not be checked. Try again.')
      notify('error', 'The resident case could not be checked.')
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
      <div className="inbox-heading"><h3 className="case-category">{caseStatusLabel(job.payload.service_type)}</h3>
        <span className="status" data-status={job.status.toLowerCase()} role="status">{caseStatusLabel(job.status)}</span></div>
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

function Manager(props: {
  contractors: Contractor[] | undefined
  loadError: boolean
  onAdded: (contractor: Contractor) => void
}) {
  const home = useLoad(loadHome, 'Home details')
  const repairs = useLoad(api.listManagerRepairs, 'Repairs')
  return (
    <div>
      <ManagerContractors {...props} region={home.data?.property.region ?? ''} onAdded={(contractor) => {
        props.onAdded(contractor)
        repairs.reloadSilently()
      }} />
      <section className="inbox" aria-label="Repairs by contractor">
        <div className="inbox-heading">
          <h2>Repairs by contractor</h2>
          <button className="secondary" disabled={repairs.refreshing} onClick={repairs.reload}>Refresh repairs</button>
        </div>
        {repairs.failed ? <p className="panel error" role="alert">Repairs could not be loaded. Try refreshing.</p>
          : !repairs.data ? <p className="panel" role="status">Loading repairs…</p>
            : !repairs.data.length ? <p className="panel">No repair reports yet.</p>
              : repairs.data.map(({ contractor, repairs: cases }) => {
                const groupId = 'repair-group-' + (contractor?.id ?? 'unassigned')
                return <section className="inbox manager-repair-group" key={groupId} aria-labelledby={groupId}>
                  <h3 id={groupId}>{contractor?.name ?? 'Unassigned'}</h3>
                  {cases.map((repair) => <ManagerCase key={repair.case.id} repair={repair} />)}
                </section>
              })}
      </section>
    </div>
  )
}

function ResidentCases() {
  const cases = useLoad(loadResidentCases, 'Your cases')
  const ownCases = cases.data

  return (
    <section className="inbox" aria-label="Resident cases">
      <div className="inbox-heading">
        <h2 className="case-category">Heating cases</h2>
        <button className="secondary" disabled={cases.refreshing} onClick={cases.reload}>Refresh cases</button>
      </div>
      {cases.failed ? <p className="panel error" role="alert">Your cases could not be loaded. Try refreshing.</p>
        : !ownCases ? <p className="panel" role="status">Loading your cases…</p>
          : !ownCases.length ? <p className="panel">No heating reports yet.</p>
            : ownCases.map((item) => <ResidentCase key={item.id} item={item} />)}
    </section>
  )
}

function ResidentCase({ item }: { item: MaintenanceCase }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <article className="panel job">
      <div className="inbox-heading"><h3>Case {item.id}</h3><span className="status" data-status={item.status.toLowerCase()}>{caseStatusLabel(item.status)}</span></div>
      <p className="issue-copy">{item.description}</p>
      <button className="secondary" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
        {expanded ? 'Hide case details' : 'View case details'}
      </button>
      {expanded && (item.partner_job_id ? <CaseProgress initial={item} active /> : <CaseTimeline caseId={item.id} />)}
    </article>
  )
}

function ManagerCase({ repair }: { repair: ManagerRepair }) {
  const { case: item, address, unit } = repair
  const [showTimeline, setShowTimeline] = useState(false)
  return (
    <article className="panel job">
      <div className="inbox-heading"><h4>Case {item.id}</h4><span className="status" data-status={item.status.toLowerCase()}>{caseStatusLabel(item.status)}</span></div>
      <p className="issue-copy">{item.description}</p>
      <dl className="home-details">
        <dt>Repair address</dt><dd>{address}</dd>
        <dt>Unit</dt><dd>{unit}</dd>
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
