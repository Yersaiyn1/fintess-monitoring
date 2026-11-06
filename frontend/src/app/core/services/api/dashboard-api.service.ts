import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { DashboardResponse } from './dashboard-response.model';

/** Simple typed HTTP client for the dashboard endpoint */
@Injectable({
  providedIn: 'root',
})
export class DashboardApiService {
  private readonly baseUrl = '/api'; // prefixed in main.ts proxy or same origin

  constructor(private http: HttpClient) {}

  /** GET /api/dashboard/{user_id} */
  getDashboard(userId: number): Observable<DashboardResponse> {
    return this.http.get<DashboardResponse>(
      `${this.baseUrl}/dashboard/${userId}`
    );
  }
}

