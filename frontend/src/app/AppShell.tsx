import { useState, type FormEvent } from 'react'
import { Link, Navigate, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Bell, LogOut, RotateCcw, Search, Sprout } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Loading, Pill } from '@/components/common'
import { ApiError, useLogout, useMe, useNotifications, useReadAllNotifications, useResetDemo } from '@/lib/api'
import { fmtDate, fmtDateTime, ROLE_LABEL } from '@/lib/format'
import { cn } from '@/lib/utils'
import { NAV_ITEMS } from './nav'

export default function AppShell() {
  const me = useMe()
  if (me.isLoading) return <Loading />
  if (me.error instanceof ApiError && me.error.status === 401) return <Navigate to="/login" replace />
  if (!me.data) return <Navigate to="/login" replace />

  return (
    <div className="flex min-h-svh bg-muted/30 text-foreground">
      <aside className="sticky top-0 flex h-svh w-56 shrink-0 flex-col border-r bg-background">
        <Link to="/app/home" className="flex h-14 items-center gap-2 border-b px-4 font-semibold tracking-tight">
          <Sprout className="size-5 text-primary" /> Graft
        </Link>
        <nav className="flex flex-1 flex-col gap-0.5 p-2" aria-label="Main">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground',
                  isActive && 'bg-primary/10 font-medium text-primary',
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t p-3 text-xs text-muted-foreground">
          As of <span className="font-medium text-foreground">{fmtDate(me.data.org.as_of_date)}</span>
          {me.data.org.is_demo && <div>Demo data · fictional people</div>}
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar orgName={me.data.org.name} name={me.data.user.name} role={me.data.role} demo={me.data.demo_mode} />
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function TopBar({ orgName, name, role, demo }: { orgName: string; name: string; role: keyof typeof ROLE_LABEL; demo: boolean }) {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const logout = useLogout()
  const reset = useResetDemo()
  const onSearch = (e: FormEvent) => {
    e.preventDefault()
    navigate(`/app/cases?view=all&q=${encodeURIComponent(q.trim())}`)
  }
  return (
    <header className="sticky top-0 z-10 flex h-14 items-center gap-4 border-b bg-background px-6">
      <div className="shrink-0 truncate text-sm font-medium whitespace-nowrap">{orgName}</div>
      <form onSubmit={onSearch} className="relative ml-4 w-full max-w-sm">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search employee or case ref…" className="pl-8" />
      </form>
      <div className="ml-auto flex items-center gap-2">
        <NotificationsBell />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-9 gap-2">
              <span className="text-sm">{name}</span>
              <Pill className="bg-primary/10 text-primary ring-primary/20">{ROLE_LABEL[role]}</Pill>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>
              {name}
              <div className="text-xs font-normal text-muted-foreground">{ROLE_LABEL[role]} · {orgName}</div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => logout.mutate(undefined, { onSuccess: () => navigate('/login') })}>
              <LogOut /> Switch account
            </DropdownMenuItem>
            {demo && role === 'admin' && (
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
  const unread = (n.data ?? []).filter((x) => !x.read).length
  return (
    <DropdownMenu onOpenChange={(open) => !open && unread > 0 && readAll.mutate()}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label="Notifications">
          <Bell />
          {unread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex size-4 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground">
              {unread}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel>Notifications</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {(n.data ?? []).length === 0 && <div className="px-2 py-3 text-sm text-muted-foreground">Nothing yet.</div>}
        {(n.data ?? []).slice(0, 8).map((x) => (
          <DropdownMenuItem key={x.id} onClick={() => x.link && navigate(x.link)} className="flex-col items-start gap-0.5">
            <span className={cn('text-sm', !x.read && 'font-medium')}>{x.text}</span>
            <span className="text-xs text-muted-foreground">{fmtDateTime(x.created_at)}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
