import { DetailCard } from '@/components/leads/detail/DetailCard';
import { PitchBlock } from '@/components/leads/detail/PitchBlock';
import type { Lead } from '@/types/lead';

/**
 * Recommended outreach. The backend persists a single pitch string (not the
 * per-channel email/LinkedIn/call breakdown produced at analysis time), so a
 * single copyable pitch is shown rather than fabricated tabs.
 */
export function OutreachPanel({ lead }: { lead: Lead }) {
  return (
    <DetailCard title="Recommended outreach">
      {lead.recommended_pitch ? (
        <PitchBlock pitch={lead.recommended_pitch} />
      ) : (
        <p className="text-sm text-slate-400">No pitch generated for this lead.</p>
      )}
    </DetailCard>
  );
}
