import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search } from 'lucide-react'
import { screens, type Persona } from './catalog'
import { useWorkspace } from './context'

export default function WorkspaceSearch({ allowed }: { allowed: Persona[] }) {
  const w = useWorkspace(),
    input = useRef<HTMLInputElement>(null),
    [query, setQuery] = useState(''),
    [open, setOpen] = useState(false)
  useEffect(() => {
    const shortcut = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        input.current?.focus()
      }
    }
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  }, [])
  const text = query.trim().toLowerCase()
  const match = screens
    .filter((s) => allowed.includes(s.role) && s.title.toLowerCase().includes(text))
    .slice(0, 4)
  const people = w.data.people
    .filter((p) => [p.name, p.ref, p.project].join(' ').toLowerCase().includes(text))
    .slice(0, 4)
  return (
    <div
      className="ow-global-search"
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          setOpen(false)
          input.current?.blur()
        }
      }}
    >
      <Search size={15} />
      <input
        ref={input}
        value={query}
        aria-label="Search screens and cases"
        placeholder="Search screens and cases"
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
      />
      <kbd>Ctrl K</kbd>
      {open && text && (
        <div className="ow-search-results">
          {match.map((s) => (
            <Link
              key={s.id}
              to={w.href(s.id)}
              onClick={() => {
                setQuery('')
                setOpen(false)
              }}
            >
              <s.icon size={15} />
              {s.title}
            </Link>
          ))}
          {people.map((p) => (
            <Link
              key={p.ref}
              to={w.demo ? w.href(3, p.ref) : '/app/cases/' + p.ref}
              onClick={() => {
                setQuery('')
                setOpen(false)
              }}
            >
              {p.name}
              <small>
                {p.ref} · {p.project}
              </small>
            </Link>
          ))}
          {!match.length && !people.length && <small>No matching screens or cases.</small>}
        </div>
      )}
    </div>
  )
}
