import { describe, expect, it } from 'vitest';
import { alertSeverityDisplay, alertStatusDisplay, alertTypeLabel } from './alerts';

describe('alert display helpers', () => {
  it('maps severities to distinct colour + label pairs', () => {
    expect(alertSeverityDisplay('CRITICAL')).toEqual({
      label: 'Critical',
      className: expect.stringContaining('rose'),
    });
    expect(alertSeverityDisplay('HIGH').className).toContain('amber');
    expect(alertSeverityDisplay('MEDIUM').className).toContain('blue');
    expect(alertSeverityDisplay('LOW').className).toContain('slate');
  });

  it('falls back gracefully for an unknown severity', () => {
    // @ts-expect-error — exercising the runtime fallback path.
    const display = alertSeverityDisplay('MYSTERY');
    expect(display.label).toBe('MYSTERY');
    expect(display.className).toContain('slate');
  });

  it('maps statuses to colour + label pairs', () => {
    expect(alertStatusDisplay('NEW').label).toBe('New');
    expect(alertStatusDisplay('ACKNOWLEDGED').label).toBe('Acknowledged');
    expect(alertStatusDisplay('RESOLVED').className).toContain('emerald');
    expect(alertStatusDisplay('DISMISSED').className).toContain('slate');
  });

  it('humanizes known alert types', () => {
    expect(alertTypeLabel('NEW_HIGH_INTENT_LEAD')).toBe('New high-intent lead');
    expect(alertTypeLabel('TENDER_CLOSING_SOON')).toBe('Tender closing soon');
    expect(alertTypeLabel('SOURCE_RECOVERED')).toBe('Source recovered');
  });

  it('title-cases an unknown alert type as a fallback', () => {
    expect(alertTypeLabel('SOME_NEW_KIND')).toBe('Some New Kind');
  });
});
