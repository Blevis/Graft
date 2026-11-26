import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { KeyRound, LogIn } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ErrorState, Field, Loading } from '@/components/common'
import { useAuthConfig, useDemoAccounts, useDemoPassword, usePasswordLogin } from '@/lib/api'
import { ROLE_LABEL } from '@/lib/format'
import type { DemoAccount, Role } from '@/lib/types'
import SiteHeader from './SiteHeader'

export default function Login() {
  const config = useAuthConfig()
  const oidc = config.data?.auth_mode === 'oidc'
  const passwords = config.data?.password_login === true
  const accounts = useDemoAccounts()
  const demoPassword = useDemoPassword(passwords)
  const login = usePasswordLogin()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const byOrg = new Map<string, DemoAccount[]>()
  for (const a of accounts.data ?? []) byOrg.set(a.org_name, [...(byOrg.get(a.org_name) ?? []), a])

  const signIn = (e: React.FormEvent) => {
    e.preventDefault()
    login.mutate(
      { email, password },
      { onSuccess: () => navigate('/app/home'), onError: (er) => toast.error(er.message) },
    )
  }
  const pick = (a: DemoAccount) => {
    setEmail(a.email ?? '')
    setPassword(demoPassword.data?.password ?? '')
  }

  return (
    <div className="min-h-svh bg-muted/30">
      <SiteHeader />
      <main className="mx-auto max-w-2xl px-4 py-12 sm:px-6">
        <h1 className="text-2xl font-semibold tracking-tight">{oidc ? 'Sign in' : 'Sign in to the demo'}</h1>
        {oidc && (
          <div className="mt-6">
            <Button asChild><a href={config.data!.oidc_login_url!}><LogIn /> Sign in with your organisation</a></Button>
            <p className="mt-2 text-xs text-muted-foreground">Single sign-on. Graft never sees or stores your password.</p>
          </div>
        )}
        {passwords && (
          <>
            <p className="mt-2 text-sm text-muted-foreground">
              Every account below is a fictional person. Roles come from that person's server-side role grants, so each
              account sees and can do different things. In production, people sign in with their organisation's single
              sign-on.
            </p>
            <form onSubmit={signIn} className="mt-6 grid gap-3 rounded-lg border bg-background p-4">
              <Field label="Email">
                <Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </Field>
              <Field label="Password">
                <Input type="password" autoComplete="current-password" value={password}
                  onChange={(e) => setPassword(e.target.value)} required />
              </Field>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Button type="submit" disabled={login.isPending || !email || !password}><LogIn /> Sign in</Button>
                {demoPassword.data && (
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <KeyRound className="size-3.5" /> Demo password for every account:{' '}
                    <code className="rounded bg-muted px-1.5 py-0.5 text-foreground">{demoPassword.data.password}</code>
                  </span>
                )}
              </div>
            </form>
          </>
        )}
        <div className="mt-8 space-y-8">
          {passwords && accounts.isLoading && <Loading />}
          {passwords && accounts.error && <ErrorState error={accounts.error} />}
          {passwords && [...byOrg.entries()].map(([org, list]) => (
            <section key={org}>
              <h2 className="mb-2 text-sm font-semibold text-muted-foreground">{org}</h2>
              <div className="divide-y rounded-lg border bg-background">
                {list.map((a) => (
                  <div key={a.user_id} className="flex items-center justify-between gap-4 px-4 py-3">
                    <div className="min-w-0">
                      <div className="font-medium">{a.name}</div>
                      <div className="truncate text-xs text-muted-foreground">
                        {(a.roles.length ? a.roles : [a.role]).map((r: Role) => ROLE_LABEL[r]).join(' + ')}
                        {a.title ? ` · ${a.title}` : ''}
                      </div>
                      <div className="truncate text-xs text-muted-foreground">{a.email}</div>
                    </div>
                    <Button size="sm" variant="outline" type="button" disabled={!a.email} onClick={() => pick(a)}>
                      Use this account
                    </Button>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </main>
    </div>
  )
}
