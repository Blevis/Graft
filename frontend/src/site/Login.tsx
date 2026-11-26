import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, FileSearch, KeyRound, LogIn, ShieldCheck, UsersRound } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Avatar, ErrorState, Field, Loading } from '@/components/common'
import { useAuthConfig, useDemoAccounts, useDemoPassword, usePasswordLogin } from '@/lib/api'
import { ROLE_LABEL } from '@/lib/format'
import type { DemoAccount, Role } from '@/lib/types'

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
  const submit = useRef<HTMLButtonElement>(null)

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
    submit.current?.focus()
  }

  return (
    <div className="ow-auth">
      <aside className="ow-auth-aside">
        <div className="ow-orbit" aria-hidden="true" />
        <Link to="/" className="ow-brand !px-0">
          <img src="/orchid/graft.svg" alt="" />
          Graft
        </Link>
        <div>
          <span className="ow-kicker">{oidc ? 'Organization workspace' : 'Demo workspace'}</span>
          <h1>See the evidence behind every status.</h1>
          <p>
            Onboarding and knowledge-transfer readiness across projects: what the tracker says, what the evidence
            shows, what the technical owner decided, and who acts next.
          </p>
        </div>
        <ul className="ow-auth-points">
          <li>
            <span><FileSearch size={16} /></span>
            <div><b>Cited claims</b>Every AI statement links to the exact words in its source.</div>
          </li>
          <li>
            <span><UsersRound size={16} /></span>
            <div><b>Scoped by role</b>Each account sees its own cases, at the level its role allows.</div>
          </li>
          <li>
            <span><ShieldCheck size={16} /></span>
            <div><b>People decide</b>Only the technical owner records readiness. Everything is audited.</div>
          </li>
        </ul>
      </aside>

      <main className="ow-auth-main">
        <Link to="/" className="ow-back"><ArrowLeft size={14} /> Back to graft</Link>
        <div className="ow-overline">
          <span />
          {oidc ? 'Single sign-on' : 'Fictional accounts'}
        </div>
        <h1 className="text-[clamp(28px,2.4vw,40px)] leading-tight font-extrabold tracking-[-0.05em]">
          {oidc ? 'Sign in' : 'Sign in to the demo'}
        </h1>
        {config.isLoading && <Loading />}
        {oidc && (
          <div className="mt-6">
            <Button asChild size="lg"><a href={config.data!.oidc_login_url!}><LogIn /> Sign in with your organisation</a></Button>
            <p className="mt-3 text-xs text-muted-foreground">Single sign-on. Graft never sees or stores your password.</p>
          </div>
        )}
        {passwords && (
          <>
            <p className="mt-2 text-[13.5px] text-muted-foreground">
              Every account below is a fictional person. Roles come from that person's server-side role grants, so each
              account sees and can do different things. In production, people sign in with their organisation's single
              sign-on.
            </p>
            <form onSubmit={signIn} className="ow-panel mt-6 grid gap-3.5">
              <Field label="Email">
                <Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </Field>
              <Field label="Password">
                <Input type="password" autoComplete="current-password" value={password}
                  onChange={(e) => setPassword(e.target.value)} required />
              </Field>
              <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                <Button ref={submit} type="submit" size="lg" disabled={login.isPending || !email || !password}><LogIn /> Sign in</Button>
                {demoPassword.data && (
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <KeyRound className="size-3.5" /> Demo password for every account:{' '}
                    <code className="rounded-md bg-accent px-1.5 py-0.5 font-mono font-semibold text-accent-foreground">{demoPassword.data.password}</code>
                  </span>
                )}
              </div>
            </form>
          </>
        )}
        <div className="mt-7 space-y-6">
          {passwords && accounts.isLoading && <Loading />}
          {passwords && accounts.error && <ErrorState error={accounts.error} />}
          {passwords && [...byOrg.entries()].map(([org, list]) => (
            <section key={org}>
              <h2 className="mb-2.5 text-[11px] font-extrabold tracking-[1.6px] text-muted-foreground uppercase">{org}</h2>
              <div className="grid gap-2 sm:grid-cols-2">
                {list.map((a) => (
                  <button
                    key={a.user_id}
                    type="button"
                    className="ow-account"
                    disabled={!a.email}
                    aria-pressed={!!a.email && a.email === email}
                    aria-label={`Use the account of ${a.name}`}
                    title={a.email ?? undefined}
                    onClick={() => pick(a)}
                  >
                    <Avatar name={a.name} />
                    <span>
                      <b>{a.name}</b>
                      <small className="truncate">
                        {(a.roles.length ? a.roles : [a.role]).map((r: Role) => ROLE_LABEL[r]).join(' + ')}
                      </small>
                      {a.title && <small className="truncate">{a.title}</small>}
                    </span>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>
      </main>
    </div>
  )
}
