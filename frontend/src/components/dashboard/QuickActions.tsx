import { useNavigate } from 'react-router-dom';
import { Flame, List, Sparkles } from 'lucide-react';
import { Card, CardTitle } from '@/components/ui/Card';

export function QuickActions() {
  const navigate = useNavigate();
  return (
    <Card>
      <CardTitle>Quick Actions</CardTitle>
      <div className="mt-4 flex flex-col gap-2">
        {/* The Analyze Lead flow is not built yet — disabled with an explanation. */}
        <button
          type="button"
          className="btn-primary justify-start"
          disabled
          title="The Analyze Lead flow will be available in a later phase."
          aria-label="Analyze New Lead (coming soon)"
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          Analyze New Lead
        </button>
        <button
          type="button"
          className="btn-secondary justify-start"
          onClick={() => navigate('/leads?lead_priority=HOT')}
        >
          <Flame className="h-4 w-4 text-rose-600" aria-hidden="true" />
          View Hot Leads
        </button>
        <button
          type="button"
          className="btn-secondary justify-start"
          onClick={() => navigate('/leads')}
        >
          <List className="h-4 w-4" aria-hidden="true" />
          View All Leads
        </button>
      </div>
    </Card>
  );
}
