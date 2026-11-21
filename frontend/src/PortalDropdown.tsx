import { useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'

interface DropdownProps {
  label: string
  value: string
  navigation?: boolean
  disabled?: boolean
  children: (choose: () => void) => ReactNode
}

export function PortalDropdown({ label, value, navigation = false, disabled = false, children }: DropdownProps) {
  const [open, setOpen] = useState(false)
  const container = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const menuId = useId()
  const expanded = open && !disabled

  function choose() {
    setOpen(false)
    trigger.current?.focus()
  }

  useEffect(() => {
    if (!expanded) return
    function dismiss(event: PointerEvent) {
      if (event.target instanceof Node && !container.current?.contains(event.target)) setOpen(false)
    }
    function escape(event: KeyboardEvent) {
      if (event.key === 'Escape' && !event.defaultPrevented && container.current?.contains(document.activeElement)) {
        event.preventDefault()
        choose()
      }
    }
    document.addEventListener('pointerdown', dismiss)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', dismiss)
      document.removeEventListener('keydown', escape)
    }
  }, [expanded])

  return (
    <div className={navigation ? 'portal-dropdown nav-dropdown' : 'portal-dropdown'} ref={container}
      onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false) }}>
      <button type="button" ref={trigger} className="portal-dropdown-trigger" disabled={disabled}
        aria-label={label} aria-expanded={expanded} aria-controls={menuId} onClick={() => setOpen(!expanded)}>
        <span>{value}</span>
      </button>
      <div className="portal-dropdown-menu" id={menuId} hidden={!expanded}>
        {children(choose)}
      </div>
    </div>
  )
}

interface FieldOption<Value extends string> {
  value: Value
  label: string
}

export function FieldDropdown<Value extends string>({ label, value, options, disabled, onChange }: {
  label: string
  value: Value
  options: readonly FieldOption<Value>[]
  disabled?: boolean
  onChange: (value: Value) => void
}) {
  const selected = options.find((option) => option.value === value)?.label ?? (value || 'Choose an option')
  return (
    <div className="dropdown-field">
      <span className="dropdown-field-label">{label}</span>
      <PortalDropdown label={label + ', ' + selected} value={selected} disabled={disabled}>
        {(choose) => (
          <ul>
            {options.map((option) => (
              <li key={option.value}>
                <button type="button" aria-pressed={value === option.value}
                  onClick={() => { onChange(option.value); choose() }}>
                  {option.label}
                </button>
              </li>
            ))}
          </ul>
        )}
      </PortalDropdown>
    </div>
  )
}
