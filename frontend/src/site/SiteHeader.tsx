import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export default function SiteHeader() {
  return (
    <header className="flex h-14 items-center justify-between border-b px-6">
      <Link to="/" className="font-semibold tracking-tight">DAIS-Y</Link>
      <nav className="flex items-center gap-4 text-sm">
        <Link to="/pricing" className="text-muted-foreground hover:text-foreground">Pricing</Link>
        <Button asChild size="sm"><Link to="/login">Log in</Link></Button>
      </nav>
    </header>
  )
}
