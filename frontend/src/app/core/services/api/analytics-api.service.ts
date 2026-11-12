import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../../config/api.config';
import { Analytics, Period } from '../../models/workout.model';

@Injectable({ providedIn: 'root' })
export class AnalyticsApiService {
  private readonly http = inject(HttpClient);
  private readonly url = `${inject(API_BASE_URL)}/analytics`;

  /** GET /api/v1/analytics/workouts?period=week|month */
  workouts(period: Period): Observable<Analytics> {
    return this.http.get<Analytics>(`${this.url}/workouts`, { params: new HttpParams().set('period', period) });
  }
}
