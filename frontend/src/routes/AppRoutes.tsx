import { Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { AnalyzeLeadPage } from '@/pages/AnalyzeLeadPage';
import { AnalyticsPage } from '@/pages/AnalyticsPage';
import { CareerIntegrationPage } from '@/pages/CareerIntegrationPage';
import { CompaniesPage } from '@/pages/CompaniesPage';
import { CompanyDetailsPage } from '@/pages/CompanyDetailsPage';
import { ContactsPage } from '@/pages/ContactsPage';
import { CrmPage } from '@/pages/CrmPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { LeadDetailsPage } from '@/pages/LeadDetailsPage';
import { LeadsPage } from '@/pages/LeadsPage';
import { MonitoringPage } from '@/pages/MonitoringPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { OpportunitiesPage } from '@/pages/OpportunitiesPage';
import { OutreachPage } from '@/pages/OutreachPage';
import { PipelinePage } from '@/pages/PipelinePage';
import { SettingsPage } from '@/pages/SettingsPage';
import { SignalsPage } from '@/pages/SignalsPage';
import { TendersPage } from '@/pages/TendersPage';

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/leads" element={<LeadsPage />} />
        <Route path="/leads/analyze" element={<AnalyzeLeadPage />} />
        <Route path="/leads/:id" element={<LeadDetailsPage />} />
        <Route path="/companies" element={<CompaniesPage />} />
        <Route path="/companies/:name" element={<CompanyDetailsPage />} />
        <Route path="/career-integration" element={<CareerIntegrationPage />} />
        <Route path="/opportunities" element={<OpportunitiesPage />} />
        <Route path="/pipeline" element={<PipelinePage />} />
        <Route path="/crm" element={<CrmPage />} />
        <Route path="/signals" element={<SignalsPage />} />
        <Route path="/tenders" element={<TendersPage />} />
        <Route path="/contacts" element={<ContactsPage />} />
        <Route path="/outreach" element={<OutreachPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/monitoring" element={<MonitoringPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
