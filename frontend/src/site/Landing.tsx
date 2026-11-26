import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import SiteHeader from './SiteHeader'

export default function Landing() {
  return (
    <div className="min-h-svh">
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-6 py-20">
        <h1 className="text-4xl font-semibold tracking-tight">
          What evidence shows an employee can work independently, and who acts next?
        </h1>
        <p className="mt-4 text-lg text-muted-foreground">
          DAIS-Y tracks onboarding and knowledge transfer across projects. AI extracts cited claims, rules flag
          conflicts, and people decide.
        </p>
        <div className="mt-8 flex gap-3">
          <Button asChild><Link to="/login">Open the demo</Link></Button>
          <Button asChild variant="outline"><Link to="/pricing">Pricing</Link></Button>
        </div>
      </main>
    </div>
  )
}
