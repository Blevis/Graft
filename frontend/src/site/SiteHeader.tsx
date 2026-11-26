import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import { Sprout } from '@/components/Sprout'

/** Public pages share one frame: sticky header, fluid content column, quiet footer. */
export default function SiteFrame({ children }: { children: ReactNode }) {
  return (
    <div className="ow-site">
      <header className="ow-site-top">
        <Link to="/" className="ow-site-brand">
          <Sprout size={32} grow />
          Graft
        </Link>
        <nav aria-label="Site">
          <NavLink to="/orchid/command-center">Product tour</NavLink>
          <NavLink to="/pricing" className="keep">Pricing</NavLink>
        </nav>
        <Link to="/login" className="ow-button">
          Log in
          <ArrowUpRight size={15} />
        </Link>
      </header>
      <main className="ow-site-main">{children}</main>
      <footer className="ow-site-footer">
        <span>Graft · onboarding and knowledge-transfer readiness. The demo uses fictional people and data.</span>
        <nav aria-label="Footer">
          <Link to="/orchid/command-center">Product tour</Link>
          <Link to="/pricing">Pricing</Link>
          <Link to="/login">Log in</Link>
        </nav>
      </footer>
    </div>
  )
}
