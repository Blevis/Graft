import { BarChart3, BookOpen, Briefcase, CheckSquare, FolderKanban, Home, Inbox, MessageSquareQuote, Settings, type LucideIcon } from 'lucide-react'

export type NavItem = { to: string; label: string; icon: LucideIcon }

/** Sidebar order: the daily work first, then what explains it, then administration. */
export const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: 'Work',
    items: [
      { to: '/app/home', label: 'Home', icon: Home },
      { to: '/app/cases', label: 'Cases', icon: Briefcase },
      { to: '/app/projects', label: 'Projects', icon: FolderKanban },
      { to: '/app/inbox', label: 'Inbox', icon: Inbox },
      { to: '/app/tasks', label: 'Queues', icon: CheckSquare },
    ],
  },
  {
    label: 'Understand',
    items: [
      { to: '/app/knowledge', label: 'Knowledge', icon: BookOpen },
      { to: '/app/ask', label: 'Ask Graft', icon: MessageSquareQuote },
      { to: '/app/insights', label: 'Insights', icon: BarChart3 },
    ],
  },
  { label: 'Administer', items: [{ to: '/app/settings', label: 'Settings', icon: Settings }] },
]

export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items)
