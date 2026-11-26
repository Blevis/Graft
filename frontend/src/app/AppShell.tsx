import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { NAV_ITEMS } from './nav'

export default function AppShell() {
  return (
    <div className="flex min-h-svh bg-muted/30 text-foreground">
      <aside className="flex w-56 shrink-0 flex-col border-r bg-background">
        <div className="flex h-14 items-center border-b px-4 font-semibold tracking-tight">DAIS-Y</div>
        <nav className="flex flex-1 flex-col gap-0.5 p-2" aria-label="Main">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground',
                  isActive && 'bg-muted font-medium text-foreground',
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center border-b bg-background px-6 text-sm text-muted-foreground">
          Engineering Albania (demo)
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
