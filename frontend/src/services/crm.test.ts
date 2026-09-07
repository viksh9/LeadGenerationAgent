import { describe, expect, it } from 'vitest';

import {
  activityStatusDisplay,
  followUpStatusDisplay,
  formatPipelineValue,
  formatRate,
  salesStageDisplay,
} from './crm';

describe('crm formatters — real-data honesty', () => {
  it('formatPipelineValue renders "Not available" for the NOT_AVAILABLE sentinel and null', () => {
    expect(formatPipelineValue('NOT_AVAILABLE')).toBe('Not available');
    expect(formatPipelineValue(null)).toBe('Not available');
    expect(formatPipelineValue(undefined)).toBe('Not available');
  });

  it('formatPipelineValue formats a real numeric value', () => {
    // Grouping/locale may vary; assert the digits are present and it is not "Not available".
    const formatted = formatPipelineValue(500000, 'INR');
    expect(formatted).not.toBe('Not available');
    expect(formatted.replace(/[^0-9]/g, '')).toContain('500000');
  });

  it('formatPipelineValue with an unknown currency still shows the number (never fabricates)', () => {
    const formatted = formatPipelineValue(1000, 'ZZZ');
    expect(formatted.replace(/[^0-9]/g, '')).toContain('1000');
  });

  it('formatRate renders "Insufficient data" for the sentinel and nullish, never 0%', () => {
    expect(formatRate('INSUFFICIENT_DATA')).toBe('Insufficient data');
    expect(formatRate(null)).toBe('Insufficient data');
    expect(formatRate(undefined)).toBe('Insufficient data');
  });

  it('formatRate renders a real fraction as a percentage', () => {
    expect(formatRate(0.6)).toBe('60%');
    expect(formatRate(1)).toBe('100%');
    expect(formatRate(0.6667)).toBe('66.7%');
  });
});

describe('crm display helpers', () => {
  it('salesStageDisplay maps known stages and falls back for unknown', () => {
    expect(salesStageDisplay('WON').label.toLowerCase()).toContain('won');
    const fallback = salesStageDisplay('MYSTERY' as never);
    expect(fallback.label).toBeTruthy();
    expect(fallback.className).toBeTruthy();
  });

  it('activityStatusDisplay maps SENT and has a fallback', () => {
    expect(activityStatusDisplay('SENT').label.toLowerCase()).toContain('sent');
    expect(activityStatusDisplay('WEIRD' as never).label).toBeTruthy();
  });

  it('followUpStatusDisplay maps OPEN and has a fallback', () => {
    expect(followUpStatusDisplay('OPEN').label.toLowerCase()).toContain('open');
    expect(followUpStatusDisplay('WEIRD' as never).label).toBeTruthy();
  });
});
