import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Send, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Empty, Field, ModeBadge, NativeSelect, PageHeader, Pill, Section } from '@/components/common'
import { useAsk, useCases, usePreferences } from '@/lib/api'
import type { AskDetail, AskFocus, AskFormat } from '@/lib/types'
import { DETAIL_LABEL, FOCUS_LABEL, FORMAT_LABEL } from '../settings/GuidancePage'

const EXAMPLES: Record<string, string> = {
  pmo_coordinator: 'Which onboarding cases have conflicting closure reports?',
  project_manager: 'Summarize onboarding risks on my projects.',
  line_manager: 'What does the evidence say about Eva’s training progress?',
  technical_owner: 'Which scenarios still need validation before independent execution?',
  training_responsible: 'What KT activities are reported without an observation?',
  access_responsible: 'Which systems are approved but not yet confirmed usable?',
  employee: 'What is still open on my onboarding?',
}

/** Ask Graft: extractive answers from the evidence you may see. Focus, detail and format change presentation only. */
export default function AskPage() {
  const prefs = usePreferences()
  const cases = useCases('all')
  const ask = useAsk()
  const [question, setQuestion] = useState('')
  const [caseId, setCaseId] = useState('')
  const [focus, setFocus] = useState<AskFocus | ''>('')
  const [detail, setDetail] = useState<AskDetail | ''>('')
  const [format, setFormat] = useState<AskFormat | ''>('')
  const eff = prefs.data?.effective
  const a = ask.data
  const example = EXAMPLES[eff?.profile ?? ''] ?? 'What is blocking this onboarding?'

  const submit = () =>
    ask.mutate(
      { question: question.trim(), case_id: caseId || null, focus: focus || undefined, detail: detail || undefined, format: format || undefined },
      { onError: (e) => toast.error(e.message) },
    )

  return (
    <div className="space-y-5">
      <PageHeader
        title="Ask Graft"
        description="Answers come only from evidence inside Graft that you are allowed to see, quoted verbatim with a citation. Graft never decides readiness."
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Section title="Question">
            <form
              className="grid gap-3"
              onSubmit={(e) => {
                e.preventDefault()
                if (question.trim()) submit()
              }}
            >
              <Textarea rows={3} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder={example} />
              <div className="grid gap-3 sm:grid-cols-4">
                <Field label="Case">
                  <NativeSelect value={caseId} onChange={(e) => setCaseId(e.target.value)}>
                    <option value="">All cases I can see</option>
                    {(cases.data ?? []).map((c) => (
                      <option key={c.id} value={c.id}>{c.ref} · {c.employee}</option>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="Focus">
                  <NativeSelect value={focus} onChange={(e) => setFocus(e.target.value as AskFocus)}>
                    <option value="">My default ({eff ? FOCUS_LABEL[eff.focus] : '…'})</option>
                    {Object.entries(FOCUS_LABEL).filter(([k]) => k !== 'auto').map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="Detail">
                  <NativeSelect value={detail} onChange={(e) => setDetail(e.target.value as AskDetail)}>
                    <option value="">My default ({eff ? DETAIL_LABEL[eff.detail] : '…'})</option>
                    {Object.entries(DETAIL_LABEL).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label="Format">
                  <NativeSelect value={format} onChange={(e) => setFormat(e.target.value as AskFormat)}>
                    <option value="">My default ({eff ? FORMAT_LABEL[eff.format] : '…'})</option>
                    {Object.entries(FORMAT_LABEL).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </NativeSelect>
                </Field>
              </div>
              <Button type="submit" className="justify-self-start" disabled={!question.trim() || ask.isPending}>
                <Send /> {ask.isPending ? 'Reading evidence…' : 'Ask'}
              </Button>
            </form>
          </Section>
          <Section
            title="Answer"
            actions={a ? <ModeBadge mode={a.mode} model={a.model} prompt={a.prompt_version} /> : undefined}
          >
            {!a ? (
              <Empty>Ask a question to see cited evidence.</Empty>
            ) : (
              <div className="space-y-3">
                {a.presentation && (
                  <div className="flex flex-wrap gap-1.5 text-xs">
                    <Pill className="bg-muted text-muted-foreground ring-border">Presented for {a.presentation.profile_label}</Pill>
                    <Pill className="bg-muted text-muted-foreground ring-border">{FOCUS_LABEL[a.presentation.focus]}</Pill>
                    <Pill className="bg-muted text-muted-foreground ring-border">{DETAIL_LABEL[a.presentation.detail]}</Pill>
                    <Pill className="bg-muted text-muted-foreground ring-border">{FORMAT_LABEL[a.presentation.format]}</Pill>
                    {a.presentation.guidance_version && (
                      <Pill className="bg-sky-50 text-sky-800 ring-sky-200">PMO guidance v{a.presentation.guidance_version}</Pill>
                    )}
                  </div>
                )}
                <pre className="font-sans text-sm whitespace-pre-wrap">{a.answer}</pre>
                {a.refused && (
                  <p className="text-xs text-amber-800">Readiness is decided by the case's technical owner, never by the assistant.</p>
                )}
                {a.citations.length > 0 && (
                  <div>
                    <div className="mb-1 text-xs font-medium text-muted-foreground">Citations (verified verbatim against the original)</div>
                    <ul className="space-y-1 text-xs">
                      {a.citations.map((c, i) => {
                        const row = cases.data?.find((x) => x.id === caseId)
                        return (
                          <li key={i} className="rounded border bg-muted/30 px-2 py-1">
                            “{c.quote}”
                            {row && (
                              <Link className="ml-1 text-primary hover:underline" to={`/app/cases/${row.ref}?tab=evidence`}>
                                open source
                              </Link>
                            )}
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </Section>
        </div>
        <Section title="How Ask Graft stays within your access">
          <ul className="space-y-2 text-sm">
            {[
              'The server picks the evidence first, from cases your roles let you see. Summary-level roles send no raw evidence to the model.',
              'Focus, detail, format, your working context and the PMO guidance change emphasis and layout only.',
              'Asking it to “act as PMO” changes nothing: the evidence set was fixed before the question reached the model.',
              'Every statement is a verbatim quote checked against the original source. Anything that fails is refused.',
              'It never decides readiness, closes onboarding, changes access or saves a task.',
            ].map((t) => (
              <li key={t} className="flex gap-2">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" />
                {t}
              </li>
            ))}
          </ul>
          {eff && <p className="mt-3 text-xs text-muted-foreground">Your profile: {eff.profile_label}. {eff.emphasis}</p>}
        </Section>
      </div>
    </div>
  )
}
