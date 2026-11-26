import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from '@/app/AppShell'
import HomePage from '@/app/home/HomePage'
import CasesPage from '@/app/cases/CasesPage'
import CasePage from '@/app/cases/CasePage'
import InboxPage from '@/app/inbox/InboxPage'
import TasksPage from '@/app/tasks/TasksPage'
import KnowledgePage from '@/app/knowledge/KnowledgePage'
import InsightsPage from '@/app/insights/InsightsPage'
import SettingsPage from '@/app/settings/SettingsPage'
import Landing from '@/site/Landing'
import Pricing from '@/site/Pricing'
import Login from '@/site/Login'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/pricing" element={<Pricing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/app" element={<AppShell />}>
        <Route index element={<Navigate to="home" replace />} />
        <Route path="home" element={<HomePage />} />
        <Route path="cases" element={<CasesPage />} />
        <Route path="cases/:caseId" element={<CasePage />} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="knowledge" element={<KnowledgePage />} />
        <Route path="insights" element={<InsightsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="home" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
