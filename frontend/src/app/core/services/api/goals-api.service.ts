import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../../config/api.config';

export type GoalPeriod = 'daily' | 'weekly';
export type GoalMetric =
  | 'steps'
  | 'calories_kcal'
  | 'distance_km'
  | 'active_minutes'
  | 'workouts';

export interface GoalProgress {
  goal_id: number;
  period: GoalPeriod;
  metric: GoalMetric;
  target_value: number;
  current_value: number;
  progress_percent: number;
  achieved: boolean;
}

export interface HealthAlerts {
  high_heart_rate_alert: boolean;
  avg_heart_rate_7d: number | null;
  heart_rate_readings_7d: number;
  inactivity_alert: boolean;
  active_days_7d: number;
  messages: string[];
}

export interface GoalsSummary {
  goals: GoalProgress[];
  alerts: HealthAlerts;
}

@Injectable({ providedIn: 'root' })
export class GoalsApiService {
  private readonly http = inject(HttpClient);
  private readonly url = `${inject(API_BASE_URL)}/goals`;

  summary(): Observable<GoalsSummary> {
    return this.http.get<GoalsSummary>(this.url);
  }

  upsertGoal(
    period: GoalPeriod,
    metric: GoalMetric,
    targetValue: number,
  ): Observable<GoalProgress> {
    return this.http.post<GoalProgress>(this.url, {
      period,
      metric,
      target_value: targetValue,
    });
  }

  deleteGoal(goalId: number): Observable<void> {
    return this.http.delete<void>(`${this.url}/${goalId}`);
  }
}
