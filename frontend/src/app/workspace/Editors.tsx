import { useState, type FormEvent } from 'react'
import {
  Check,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  FilePenLine,
  Fingerprint,
  Paperclip,
  Save,
  ShieldCheck,
} from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { usePostObservation, useRecordTraining } from '@/lib/api'
import ReviewDialog from '../cases/ReviewDialog'
import { TrainingSection } from '../cases/StakeholdersPanel'
import { useWorkspace } from './context'
import { Empty, Panel, RecordStrip, Rows, Spotlight } from './ui'
import { EvidenceList } from './CaseWork'

type Fields = Record<string, string>
function useDraft(defaults: Fields = {}) {
  const { draftKey } = useWorkspace()
  const [fields, setFields] = useState<Fields>(() => {
    try {
      const stored: unknown = JSON.parse(sessionStorage.getItem(draftKey) ?? '{}')
      return stored && typeof stored === 'object' && Object.values(stored).every((v) => typeof v === 'string')
        ? { ...defaults, ...(stored as Fields) }
        : defaults
    } catch {
      return {}
    }
  })
  const [message, setMessage] = useState('')
  function update(k: string, v: string) {
    setFields((f) => ({ ...f, [k]: v }))
    setMessage('')
  }
  function save() {
    try {
      sessionStorage.setItem(draftKey, JSON.stringify(fields))
      setMessage('Draft saved in this browser tab.')
    } catch {
      setMessage('Browser storage unavailable. Download a copy of your draft.')
    }
  }
  function download() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify({ status: 'draft', fields }, null, 2)], { type: 'application/json' }),
    )
    const a = document.createElement('a')
    a.href = url
    a.download = draftKey.split(':').slice(-2).join('-') + '-draft.json'
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return { fields, update, save, download, message }
}
interface FieldSpec {
  name: string
  placeholder?: string
  options?: string[]
  type?: string
  required?: boolean
}
function FieldsView({ spec, draft }: { spec: FieldSpec[]; draft: ReturnType<typeof useDraft> }) {
  return (
    <div className="ow-fields">
      {spec.map((f) => (
        <label key={f.name}>
          {f.name}
          {f.options ? (
            <select
              required={f.required}
              value={draft.fields[f.name] ?? ''}
              onChange={(e) => draft.update(f.name, e.target.value)}
            >
              <option value="">Select an option</option>
              {f.options.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          ) : f.type === 'textarea' ? (
            <textarea
              required={f.required}
              placeholder={f.placeholder}
              value={draft.fields[f.name] ?? ''}
              onChange={(e) => draft.update(f.name, e.target.value)}
            />
          ) : (
            <input
              type={f.type ?? 'text'}
              required={f.required}
              placeholder={f.placeholder}
              value={draft.fields[f.name] ?? ''}
              onChange={(e) => draft.update(f.name, e.target.value)}
            />
          )}
        </label>
      ))}
    </div>
  )
}
const stepNames = ['Employee', 'Movement', 'Project', 'Stakeholders', 'Review']
const intakeFields: FieldSpec[][] = [
  [
    { name: 'Employee name', placeholder: 'Full name', required: true },
    { name: 'Employee identifier', placeholder: 'Employee ID', required: true },
    { name: 'Work email', type: 'email', placeholder: 'name@company.com' },
    { name: 'Expected start date', type: 'date' },
  ],
  [
    { name: 'Movement type', options: ['New hire', 'Internal reallocation'], required: true },
    { name: 'Previous project', placeholder: 'If known' },
  ],
  [
    { name: 'Receiving project', placeholder: 'Project name or unconfirmed', required: true },
    { name: 'Expected role', placeholder: 'Role on the receiving project' },
  ],
  [
    { name: 'Line manager', placeholder: 'Name or unconfirmed' },
    { name: 'Technical owner', placeholder: 'Name or unconfirmed' },
    { name: 'KT owner', placeholder: 'Name or unconfirmed' },
  ],
]
export function Intake() {
  const [step, setStep] = useState(0),
    draft = useDraft()
  function submit(e: FormEvent) {
    e.preventDefault()
    if (step < 4) setStep(step + 1)
    else draft.save()
  }
  return (
    <>
      <div className="ow-wizard">
        {stepNames.map((name, i) => (
          <button
            key={name}
            disabled={i > step}
            className={step === i ? 'current' : ''}
            onClick={() => setStep(i)}
          >
            <i>{i < step ? <Check size={16} /> : i + 1}</i>
            {name}
          </button>
        ))}
      </div>
      <div className="ow-grid major">
        <Panel
          title={
            [
              'Employee information',
              'Employee movement',
              'Project assignment',
              'Accountable stakeholders',
              'Review intake draft',
            ][step]
          }
          sub={'Step ' + (step + 1) + ' of 5'}
          icon={Fingerprint}
        >
          <form onSubmit={submit}>
            {step < 4 ? (
              <FieldsView spec={intakeFields[step]} draft={draft} />
            ) : (
              <Rows rows={Object.entries(draft.fields).map(([title, detail]) => ({ title, detail }))} />
            )}
            <div className="ow-form-actions">
              {step > 0 && (
                <button type="button" className="ow-secondary" onClick={() => setStep(step - 1)}>
                  <ChevronLeft size={16} />
                  Back
                </button>
              )}
              <button className="ow-button">
                {step < 4 ? 'Continue' : 'Save intake draft'}
                <ChevronRight size={16} />
              </button>
              <button type="button" className="ow-text-button" onClick={draft.save}>
                Save progress
              </button>
              {step === 4 && (
                <button className="ow-text-button" type="button" onClick={draft.download}>
                  Download draft
                </button>
              )}
            </div>
          </form>
          <p role="status">{draft.message}</p>
        </Panel>
        <div className="ow-stack">
          <Spotlight label="Case intake" title="One case. Clear accountability.">
            Capture the employee’s movement, receiving project and responsible stakeholders before review.
          </Spotlight>
          <Panel title="Intake checklist">
            <Rows
              rows={[
                { title: 'Employee information', detail: 'Name and employee identifier', icon: Fingerprint },
                {
                  title: 'Project assignment',
                  detail: 'Confirm the project or flag the gap',
                  icon: ClipboardCheck,
                },
                { title: 'Stakeholders', detail: 'Identify the responsible roles', icon: ShieldCheck },
              ]}
            />
          </Panel>
        </div>
      </div>
    </>
  )
}
export function Editor({ kind }: { kind: 'evidence' | 'assessment' | 'signoff' | 'checkin' }) {
  const w = useWorkspace(),
    [params] = useSearchParams()
  const requirements = w.data.access.filter((a) => a.ref === w.person?.ref).map((a) => a.system)
  const requested = params.get('system') ?? ''
  const draft = useDraft(
    kind === 'evidence'
      ? {
          'Evidence type': 'Access usability confirmation',
          'Related requirement': requirements.includes(requested)
            ? requested
            : (requirements[0] ?? 'Practical execution'),
        }
      : {},
  )
  const [sign, setSign] = useState(false)
  const assessment = kind === 'assessment',
    decision = kind === 'signoff',
    evidence = kind === 'evidence',
    checkin = kind === 'checkin'
  const p = w.person
  const post = usePostObservation(p?.ref ?? '')
  const training = useRecordTraining(p?.ref ?? '')
  const canAssess = assessment && w.detail?.permissions.can_record_training
  const sourceKind = checkin ? 'manager_check_in' : 'employee_evidence'
  const canSubmit = (evidence || checkin) && w.detail?.permissions.observation_kinds?.includes(sourceKind)
  if (!p) return <Empty>No case available for this form.</Empty>
  const spec: FieldSpec[] = evidence
    ? [
        {
          name: 'Evidence type',
          options: ['Access usability confirmation', 'Work observation', 'Learning artifact'],
          required: true,
        },
        {
          name: 'Related requirement',
          options: [...requirements, 'Practical execution', 'Knowledge transfer'],
        },
        {
          name: 'Observation',
          type: 'textarea',
          placeholder: 'Describe the test, its scope and what happened.',
          required: true,
        },
        { name: 'Approved evidence reference', placeholder: 'Project-owned link or reference ID' },
      ]
    : checkin
      ? [
          {
            name: 'Observed progress',
            type: 'textarea',
            placeholder: 'What work did you observe?',
            required: true,
          },
          { name: 'Support required', placeholder: 'Describe the assistance needed' },
          { name: 'Practical blockers', placeholder: 'Record any outstanding dependencies' },
        ]
      : decision
        ? [
            {
              name: 'Proposed decision',
              options: [
                'Partially ready',
                'Ready with support',
                'Independently ready',
                'Request additional evidence',
              ],
              required: true,
            },
            { name: 'Scope', placeholder: 'Which activities does this decision cover?', required: true },
            {
              name: 'Decision rationale',
              type: 'textarea',
              placeholder: 'Reference the evidence and outstanding requirements.',
              required: true,
            },
          ]
        : [
            { name: 'Practical scope', placeholder: 'Activity or scenario under assessment', required: true },
            {
              name: 'Technical feedback',
              type: 'textarea',
              placeholder: 'Record the observed work and any support required.',
              required: true,
            },
            {
              name: 'Assessment result',
              options: [
                'Request additional evidence',
                'Supported execution observed',
                'Independent execution observed',
              ],
            },
          ]
  return (
    <>
      <RecordStrip />
      <div className="ow-grid major">
        <Panel
          title={
            evidence
              ? 'Prepare evidence'
              : checkin
                ? 'New observation'
                : decision
                  ? 'Decision rationale'
                  : 'Technical feedback'
          }
          sub={decision ? 'Draft for technical review' : 'Case-specific working draft'}
          aside={<FilePenLine size={21} />}
        >
          <form
            onChange={() => {
              if (post.isSuccess || post.isError) post.reset()
              if (training.isSuccess || training.isError) training.reset()
            }}
            onSubmit={(e) => {
              e.preventDefault()
              if (
                canSubmit &&
                (e.nativeEvent as SubmitEvent).submitter?.getAttribute('value') === 'submit-source'
              ) {
                post.mutate({
                  kind: sourceKind,
                  title: (checkin ? 'Manager check-in' : 'Employee evidence') + ' · ' + p.name,
                  body: Object.entries(draft.fields)
                    .filter(([, v]) => v.trim())
                    .map(([k, v]) => k + ': ' + v.trim())
                    .join('\n'),
                })
              } else if (
                canAssess &&
                (e.nativeEvent as SubmitEvent).submitter?.getAttribute('value') === 'record-assessment'
              ) {
                training.mutate({
                  kind: 'observation',
                  title: draft.fields['Practical scope'],
                  notes: [draft.fields['Technical feedback'], draft.fields['Assessment result']]
                    .filter(Boolean)
                    .join('\n'),
                  activity_date: w.date,
                })
              } else draft.save()
            }}
          >
            <FieldsView spec={spec} draft={draft} />
            <div className="ow-form-actions">
              {canSubmit && (
                <button
                  className="ow-button"
                  value="submit-source"
                  disabled={post.isPending || post.isSuccess}
                >
                  Submit for review
                </button>
              )}
              {canAssess && (
                <button
                  className="ow-button"
                  value="record-assessment"
                  disabled={training.isPending || training.isSuccess}
                >
                  Record observation
                </button>
              )}
              <button className={canSubmit ? 'ow-secondary' : 'ow-button'}>
                <Save size={16} />
                Save draft
              </button>
              <button type="button" className="ow-text-button" onClick={draft.download}>
                Download draft
              </button>
            </div>
          </form>
          <p className="ow-note" role="status">
            {training.isError
              ? training.error.message
              : training.isSuccess
                ? 'Assessment recorded in the training log.'
                : post.isError
                  ? post.error.message
                  : post.isSuccess
                    ? 'Observation submitted to the case evidence record.'
                    : draft.message ||
                      'Drafts are kept in this browser tab. Download a copy to share for review.'}
          </p>
        </Panel>
        <div className="ow-stack">
          <Spotlight
            label={
              checkin
                ? 'Previous assessment'
                : decision
                  ? 'Provisional assessment'
                  : assessment
                    ? 'Observed performance'
                    : 'Review status'
            }
            title={evidence ? w.data.review : p.status}
          >
            {checkin
              ? (w.data.reports.find((r) => r.author.toLowerCase().includes('line manager'))?.body ??
                'No previous line manager report available for this case.')
              : assessment || decision
                ? 'Compare observed practical execution with the scope of the proposed decision.'
                : 'A submitted observation needs review before it can support a readiness decision.'}
          </Spotlight>
          <Panel
            title={
              assessment
                ? 'Acceptance criteria'
                : decision
                  ? 'Evidence summary'
                  : checkin
                    ? 'Recommended follow-up'
                    : 'Submission checklist'
            }
          >
            <Rows
              rows={
                assessment
                  ? [
                      {
                        title: 'Independent execution',
                        detail: 'Observe the required work without assistance',
                      },
                      { title: 'Complex scenarios', detail: 'Document remaining cases' },
                      { title: 'Traceability', detail: 'Identify approved work samples' },
                    ]
                  : decision || checkin
                    ? p.flags.map((title) => ({ title, icon: ClipboardCheck }))
                    : [
                        {
                          title: 'Requirement',
                          detail: 'Identify the system or activity tested',
                          icon: ShieldCheck,
                        },
                        {
                          title: 'Evidence reference',
                          detail: 'Link to an approved project location',
                          icon: Paperclip,
                        },
                      ]
              }
            />
          </Panel>
        </div>
      </div>
      {(!evidence || w.data.reports.length > 0) && (
        <Panel title="Source reports" sub="Evidence available for the selected case">
          <EvidenceList />
        </Panel>
      )}
      {w.detail?.permissions.can_review && decision && (
        <Panel title="Authorized technical review">
          <button className="ow-button" onClick={() => setSign(true)}>
            Open signed review
          </button>
          <ReviewDialog
            d={w.detail}
            open={sign}
            onOpenChange={setSign}
            draft={{
              scope: draft.fields.Scope,
              rationale: [draft.fields['Proposed decision'], draft.fields['Decision rationale']]
                .filter(Boolean)
                .join(' · '),
            }}
          />
        </Panel>
      )}
      {w.detail?.permissions.can_record_training && assessment && <TrainingSection d={w.detail} />}
    </>
  )
}
