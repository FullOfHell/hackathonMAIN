import { PortalDropdown } from './PortalDropdown'
import { contractorInboxHref } from './repairNotifications'
import type { Contractor } from './types/domain'

interface Props {
  inboxes: Pick<Contractor, 'slug' | 'name'>[]
  selectedSlug?: string
}

export function ContractorPicker({ inboxes, selectedSlug }: Props) {
  const selected = inboxes.find(({ slug }) => slug === selectedSlug)
  return (
    <PortalDropdown navigation value={selected?.name ?? 'Contractors'}
      label={selected ? selected.name + ', contractor inbox' : 'Contractors, choose an inbox'}>
      {(choose) => inboxes.length ? (
        <ul>
          {inboxes.map(({ slug, name }) => (
            <li key={slug}>
              <a href={contractorInboxHref(slug)} aria-current={slug === selectedSlug ? 'page' : undefined}
                onClick={choose}>{name}</a>
            </li>
          ))}
        </ul>
      ) : <p>No contractor inboxes available.</p>}
    </PortalDropdown>
  )
}
