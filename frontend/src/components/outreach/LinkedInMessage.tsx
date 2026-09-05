import { MessageEditor } from '@/components/outreach/MessageEditor';
import type { OutreachItem } from '@/types/outreach';

/** LinkedIn channel. The LinkedIn variant is not persisted in this phase. */
export function LinkedInMessage({ item }: { item: OutreachItem }) {
  if (!item.message.linkedin) {
    return <p className="text-sm text-slate-400">No LinkedIn message has been generated.</p>;
  }
  return (
    <MessageEditor label="LinkedIn message" original={item.message.linkedin} copyLabel="Copy LinkedIn message" rows={6} />
  );
}
