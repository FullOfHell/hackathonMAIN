import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, isFixtureMode } from './api/client'
import { contractorInboxHref } from './repairNotifications'
import type { Contractor, ContractorRouting } from './types/domain'

interface Props {
  region: string
  contractors: Contractor[] | undefined
  loadError: boolean
  onSaved: (contractor: Contractor) => void
}

export function ManagerContractors({ region, contractors, loadError, onSaved }: Props) {
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState<Contractor>()
  const [regionDraft, setRegionDraft] = useState<string>()
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')

  function editContractor(contractor?: Contractor) {
    setEditing(contractor)
    setError('')
    setStatus('')
  }

  async function saveContractor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving || !contractors) return
    const form = event.currentTarget
    const fields = new FormData(form)
    setSaving(true)
    setError('')
    setStatus('')
    const routing: ContractorRouting = {
      quality_rating: Number(fields.get('quality_rating')),
      estimated_price_eur: Number(fields.get('estimated_price_eur')),
      latitude: Number(fields.get('latitude')),
      longitude: Number(fields.get('longitude')),
    }
    try {
      const contractor = editing
        ? await api.updateContractorRouting(editing.slug, routing)
        : await api.addContractor({
          name: String(fields.get('name')).trim(),
          slug: String(fields.get('slug')).trim(),
          region: String(fields.get('region')).trim(),
          routing,
        })
      onSaved(contractor)
      setStatus(editing ? `Matching details saved for ${contractor.name}.` : `${contractor.name} was added.`)
      form.reset()
      setRegionDraft(undefined)
      setEditing(undefined)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not save the contractor.')
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
              <span>{contractor.routing
                ? `${contractor.routing.quality_rating}/5 stars · €${contractor.routing.estimated_price_eur} estimate`
                : 'Matching details missing'}</span>
              <button type="button" className="secondary" disabled={saving} onClick={() => editContractor(contractor)}
                aria-label={`Edit matching details for ${contractor.name}`}>Edit</button>
              <a href={contractorInboxHref(contractor.slug)} aria-label={`Open ${contractor.name} inbox`}>Open inbox</a>
            </li>
          ))}
        </ul>}
        <form key={editing?.slug ?? 'new'} onSubmit={(event) => void saveContractor(event)}>
          <fieldset disabled={saving}>
            <legend>{editing ? `Matching details for ${editing.name}` : 'Add a simulated heating contractor'}</legend>
            <div className="manager-contractor-fields">
              {!editing && <>
                <label>Company name<input name="name" required maxLength={100} /></label>
                <label>Service region<input name="region" required maxLength={80} value={regionDraft ?? region}
                  onChange={(event) => setRegionDraft(event.target.value)} /></label>
                <label>Inbox slug<input name="slug" required maxLength={48}
                  pattern="[a-z0-9]+(-[a-z0-9]+)*" placeholder="aachen-heating"
                  aria-describedby="contractor-slug-help" /></label>
              </>}
              <label>Quality rating (1–5 stars)<input name="quality_rating" type="number" min={1} max={5}
                step={1} required defaultValue={editing?.routing?.quality_rating} /></label>
              <label>Estimated service price (€)<input name="estimated_price_eur" type="number" min={0.01}
                step={0.01} required defaultValue={editing?.routing?.estimated_price_eur} /></label>
              <label>Contractor latitude<input name="latitude" type="number" min={-90} max={90}
                step="any" required defaultValue={editing?.routing?.latitude} /></label>
              <label>Contractor longitude<input name="longitude" type="number" min={-180} max={180}
                step="any" required defaultValue={editing?.routing?.longitude} /></label>
            </div>
            {!editing && <p id="contractor-slug-help" className="muted">Use lowercase letters, numbers and hyphens in the inbox slug.</p>}
            <button type="submit">{saving ? 'Saving…' : editing ? 'Save matching details' : 'Add contractor'}</button>
            {editing && <button type="button" className="secondary" onClick={() => editContractor()}>Cancel</button>}
          </fieldset>
        </form>
        {error && <p className="error" role="alert">{error}</p>}
        {status && <p role="status">{status}</p>}
      </>}
    </section>
  )
}
