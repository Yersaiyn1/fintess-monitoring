import { HttpErrorResponse } from '@angular/common/http';

/**
 * Turns an HTTP failure into a message a user (or a student at a demo) can act on.
 *  - status 0 / 502 / 504: the browser or the dev proxy could not reach the backend
 *  - other 5xx without a message: `ng serve` answers a bare 500 when the backend is not running,
 *    and the backend itself answers 500 on an unexpected bug, so the text covers both
 *  - text from the API (`detail`) is shown as is (e.g. "An account with this email already exists.")
 */
export function describeHttpError(e: unknown, fallback: string): string {
  if (!(e instanceof HttpErrorResponse)) return fallback;

  if (e.status === 0 || e.status === 502 || e.status === 504) {
    return 'Cannot reach the server. Make sure the backend is running (uvicorn on port 8000).';
  }
  const detail = e.error?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0]?.msg) {
    return String(detail[0].msg).replace(/^Value error,\s*/, '');
  }
  if (e.status >= 500) {
    return 'Server error. Make sure the backend is running (uvicorn on port 8000) and check its terminal for details.';
  }
  return fallback;
}
