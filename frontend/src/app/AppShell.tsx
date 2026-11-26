import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Bell, CalendarDays, Check, ChevronDown, ChevronRight, Layers, LogOut, Menu, RotateCcw, Search, ShieldCheck, Sparkles, X,
} from 'lucide-react'
import { toast } from 'sonner'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Loading } from '@/components/common'
import { ApiError, useLogout, useMe, useNotifications, usePatchPreferences, useReadAllNotifications, useResetDemo } from '@/lib/api'
import { fmtDate, fmtDateTime, roleLabel } from '@/lib/format'
import type { Me, Role } from '@/lib/types'
import { cn } from '@/lib/utils'
import { NAV_GROUPS, NAV_ITEMS } from './nav'
import { availableRoles } from './workspace/catalog'

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('')

export default function AppShell() {
  const me = useMe()
  const location = useLocation()
  const [menu, setMenu] = useState(false)
  const patchPrefs = usePatchPreferences()

  // The page title follows the section; the mobile drawer closes when a destination is picked.
  const current = NAV_ITEMS.find((n) => location.pathname === n.to || location.pathname.startsWith(n.to + '/'))
  useEffect(() => {
    document.title = (current ? current.label + ' · ' : '') + 'Graft'
  }, [current])

  if (me.isLoading) return <div className="ow-splash"><Loading /></div>
  if (me.error instanceof ApiError && me.error.status === 401) return <Navigate to="/login" replace />
  if (!me.data) return <Navigate to="/login" replace />

  const m = me.data
  const hasWorkspace = availableRoles(m.roles).length > 0

  return (
    <div className="orchid">
      <a className="ow-skip" href="#app-main">Skip to content</a>
      {menu && <button className="ow-scrim" aria-label="Close navigation" onClick={() => setMenu(false)} />}
      <aside className={cn('ow-sidebar', menu && 'is-open')}>
        <Link to="/app/home" className="ow-brand" onClick={() => setMenu(false)}>
          <img src="/orchid/graft.svg" alt="" />
          Graft
        </Link>
        {m.roles.length > 1 ? (
          <label className="ow-role-select">
            <small>Working as</small>
            <span>
              <Layers size={17} />
              <select
                aria-label="Working context"
                title="Changes what Home and Ask Graft emphasise, never what you can do"
                value={m.working_role ?? ''}
                onChange={(e) =>
                  patchPrefs.mutate({ working_role: (e.target.value || null) as Role | null }, { onError: (err) => toast.error(err.message) })
                }
              >
                <option value="">All my roles</option>
                {m.roles.map((r) => <option key={r} value={r}>{roleLabel(m, r)}</option>)}
              </select>
              <ChevronDown size={14} />
            </span>
          </label>
        ) : (
          <div className="ow-role-select is-static">
            <small>Working as</small>
            <span>
              <Layers size={17} />
              {roleLabel(m, m.role)}
            </span>
          </div>
        )}
        <nav aria-label="Main">
          {NAV_GROUPS.map((g) => (
            <div key={g.label} className="contents">
              <div className="ow-nav-label">{g.label}</div>
              {g.items.map(({ to, label, icon: Icon }) => (
                <NavLink key={to} to={to} onClick={() => setMenu(false)}>
                  <Icon size={19} />
                  {label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="ow-sidebar-bottom">
          {hasWorkspace && (
            <Link to="/app/workspace">
              <Sparkles size={16} />
              Open role workspace
            </Link>
          )}
          <div className="ow-org">
            <span><Layers size={18} /></span>
            <div>
              <b>{m.org.name}</b>
              <small>{m.org.is_demo ? 'Demo data · fictional people' : 'Organization workspace'}</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="ow-main">
        <TopBar me={m} section={current?.label} menu={menu} onMenu={() => setMenu(!menu)} />
        <main id="app-main" className="ow-content">
          <Outlet />
          <footer className="ow-footer">
            <span><ShieldCheck size={13} /> AI proposes, people decide. Every change is audited.</span>
            <span>As of {fmtDate(m.org.as_of_date)}{m.org.is_demo ? ' · fictional demo data' : ''}</span>
          </footer>
        </main>
      </div>
    </div>
  )
}

function TopBar({ me, section, menu, onMenu }: { me: Me; section?: string; menu: boolean; onMenu: () => void }) {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const search = useRef<HTMLInputElement>(null)
  const logout = useLogout()
  const reset = useResetDemo()
  const patchPrefs = usePatchPreferences()
  const { name } = me.user
  const shown = me.working_role ?? me.role
  const isAdmin = me.roles.includes('org_admin')
  const mac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        search.current?.focus()
        search.current?.select()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const onSearch = (e: FormEvent) => {
    e.preventDefault()
    navigate(`/app/cases?view=all&q=${encodeURIComponent(q.trim())}`)
  }

  return (
    <header className="ow-top is-sticky">
      <button className="ow-mobile-menu" aria-label={menu ? 'Close navigation' : 'Open navigation'} onClick={onMenu}>
        {menu ? <X /> : <Menu />}
      </button>
      <span className="ow-crumb">
        <span className="max-w-[22ch] truncate">{me.org.name}</span>
        {section && (
          <>
            <ChevronRight size={13} /> <b>{section}</b>
          </>
        )}
      </span>
      <form className="ow-global-search" role="search" onSubmit={onSearch}>
        <Search size={15} />
        <input
          ref={search}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search employee or case ref"
          aria-label="Search employee or case reference"
        />
        <kbd>{mac ? '⌘K' : 'Ctrl K'}</kbd>
      </form>
      <div className="ow-top-right">
        <span className="ow-date" title="Ages, staleness and SLAs are computed against this date">
          <CalendarDays size={16} />
          {fmtDate(me.org.as_of_date)}
        </span>
        <i />
        <NotificationsBell />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="ow-user" aria-label={`Account menu for ${name}`}>
              <span className="ow-profile">{initials(name)}</span>
              <span>
                <b>{name}</b>
                <small>
                  {roleLabel(me, shown)}
                  {me.roles.length > 1 && ` +${me.roles.length - 1}`}
                </small>
              </span>
              <ChevronDown size={14} />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80">
            <div className="flex items-center gap-3 px-2 py-2">
              <span className="ow-profile size-9 text-xs">{initials(name)}</span>
              <div className="min-w-0">
                <div className="truncate text-sm font-bold text-foreground">{name}</div>
                <div className="truncate text-xs text-muted-foreground">{me.user.title ?? me.org.name}</div>
              </div>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-[10px] font-extrabold tracking-[1.2px] uppercase">Your roles and scope</DropdownMenuLabel>
            <ul className="space-y-1 px-2 pb-2 text-xs">
              {me.grants.map((g, i) => (
                <li key={i} className="flex justify-between gap-3">
                  <span className="font-semibold">{roleLabel(me, g.role)}</span>
                  <span className="text-right text-muted-foreground">
                    {g.scope_type === 'organization' ? 'Organization' : `${g.scope_type === 'project' ? 'Project' : 'Case'} ${g.scope_name ?? ''}`}
                    {g.default_for_cases ? ' · default' : ''}
                  </span>
                </li>
              ))}
            </ul>
            {me.roles.length > 1 && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuLabel className="text-[10px] font-extrabold tracking-[1.2px] uppercase">Working context</DropdownMenuLabel>
                <p className="px-2 pb-1 text-[11px] leading-snug text-muted-foreground">
                  Changes what Home and Ask Graft emphasise, never what you can do.
                </p>
                {[null, ...me.roles].map((r) => (
                  <DropdownMenuItem
                    key={r ?? 'all'}
                    onClick={() => patchPrefs.mutate({ working_role: r }, { onError: (e) => toast.error(e.message) })}
                  >
                    <Check className={cn('size-4 text-primary', (me.working_role ?? null) === r ? 'opacity-100' : 'opacity-0')} />
                    {r ? roleLabel(me, r) : 'All my roles'}
                  </DropdownMenuItem>
                ))}
              </>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => logout.mutate(undefined, { onSuccess: () => navigate('/login') })}>
              <LogOut /> Switch account
            </DropdownMenuItem>
            {me.demo_mode && isAdmin && (
              <DropdownMenuItem
                onClick={() => {
                  if (!window.confirm('Reset the demo? This deletes all tasks and reviews in both demo orgs and reloads the starter data.')) return
                  reset.mutate(undefined, {
                    onSuccess: () => {
                      toast.success('Demo data reset')
                      navigate('/login')
                    },
                    onError: (e) => toast.error(e.message),
                  })
                }}
              >
                <RotateCcw /> Reset demo data
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}

function NotificationsBell() {
  const n = useNotifications()
  const readAll = useReadAllNotifications()
  const navigate = useNavigate()
  const items = n.data ?? []
  const unread = items.filter((x) => !x.read).length
  return (
    <DropdownMenu onOpenChange={(open) => !open && unread > 0 && readAll.mutate()}>
      <DropdownMenuTrigger asChild>
        <button className="ow-icon-button" aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}>
          <Bell size={17} />
          {unread > 0 && <em>{unread}</em>}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-88">
        <div className="flex items-center justify-between px-2 py-1.5">
          <span className="text-sm font-extrabold tracking-tight text-foreground">Notifications</span>
          {unread > 0 && <span className="ow-count">{unread} new</span>}
        </div>
        <DropdownMenuSeparator />
        {items.length === 0 && <div className="px-2 py-6 text-center text-[13px] text-muted-foreground">You are all caught up.</div>}
        {items.slice(0, 8).map((x) => (
          <DropdownMenuItem key={x.id} onClick={() => x.link && navigate(x.link)} className="items-start gap-2.5 py-2">
            <span className={cn('mt-1.5 size-1.5 shrink-0 rounded-full', x.read ? 'bg-transparent' : 'bg-primary')} />
            <span className="grid gap-0.5">
              <span className={cn('text-[13px] leading-snug', !x.read && 'font-bold')}>{x.text}</span>
              <span className="text-[11px] text-muted-foreground">{fmtDateTime(x.created_at)}</span>
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
