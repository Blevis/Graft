import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import SiteHeader from './SiteHeader'

export default function Login() {
  return (
    <div className="min-h-svh">
      <SiteHeader />
      <main className="mx-auto max-w-md px-6 py-20">
        <h1 className="text-3xl font-semibold tracking-tight">Log in</h1>
        <Button asChild className="mt-6"><Link to="/app/home">Enter demo workspace</Link></Button>
      </main>
    </div>
  )
}
