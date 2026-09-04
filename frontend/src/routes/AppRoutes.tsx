import { Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { AnalyzeLeadPage } from '@/pages/AnalyzeLeadPage';
import { AnalyticsPage } from '@/pages/AnalyticsPage';
import { CompaniesPage } from '@/pages/CompaniesPage';
import { CompanyDetailsPage } from '@/pages/CompanyDetailsPage';
import { ContactsPage } from '@/pages/ContactsPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { LeadDetailsPage } from '@/pages/LeadDetailsPage';
import { LeadsPage } from '@/pages/LeadsPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { OpportunitiesPage } from '@/pages/OpportunitiesPage';
import { OutreachPage } from '@/pages/OutreachPage';
import { SettingsPage } from '@/pages/SettingsPage';

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
        <Route path="/opportunities" element={<OpportunitiesPage />} />
        <Route path="/contacts" element={<ContactsPage />} />
        <Route path="/outreach" element={<OutreachPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
