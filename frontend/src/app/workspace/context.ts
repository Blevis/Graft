import { createContext, useContext } from 'react'
import type { CaseDetail } from '@/lib/types'
import type { Screen } from './catalog'
import type { Dataset, Person } from './model'

export interface Workspace {
  screen: Screen
  demo: boolean
  data: Dataset
  person?: Person
  detail?: CaseDetail
  date: string
  href: (id: number, ref?: string, extra?: Record<string, string>) => string
  draftKey: string
}
export const WorkspaceContext = createContext<Workspace | null>(null)
export const useWorkspace = () => useContext(WorkspaceContext)!
