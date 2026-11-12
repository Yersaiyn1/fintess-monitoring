import { InjectionToken } from '@angular/core';

/**
 * Base URL of the FastAPI backend.
 *
 * It is RELATIVE on purpose: in development `ng serve` forwards /api to http://localhost:8000
 * (see proxy.conf.json), in production a reverse proxy (nginx) does the same.
 * That way the browser always talks to one origin and no CORS problems appear.
 * To use a different backend, provide another value for this token in app.config.ts.
 */
export const API_BASE_URL = new InjectionToken<string>('API_BASE_URL', {
  providedIn: 'root',
  factory: () => '/api/v1',
});
