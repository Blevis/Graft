import { BarChart3, BookOpen, Briefcase, CheckSquare, Home, Inbox, Settings, type LucideIcon } from 'lucide-react'

export type NavItem = { to: string; label: string; icon: LucideIcon }

export const NAV_ITEMS: NavItem[] = [
  { to: '/app/home', label: 'Home', icon: Home },
  { to: '/app/cases', label: 'Cases', icon: Briefcase },
  { to: '/app/inbox', label: 'Inbox', icon: Inbox },
  { to: '/app/tasks', label: 'Tasks', icon: CheckSquare },
  { to: '/app/knowledge', label: 'Knowledge', icon: BookOpen },
  { to: '/app/insights', label: 'Insights', icon: BarChart3 },
  { to: '/app/settings', label: 'Settings', icon: Settings },
]
