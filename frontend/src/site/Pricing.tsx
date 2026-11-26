import { Link } from 'react-router-dom'
import { ArrowUpRight, Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import SiteFrame from './SiteHeader'

const PLANS = [
  {
    name: 'Pilot', price: 'Free', unit: 'while you evaluate', note: 'One project team on demo data.',
    points: ['Up to 25 onboarding cases', 'Evidence, findings, tasks and reviews', 'Recorded AI examples'],
  },
  {
    name: 'Team', price: '€6', unit: 'per employee case / month', note: 'For a PMO running onboarding across projects.', featured: true,
    points: ['Unlimited projects', 'AI evidence extraction with cited claims', 'Queues, SLAs and the audit trail'],
  },
  {
    name: 'Enterprise', price: 'Contact us', unit: 'private deployment', note: 'For organisations with their own identity and retention rules.',
    points: ['Single sign-on (OIDC)', 'Data residency and a private model', 'Custom retention and integrations'],
  },
]

export default function Pricing() {
  return (
    <SiteFrame>
      <header className="ow-heading">
        <div>
          <div className="ow-overline">
            <span />
            Pricing
          </div>
          <h1>Priced by the case, not the seat.</h1>
          <p>Indicative plans for the hackathon prototype. Nothing is billed.</p>
        </div>
      </header>
      <div className="ow-cards three">
        {PLANS.map((p) => (
          <article key={p.name} className={cn('ow-panel ow-price', p.featured && 'night')}>
            <span className={cn('ow-tag', p.featured ? 'night' : 'violet')}>
              <i />
              {p.name}
            </span>
            <span className="ow-large-value">
              {p.price} <small>{p.unit}</small>
            </span>
            <p className="text-[13.5px]">{p.note}</p>
            <ul>
              {p.points.map((x) => (
                <li key={x}>
                  <Check size={15} />
                  {x}
                </li>
              ))}
            </ul>
            <Link to="/login" className={cn(p.featured ? 'ow-button light' : 'ow-secondary')}>
              Try the demo
              <ArrowUpRight size={15} />
            </Link>
          </article>
        ))}
      </div>
    </SiteFrame>
  )
}
