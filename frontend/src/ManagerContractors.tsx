import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, isFixtureMode } from './api/client'
import { contractorInboxHref } from './repairNotifications'
import type { Contractor } from './types/domain'

interface Props {
  region: string
  contractors: Contractor[] | undefined
  loadError: boolean
  onAdded: (contractor: Contractor) => void
}

export function ManagerContractors({ region, contractors, loadError, onAdded }: Props) {
  const [saving, setSaving] = useState(false)
  const [regionDraft, setRegionDraft] = useState<string>()
  const [error, setError] = useState('')
  const [added, setAdded] = useState('')

  async function addContractor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving || !contractors) return
    const form = event.currentTarget
    const fields = new FormData(form)
    setSaving(true)
    setError('')
    setAdded('')
    try {
      const contractor = await api.addContractor({
        name: String(fields.get('name')).trim(),
        slug: String(fields.get('slug')).trim(),
        region: String(fields.get('region')).trim(),
      })
      onAdded(contractor)
      setAdded(contractor.name + ' was added.')
      form.reset()
      setRegionDraft(undefined)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not add the contractor.')
    } finally {
      setSaving(false)
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
              <a href={contractorInboxHref(contractor.slug)} aria-label={`Open ${contractor.name} inbox`}>Open inbox</a>
            </li>
          ))}
        </ul>}
        <form onSubmit={(event) => void addContractor(event)}>
          <fieldset disabled={saving}>
            <legend>Add a simulated heating contractor</legend>
            <div className="manager-contractor-fields">
              <label>Company name<input name="name" required maxLength={100} /></label>
              <label>Service region<input name="region" required maxLength={80} value={regionDraft ?? region}
                onChange={(event) => setRegionDraft(event.target.value)} /></label>
              <label>Inbox slug<input name="slug" required maxLength={48}
                pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="aachen-heating"
                aria-describedby="contractor-slug-help" /></label>
            </div>
            <p id="contractor-slug-help" className="muted">Use lowercase letters, numbers and hyphens in the inbox slug.</p>
            <button type="submit">{saving ? 'Adding…' : 'Add contractor'}</button>
          </fieldset>
        </form>
        {error && <p className="error" role="alert">{error}</p>}
        {added && <p role="status">{added}</p>}
      </>}
    </section>
  )
}
