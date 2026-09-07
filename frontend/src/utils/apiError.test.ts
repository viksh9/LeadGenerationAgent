import { describe, expect, it } from 'vitest';
import { friendlyMessage } from './apiError';

describe('friendlyMessage', () => {
  it('maps known statuses to friendly text without leaking internals', () => {
    expect(friendlyMessage(404, 'x')).toMatch(/could not be found/i);
    expect(friendlyMessage(422, 'x')).toMatch(/fields are invalid/i);
    expect(friendlyMessage(429, 'x')).toMatch(/too many requests/i);
    expect(friendlyMessage(500, 'x')).toMatch(/something went wrong/i);
    expect(friendlyMessage(503, 'x')).toMatch(/temporarily unavailable/i);
  });

  it('uses the fallback for unknown statuses', () => {
    expect(friendlyMessage(418, 'custom fallback')).toBe('custom fallback');
    expect(friendlyMessage(undefined, '')).toMatch(/unexpected error/i);
  });
});
