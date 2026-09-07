import { describe, expect, it } from 'vitest';

import { draftStatusDisplay } from './outreachApi';

describe('draftStatusDisplay', () => {
  it('maps every known status to a label + badge class', () => {
    const statuses = ['DRAFT', 'READY_FOR_REVIEW', 'APPROVED', 'SENT', 'CANCELLED', 'FAILED'] as const;
    for (const s of statuses) {
      const d = draftStatusDisplay(s);
      expect(d.label).toBeTruthy();
      expect(d.className).toContain('bg-');
    }
  });

  it('marks SENT distinctly (emerald) and FAILED distinctly (rose)', () => {
    expect(draftStatusDisplay('SENT').className).toContain('emerald');
    expect(draftStatusDisplay('FAILED').className).toContain('rose');
  });

  it('falls back gracefully for an unknown status', () => {
    const d = draftStatusDisplay('MYSTERY' as never);
    expect(d.label).toBe('MYSTERY');
    expect(d.className).toContain('bg-');
  });
});
