import { HttpErrorResponse } from '@angular/common/http';
import { describeHttpError } from './error-message';

const err = (status: number, body: unknown = null) => new HttpErrorResponse({ status, error: body });

describe('describeHttpError', () => {
  it('explains an unreachable backend (no response, or 502/504 from the dev proxy)', () => {
    for (const status of [0, 502, 504]) {
      expect(describeHttpError(err(status), 'x')).toContain('Cannot reach the server');
    }
  });

  it('shows the API message as is (also for 503 database problems)', () => {
    expect(describeHttpError(err(409, { detail: 'An account with this email already exists.' }), 'x'))
      .toBe('An account with this email already exists.');
    expect(describeHttpError(err(503, { detail: 'The database schema is out of date.' }), 'x'))
      .toBe('The database schema is out of date.');
  });

  it('shows the first validation message for 422', () => {
    expect(describeHttpError(err(422, { detail: [{ msg: 'Value error, Password must contain at least one letter and one digit.' }] }), 'x'))
      .toBe('Password must contain at least one letter and one digit.');
  });

  it('for an unexplained 500 asks to check that the backend runs, and uses the fallback otherwise', () => {
    expect(describeHttpError(err(500, 'Internal Server Error'), 'x')).toContain('backend is running');
    expect(describeHttpError(err(404), 'fallback')).toBe('fallback');
    expect(describeHttpError(new Error('boom'), 'fallback')).toBe('fallback');
  });
});
