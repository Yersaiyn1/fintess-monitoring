import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../../config/api.config';

export interface UserGoalsResponse {
  steps_daily: number;
  workouts_weekly: number;
  updated_at: string | null;
}

export interface UserGoalsUpdate {
  steps_daily: number;
  workouts_weekly: number;
}

@Injectable({ providedIn: 'root' })
export class GoalsApiService {
  private readonly http = inject(HttpClient);
  private readonly url = `${inject(API_BASE_URL)}/goals`;

  getGoals(): Observable<UserGoalsResponse> {
    return this.http.get<UserGoalsResponse>(this.url);
  }

  updateGoals(body: UserGoalsUpdate): Observable<UserGoalsResponse> {
    return this.http.put<UserGoalsResponse>(this.url, body);
  }
}
