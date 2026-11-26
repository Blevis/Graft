import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import SiteHeader from './SiteHeader'

const PLANS = [
  { name: 'Pilot', price: 'Free', note: 'One project team, demo data, up to 25 onboarding cases.' },
  { name: 'Team', price: '€6 / employee case / month', note: 'Unlimited projects, AI evidence extraction, audit trail.' },
  { name: 'Enterprise', price: 'Contact us', note: 'SSO (OIDC), data residency, custom retention and integrations.' },
]

export default function Pricing() {
  return (
    <div className="min-h-svh">
      <SiteHeader />
      <main className="mx-auto max-w-4xl px-6 py-16">
        <h1 className="text-3xl font-semibold tracking-tight">Pricing</h1>
        <p className="mt-2 text-muted-foreground">Indicative plans for the hackathon prototype. Nothing is billed.</p>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {PLANS.map((p) => (
            <div key={p.name} className="rounded-lg border p-5">
              <div className="font-semibold">{p.name}</div>
              <div className="mt-1 text-lg">{p.price}</div>
              <p className="mt-2 text-sm text-muted-foreground">{p.note}</p>
            </div>
          ))}
        </div>
        <Button asChild className="mt-8"><Link to="/login">Try the demo</Link></Button>
      </main>
    </div>
  )
}
