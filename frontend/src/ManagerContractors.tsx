import { useState } from 'react'
import { useActionFeedback } from './actionFeedback'
import type { FormEvent } from 'react'
import { api, isFixtureMode } from './api/client'
import { contractorInboxHref } from './repairNotifications'
import type { Contractor } from './types/domain'

interface Props {
  region: string
  contractors: Contractor[] | undefined
  loadError: boolean
  onSaved: (contractor: Contractor) => void
  onRemoved: (slug: string) => void
}

export function ManagerContractors({ region, contractors, loadError, onSaved, onRemoved }: Props) {
  const notify = useActionFeedback()
  const [saving, setSaving] = useState(false)
  const [regionDraft, setRegionDraft] = useState<string>()
  const [removing, setRemoving] = useState<string>()
  const [confirming, setConfirming] = useState<string>()
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const busy = saving || Boolean(removing)

  async function saveContractor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || !contractors) return
    const form = event.currentTarget
    const fields = new FormData(form)
    setSaving(true)
    setError('')
    setStatus('')
    try {
      const name = String(fields.get('name')).trim()
      const contractor = await api.addContractor({
        name,
        slug: String(fields.get('slug')).trim(),
        region: String(fields.get('region')).trim(),
      })
      onSaved(contractor)
      const message = `${contractor.name} was added.`
      notify('success', message)
      setStatus(message)
      form.reset()
      setRegionDraft(undefined)
    } catch (failure) {
      const message = failure instanceof Error ? failure.message : 'Could not save the contractor.'
      notify('error', message)
      setError(message)
    } finally {
      setSaving(false)
    }
  }

  async function removeContractor(contractor: Contractor) {
    if (busy) return
    setRemoving(contractor.slug)
    setError('')
    setStatus('')
    try {
      await api.removeContractor(contractor.slug)
      onRemoved(contractor.slug)
      setConfirming(undefined)
      const message = `${contractor.name} was removed.`
      setStatus(message)
      notify('success', message)
    } catch (failure) {
      const message = failure instanceof Error ? failure.message : 'Could not remove the contractor.'
      setError(message)
      notify('error', message)
    } finally {
      setRemoving(undefined)
    }
  }

  return (
    <section className="panel manager-contractors" aria-labelledby="manager-contractors-title">
      <h2 id="manager-contractors-title">Contractors</h2>
      {isFixtureMode ? <p>Connect to FastAPI to add a contractor.</p>
        : loadError ? <p className="error" role="alert">Could not load contractors. Refresh to try again.</p>
          : !contractors ? <p role="status">Loading contractors…</p> : <>
        {contractors.length > 0 && <ul className="manager-contractor-list">
          {contractors.map((contractor) => (
            <li key={contractor.slug}>
              <span><strong>{contractor.name}</strong> · {contractor.regions.join(', ')}</span>
              <div className="manager-contractor-actions">
                <a className="button secondary" href={contractorInboxHref(contractor.slug)}
                  aria-label={`Open ${contractor.name} inbox`}>Open inbox</a>
                <button type="button" className="secondary" disabled={busy || confirming === contractor.slug}
                  onClick={() => setConfirming(contractor.slug)} aria-label={`Delete ${contractor.name}`}>Delete</button>
              </div>
              {confirming === contractor.slug && <div className="manager-contractor-confirmation"
                role="group" aria-label={`Confirm removal of ${contractor.name}`}>
                <p>Remove {contractor.name} and hide their assigned repairs from this list?</p>
                <button type="button" disabled={busy} onClick={() => void removeContractor(contractor)}>
                  {removing === contractor.slug ? 'Removing…' : 'Confirm removal'}
                </button>{' '}
                <button type="button" className="secondary" disabled={busy} onClick={() => setConfirming(undefined)}>Cancel</button>
              </div>}
            </li>
          ))}
        </ul>}
        <form onSubmit={(event) => void saveContractor(event)}>
          <fieldset disabled={busy}>
            <legend>Add a simulated heating contractor</legend>
            <div className="manager-contractor-fields">
              <label>Company name<input name="name" required maxLength={100} /></label>
              <label>City<input name="region" required maxLength={80} value={regionDraft ?? region}
                onChange={(event) => setRegionDraft(event.target.value)} /></label>
              <label>Inbox slug<input name="slug" required maxLength={48}
                pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="aachen-heating"
                aria-describedby="contractor-slug-help" /></label>
            </div>
            <p id="contractor-slug-help" className="muted">Use lowercase letters, numbers and hyphens in the inbox slug.</p>
            <button type="submit">{saving ? 'Saving…' : 'Add contractor'}</button>
          </fieldset>
        </form>
        {error && <p className="error" role="alert">{error}</p>}
        {status && <p role="status">{status}</p>}
      </>}
    </section>
  )
}
