import { useParams } from 'react-router-dom';
import { PlaceholderPage } from '@/components/common/PlaceholderPage';

export function LeadDetailsPage() {
  const { id } = useParams();
  return (
    <PlaceholderPage
      title={`Lead #${id ?? ''}`.trim()}
      subtitle="Full lead intelligence: signals, opportunity, score, POC, and pitch."
    />
  );
}
