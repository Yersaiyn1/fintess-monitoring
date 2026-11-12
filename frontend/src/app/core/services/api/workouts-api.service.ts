import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../../config/api.config';
import { ActivityType, Workout, WorkoutFilters, WorkoutKind, WorkoutPage } from '../../models/workout.model';

/** HTTP only (Phase 2: tracking, Phase 3: history). State lives in WorkoutTrackerService / pages. */
@Injectable({ providedIn: 'root' })
export class WorkoutsApiService {
  private readonly http = inject(HttpClient);
  private readonly url = `${inject(API_BASE_URL)}/workouts`;

  types(): Observable<ActivityType[]> {
    return this.http.get<ActivityType[]>(`${this.url}/types`);
  }

  /** The workout in progress, or null */
  active(): Observable<Workout | null> {
    return this.http.get<Workout | null>(`${this.url}/active`);
  }

  start(kind: WorkoutKind): Observable<Workout> {
    return this.http.post<Workout>(`${this.url}/start`, { kind });
  }

  stop(id: number): Observable<Workout> {
    return this.http.post<Workout>(`${this.url}/${id}/stop`, {});
  }

  list(filters: WorkoutFilters = {}): Observable<WorkoutPage> {
    let params = new HttpParams();
    if (filters.from) params = params.set('from', filters.from);
    if (filters.to) params = params.set('to', filters.to);
    if (filters.kind) params = params.set('kind', filters.kind);
    if (filters.limit !== undefined) params = params.set('limit', filters.limit);
    if (filters.offset !== undefined) params = params.set('offset', filters.offset);
    return this.http.get<WorkoutPage>(this.url, { params });
  }

  get(id: number): Observable<Workout> {
    return this.http.get<Workout>(`${this.url}/${id}`);
  }
}
