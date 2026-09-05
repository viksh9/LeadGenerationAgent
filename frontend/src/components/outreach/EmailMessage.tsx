import { MessageEditor } from '@/components/outreach/MessageEditor';
import type { OutreachItem } from '@/types/outreach';

/**
 * Email channel. The backend persists one pitch (subject + body); the separate
 * opening / value-prop / CTA fields produced at analysis time are not persisted,
 * so subject + body are shown (both editable) rather than fabricated sections.
 */
export function EmailMessage({ item }: { item: OutreachItem }) {
  if (!item.message.pitch) {
    return <p className="text-sm text-slate-400">No email pitch has been generated for this lead.</p>;
  }
  return (
    <div className="space-y-4">
      {item.message.subject !== null && (
        <MessageEditor label="Subject" original={item.message.subject} copyLabel="Copy subject" rows={2} />
      )}
      <MessageEditor label="Message" original={item.message.body} copyLabel="Copy email" rows={10} />
    </div>
  );
}
