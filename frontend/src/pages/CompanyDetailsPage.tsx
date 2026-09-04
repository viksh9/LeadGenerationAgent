import { useParams } from 'react-router-dom';
import { PlaceholderPage } from '@/components/common/PlaceholderPage';

export function CompanyDetailsPage() {
  const { id } = useParams();
  return <PlaceholderPage title={`Company #${id ?? ''}`.trim()} subtitle="Company profile and leads." />;
}
