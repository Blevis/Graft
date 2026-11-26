import { useEffect, useState, type CSSProperties } from 'react'
import { cn } from '@/lib/utils'

/**
 * The Graft twig as inline SVG, built from the same four parts as public/orchid/graft-animated.svg (docs/brand.md):
 * the stem draws from root to tip, then each leaf grows from its joint, lowest first. One flat colour, no effects.
 * `grow` plays the sequence once; without it the finished mark is shown.
 */
export function Sprout({ size = 40, grow = false, delay = 0, className, title }: {
  size?: number | string; grow?: boolean; delay?: number; className?: string; title?: string
}) {
  return (
    <svg
      viewBox="20 8 208 232"
      width={size}
      height={size}
      className={cn('ow-sprout', grow && 'is-growing', className)}
      style={{ '--sprout-delay': `${delay}ms` } as CSSProperties}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <path className="stem" pathLength={1} fill="none" stroke="currentColor" strokeWidth="15.85" strokeLinecap="round"
        d="M85.86 223.52Q94.92 132.95 171.9 71.82" />
      <g fill="currentColor">
        <path className="leaf l1" style={{ transformOrigin: '102.55px 158.94px' }}
          d="M102.55 158.94C96.65 132.93 57.14 130.12 40.85 136.48C49.24 151.82 81.31 175.06 102.55 158.94Z" />
        <path className="leaf l2" style={{ transformOrigin: '121.18px 125.43px' }}
          d="M121.18 125.43C144.54 109.17 131.53 68.89 118.73 55.29C106.91 69.75 96.75 110.83 121.18 125.43Z" />
        <path className="leaf l3" style={{ transformOrigin: '157.48px 89.28px' }}
          d="M157.48 89.28C193.22 92.94 215.49 43.21 215.15 19.44C191.74 23.6 147.12 54.88 157.48 89.28Z" />
      </g>
    </svg>
  )
}

const INTRO_KEY = 'graft:intro'

/** Sign-in pages call this just before entering the app, so the intro plays once per sign-in and never on reload. */
export function armIntro() {
  try {
    sessionStorage.setItem(INTRO_KEY, '1')
  } catch {
    /* private mode: the app simply opens without the intro */
  }
}

function takeIntro(): boolean {
  try {
    const armed = sessionStorage.getItem(INTRO_KEY) === '1'
    sessionStorage.removeItem(INTRO_KEY)
    return armed
  } catch {
    return false
  }
}

/**
 * Full-screen intro after sign-in: the twig grows, the wordmark and a greeting follow, then the curtain lifts.
 * About 2.6 s in all (the mark itself takes under 1.5 s); any key or click skips it. With reduced motion the
 * finished mark is shown briefly instead.
 */
export function SproutIntro({ name, org }: { name?: string; org?: string }) {
  const [show, setShow] = useState(takeIntro)
  const [leaving, setLeaving] = useState(false)

  useEffect(() => {
    if (!show) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const leave = window.setTimeout(() => setLeaving(true), reduced ? 700 : 2150)
    const done = window.setTimeout(() => setShow(false), reduced ? 900 : 2700)
    const skip = () => setShow(false)
    window.addEventListener('keydown', skip)
    return () => {
      window.clearTimeout(leave)
      window.clearTimeout(done)
      window.removeEventListener('keydown', skip)
    }
  }, [show])

  if (!show) return null
  return (
    <div className={cn('ow-intro', leaving && 'is-leaving')} role="status" aria-label="Signing you in" onClick={() => setShow(false)}>
      <div className="ow-orbit" aria-hidden="true" />
      <div className="ow-intro-mark">
        <Sprout size={132} grow delay={150} />
        <div className="ow-intro-word">Graft</div>
      </div>
      <p className="ow-intro-hello">
        {name ? <>Welcome, <b>{name.split(' ')[0]}</b></> : 'Welcome'}
        {org && <span>{org}</span>}
      </p>
    </div>
  )
}
