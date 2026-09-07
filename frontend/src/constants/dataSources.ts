/**
 * Planned real-data sources shown in Settings.
 *
 * Static placeholder that mirrors the backend source registry
 * (config/sources.yaml). There is no source-registry API yet, so this is not
 * fetched — every source is PLANNED until its collector is implemented and
 * verified. Replace with a real API call once the backend exposes the registry.
 */
export type DataSourceStatus = 'Planned' | 'Available' | 'Connected' | 'Disabled';

export interface DataSourceInfo {
  id: string;
  name: string;
  category: string;
  status: DataSourceStatus;
}

export const PLANNED_DATA_SOURCES: DataSourceInfo[] = [
  { id: 'adzuna', name: 'Adzuna Jobs API', category: 'Job', status: 'Available' },
  { id: 'company_career_pages', name: 'Company Career Pages', category: 'Company', status: 'Planned' },
  { id: 'government_open_data', name: 'Government Open Data / Tenders', category: 'Government', status: 'Planned' },
  { id: 'rss_news', name: 'RSS / Business & Technology News', category: 'News', status: 'Planned' },
  { id: 'project_registry', name: 'Public Project / Contract Registry', category: 'Project', status: 'Planned' },
  { id: 'business_database', name: 'Business / Company Database', category: 'Business database', status: 'Planned' },
];
