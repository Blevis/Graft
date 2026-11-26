import { Link } from 'react-router-dom'
import {
  ArrowUpRight, CheckCircle2, FileSearch, History, KeyRound, Layers, ShieldCheck, Split, UsersRound,
} from 'lucide-react'
import SiteFrame from './SiteHeader'

const FLOW = [
  ['Evidence arrives', 'Emails, updates, tracker rows and uploaded documents. Immutable and versioned.'],
  ['Claims are extracted', 'A private model proposes claims. Each quote is verified against the source text.'],
  ['Rules flag the gaps', 'Stale trackers, access that is requested but not usable, reports that contradict.'],
  ['A follow-up is assigned', 'The coordinator names an owner and a due date. The SLA clock starts.'],
  ['The technical owner decides', 'Keep open, validate a scope, or sign off. Reviews are append-only.'],
]

export default function Landing() {
  return (
    <SiteFrame>
      <section className="ow-hero">
        <div>
          <div className="ow-overline">
            <span />
            Onboarding and knowledge-transfer readiness
          </div>
          <h1>
            Know who is <em>ready</em>, on what evidence, and who acts next.
          </h1>
          <p>
            Graft puts every onboarding report next to the evidence behind it. AI extracts cited claims, rules flag
            the conflicts, and the technical owner signs off. A tracker status is one report among others, never the
            answer.
          </p>
          <div className="ow-hero-actions">
            <Link to="/login" className="ow-button">
              Open the demo
              <ArrowUpRight size={16} />
            </Link>
            <Link to="/orchid/command-center" className="ow-secondary">
              Explore the product tour
            </Link>
          </div>
          <div className="ow-hero-proof">
            <span><CheckCircle2 size={15} /> Fictional demo data</span>
            <span><CheckCircle2 size={15} /> Private model, no hosted inference</span>
            <span><CheckCircle2 size={15} /> Every change audited</span>
          </div>
        </div>
        <figure className="ow-hero-figure">
          <div className="ow-orbit" aria-hidden="true" />
          <img src="/orchid/pipeline.svg" alt="Illustration of the onboarding pipeline: cases grouped by readiness stage" />
          <figcaption>Illustration from the product tour: the onboarding pipeline in the PMO workspace.</figcaption>
        </figure>
      </section>

      <header className="ow-section-title">
        <div className="ow-overline">
          <span />
          How it works
        </div>
        <h2>From a status someone typed to a decision someone signed.</h2>
        <p>
          The same five steps for every case. Re-running the analysis never changes, duplicates or deletes a task or a
          review.
        </p>
      </header>
      <ol className="ow-flow">
        {FLOW.map(([title, detail]) => (
          <li key={title}>
            <b>{title}</b>
            <small>{detail}</small>
          </li>
        ))}
      </ol>

      <header className="ow-section-title">
        <div className="ow-overline">
          <span />
          Built as a system of record
        </div>
        <h2>The rules a PMO actually works by.</h2>
      </header>
      <div className="ow-cards">
        <article className="ow-panel">
          <span className="ow-tile-icon"><Split size={19} /></span>
          <h3>Three statuses, never one</h3>
          <p>Tracker report, evidence and technical review sit side by side on every case, each with its age and its source.</p>
        </article>
        <article className="ow-panel">
          <span className="ow-tile-icon"><KeyRound size={19} /></span>
          <h3>Access is not a checkbox</h3>
          <p>Requested, approved, active and confirmed usable are four different states. Only the employee's successful test counts.</p>
        </article>
        <article className="ow-panel">
          <span className="ow-tile-icon"><FileSearch size={19} /></span>
          <h3>Every claim cites its source</h3>
          <p>A quote must occur exactly once in the original text. Anything else is rejected and never reaches a rule or a screen.</p>
        </article>
        <article className="ow-panel">
          <span className="ow-tile-icon"><UsersRound size={19} /></span>
          <h3>Roles, scope and responsibility</h3>
          <p>Twelve roles at organization, project or case scope. Each person sees their cases, at the level their role allows.</p>
        </article>
        <article className="ow-panel">
          <span className="ow-tile-icon"><History size={19} /></span>
          <h3>Audited and tenant-safe</h3>
          <p>Every write records who, what, before and after. Another organization's records answer exactly like records that do not exist.</p>
        </article>
        <article className="ow-panel night">
          <span className="ow-tile-icon"><ShieldCheck size={19} /></span>
          <h3>AI proposes, people decide</h3>
          <p>The model has no path to tasks or reviews. Readiness is observed execution plus the technical owner's validation.</p>
        </article>
      </div>

      <section className="ow-spot mt-[clamp(48px,6vw,96px)]">
        <div className="ow-orbit" aria-hidden="true" />
        <div className="ow-spot-inner">
          <span className="ow-kicker"><Layers size={13} className="mr-1.5 inline align-[-2px]" />Seven role workspaces</span>
          <h2>One case, seen the way each person works on it.</h2>
          <p>
            PMO, employee, technical lead, HR, line manager, IT access and management each get their own workspace over
            the same evidence. Walk through all of them without signing in.
          </p>
          <Link to="/orchid/command-center" className="ow-link">
            Start the product tour
            <ArrowUpRight size={15} />
          </Link>
        </div>
      </section>
    </SiteFrame>
  )
}
