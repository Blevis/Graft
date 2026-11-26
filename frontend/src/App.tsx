import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from '@/app/AppShell'
import { LiveWorkspace, PreviewWorkspace } from '@/app/workspace/WorkspacePage'
import HomePage from '@/app/home/HomePage'
import CasesPage from '@/app/cases/CasesPage'
import CasePage from '@/app/cases/CasePage'
import InboxPage from '@/app/inbox/InboxPage'
import TasksPage from '@/app/tasks/TasksPage'
import KnowledgePage from '@/app/knowledge/KnowledgePage'
import InsightsPage from '@/app/insights/InsightsPage'
import SettingsPage from '@/app/settings/SettingsPage'
import PeoplePage from '@/app/settings/PeoplePage'
import GuidancePage from '@/app/settings/GuidancePage'
import ProjectsPage, { ProjectPage } from '@/app/projects/ProjectsPage'
import AskPage from '@/app/ask/AskPage'
import { ImportPage } from '@/app/cases/NewCase'
import WorkflowSettings from '@/app/settings/WorkflowSettings'
import Landing from '@/site/Landing'
import Pricing from '@/site/Pricing'
import Login from '@/site/Login'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/pricing" element={<Pricing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/orchid/:slug?" element={<PreviewWorkspace />} />
      <Route path="/app/workspace/:slug?" element={<LiveWorkspace />} />
      <Route path="/app" element={<AppShell />}>
        <Route index element={<Navigate to="home" replace />} />
        <Route path="home" element={<HomePage />} />
        <Route path="cases" element={<CasesPage />} />
        <Route path="cases/import" element={<ImportPage />} />
        <Route path="cases/:caseId" element={<CasePage />} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="knowledge" element={<KnowledgePage />} />
        <Route path="insights" element={<InsightsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="settings/people" element={<PeoplePage />} />
        <Route path="settings/ai-guidance" element={<GuidancePage />} />
        <Route path="settings/workflow" element={<WorkflowSettings />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId" element={<ProjectPage />} />
        <Route path="ask" element={<AskPage />} />
        <Route path="*" element={<Navigate to="home" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
