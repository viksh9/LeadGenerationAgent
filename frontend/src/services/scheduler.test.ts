import { describe, expect, it } from 'vitest';
import { formatInterval, jobStatusDisplay, runStatusDisplay } from './scheduler';

describe('scheduler display helpers', () => {
  it('maps run statuses to colour + label pairs', () => {
    expect(runStatusDisplay('SUCCESS').className).toContain('emerald');
    expect(runStatusDisplay('RUNNING').className).toContain('blue');
    expect(runStatusDisplay('FAILED').className).toContain('rose');
    expect(runStatusDisplay('PARTIAL').className).toContain('amber');
    expect(runStatusDisplay('SKIPPED').className).toContain('slate');
  });

  it('maps job statuses to colour + label pairs', () => {
    expect(jobStatusDisplay('SUCCESS').label).toBe('Success');
    expect(jobStatusDisplay('RUNNING').className).toContain('blue');
    expect(jobStatusDisplay('SCHEDULED').className).toContain('blue');
    expect(jobStatusDisplay('FAILED').className).toContain('rose');
    expect(jobStatusDisplay('PAUSED').className).toContain('slate');
    expect(jobStatusDisplay('DISABLED').className).toContain('slate');
  });

  it('falls back gracefully for unknown statuses', () => {
    // @ts-expect-error — exercising the runtime fallback path.
    expect(jobStatusDisplay('WAT').label).toBe('WAT');
    // @ts-expect-error — exercising the runtime fallback path.
    expect(runStatusDisplay('WAT').className).toContain('slate');
  });

  it('formats intervals into human cadences', () => {
    expect(formatInterval(0)).toBe('On demand');
    expect(formatInterval(60)).toBe('Every 1m');
    expect(formatInterval(300)).toBe('Every 5m');
    expect(formatInterval(3600)).toBe('Every 1h');
    expect(formatInterval(1800)).toBe('Every 30m');
    expect(formatInterval(86400)).toBe('Every 1d');
  });
});
