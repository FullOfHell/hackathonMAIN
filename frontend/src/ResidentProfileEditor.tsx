import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { profileChanges } from './api/client'
import { FieldDropdown } from './PortalDropdown'
import type { Resident, ResidentHomeDetails, ResidentProfileChanges, ResidentProfileDraft } from './types/domain'

interface Props {
  resident: Resident
  homeDetails: ResidentHomeDetails
  saving: boolean
  blocked: boolean
  onSave: (changes: ResidentProfileChanges) => Promise<boolean>
}

export function ResidentProfileEditor({ resident, homeDetails, saving, blocked, onSave }: Props) {
  const [draft, setDraft] = useState<ResidentProfileDraft | null>(null)
  const [error, setError] = useState('')
  const editButton = useRef<HTMLButtonElement>(null)
  const nameInput = useRef<HTMLInputElement>(null)
  const changes = draft && profileChanges({ ...resident, ...homeDetails }, draft)

  function open() {
    setError('')
    setDraft({ name: resident.name, email: resident.email ?? '', phone: resident.phone ?? '',
      preferred_contact: resident.preferred_contact ?? '', ...homeDetails })
    requestAnimationFrame(() => nameInput.current?.focus())
  }

  function close() {
    setDraft(null)
    setError('')
    requestAnimationFrame(() => editButton.current?.focus())
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (saving || blocked || !changes || !Object.keys(changes).length) return
    setError('')
    try {
      if (await onSave(changes)) close()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Your details could not be saved. Please try again.')
    }
  }

  if (!draft) return <>
    <dl className="home-details">
      <dt>Resident</dt><dd>{resident.name}</dd>
      <dt>Email</dt><dd>{resident.email || 'Not on file'}</dd>
      <dt>Phone</dt><dd>{resident.phone || 'Not on file'}</dd>
      <dt>Preferred contact</dt><dd>{resident.preferred_contact || 'Not on file'}</dd>
    </dl>
    <dl className="home-details property-details">
      <dt>Address</dt><dd>{homeDetails.address}</dd>
      <dt>Unit</dt><dd>{homeDetails.unit}</dd>
      <dt>Heating</dt><dd>{homeDetails.heating || 'Not on file'}</dd>
    </dl>
    <button ref={editButton} type="button" className="secondary edit-profile" disabled={blocked} onClick={open}>
      Edit my details
    </button>
  </>

  return <form className="profile-editor" aria-label="Edit my details" onSubmit={save}>
    <fieldset disabled={saving || blocked}>
      <legend>My details</legend>
      <label>Name<input ref={nameInput} autoComplete="name" required maxLength={120} value={draft.name}
        onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
      <label>Email<input type="email" autoComplete="email" required={Boolean(resident.email)} maxLength={254} value={draft.email}
        onChange={(event) => setDraft({ ...draft, email: event.target.value })} /></label>
      <label>Phone<input type="tel" autoComplete="tel" required={Boolean(resident.phone)} maxLength={40} value={draft.phone}
        onChange={(event) => setDraft({ ...draft, phone: event.target.value })} /></label>
      <FieldDropdown label="Preferred contact channel" value={draft.preferred_contact} disabled={saving || blocked}
        options={[{ value: 'portal', label: 'Portal' }, { value: 'email', label: 'Email' },
          { value: 'phone', label: 'Phone (text message)' }]}
        onChange={(preferred_contact) => setDraft({ ...draft, preferred_contact })} />
      <label>Address<input autoComplete="street-address" required maxLength={200} value={draft.address}
        onChange={(event) => setDraft({ ...draft, address: event.target.value })} /></label>
      <label>Unit<input autoComplete="address-line2" required maxLength={80} value={draft.unit}
        onChange={(event) => setDraft({ ...draft, unit: event.target.value })} /></label>
      <label>Heating type<input required={Boolean(homeDetails.heating)} maxLength={120} value={draft.heating}
        onChange={(event) => setDraft({ ...draft, heating: event.target.value })} /></label>
    </fieldset>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="actions">
      <button type="submit" disabled={saving || blocked || !changes || !Object.keys(changes).length}>{saving ? 'Saving…' : 'Save'}</button>
      <button type="button" className="secondary" disabled={saving} onClick={close}>Cancel</button>
    </div>
  </form>
}
