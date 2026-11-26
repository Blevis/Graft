import { useNavigate } from 'react-router-dom'
import { LogIn } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { ErrorState, Loading } from '@/components/common'
import { useDemoAccounts, useDemoLogin } from '@/lib/api'
import { ROLE_LABEL } from '@/lib/format'
import type { DemoAccount } from '@/lib/types'
import SiteHeader from './SiteHeader'

export default function Login() {
  const accounts = useDemoAccounts()
  const login = useDemoLogin()
  const navigate = useNavigate()

  const byOrg = new Map<string, DemoAccount[]>()
  for (const a of accounts.data ?? []) byOrg.set(a.org_name, [...(byOrg.get(a.org_name) ?? []), a])

  const signIn = (a: DemoAccount) =>
    login.mutate(a.user_id, {
      onSuccess: () => navigate('/app/home'),
      onError: (e) => toast.error(e.message),
    })

  return (
    <div className="min-h-svh bg-muted/30">
      <SiteHeader />
      <main className="mx-auto max-w-2xl px-6 py-12">
        <h1 className="text-2xl font-semibold tracking-tight">Sign in to the demo</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Pick a fictional person to act as. Your role comes from that person's membership on the server, so each
          account sees and can do different things. Production uses OIDC single sign-on; Graft stores no passwords.
        </p>
        <div className="mt-8 space-y-8">
          {accounts.isLoading && <Loading />}
          {accounts.error && <ErrorState error={accounts.error} />}
          {[...byOrg.entries()].map(([org, list]) => (
            <section key={org}>
              <h2 className="mb-2 text-sm font-semibold text-muted-foreground">{org}</h2>
              <div className="divide-y rounded-lg border bg-background">
                {list.map((a) => (
                  <div key={a.user_id} className="flex items-center justify-between gap-4 px-4 py-3">
                    <div>
                      <div className="font-medium">{a.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {ROLE_LABEL[a.role]}
                        {a.title ? ` · ${a.title}` : ''}
                      </div>
                    </div>
                    <Button size="sm" variant="outline" disabled={login.isPending} onClick={() => signIn(a)}>
                      <LogIn /> Sign in
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
