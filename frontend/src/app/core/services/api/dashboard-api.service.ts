import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../../config/api.config';
import { DashboardResponse } from './dashboard-response.model';

/**
 * Typed HTTP client for the dashboard endpoint.
 * Pattern for every feature/phase: one `<feature>-api.service.ts` next to this file
 * that only talks HTTP; state lives in a separate data service (see DashboardDataService).
 */
@Injectable({ providedIn: 'root' })
export class DashboardApiService {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE_URL);

  /** GET /api/v1/dashboard — activity of the logged-in user (taken from the token) */
  getDashboard(): Observable<DashboardResponse> {
    return this.http.get<DashboardResponse>(`${this.base}/dashboard`);
  }
}
