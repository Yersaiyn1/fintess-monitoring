import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { describeHttpError } from '../http/error-message';
import { ActivityType, Workout, WorkoutKind } from '../models/workout.model';
import { WorkoutsApiService } from './api/workouts-api.service';
import { AuthService } from './auth.service';
import { DashboardDataService } from './dashboard-data.service';

/**
 * State of the Activity page (Phase 2): selected activity type, the workout in progress and its timer.
 *
 * The workout lives in the database, so the timer survives a page refresh (or closing the browser):
 * elapsed time = now - startedAt, where startedAt comes from the server.
 * The numbers shown while running are ESTIMATES from the per-minute rates sent by the backend;
 * the final saved numbers are calculated by the backend when the workout is stopped.
 */
@Injectable({ providedIn: 'root' })
export class WorkoutTrackerService {
  private readonly api = inject(WorkoutsApiService);
  private readonly auth = inject(AuthService);
  private readonly dashboard = inject(DashboardDataService);

  readonly types = signal<ActivityType[]>([]);
  readonly selectedKind = signal<WorkoutKind>('Run');
  readonly active = signal<Workout | null>(null);
  /** The workout that was just stopped (shown as a summary until the next start). */
  readonly lastResult = signal<Workout | null>(null);
  readonly ready = signal(false);
  readonly busy = signal(false);
  readonly error = signal('');

  private readonly now = signal(Date.now());
  private timer: ReturnType<typeof setInterval> | null = null;

  readonly isRunning = computed(() => this.active() !== null);

  /** Seconds since the workout started (never negative, even if the PC clock is a bit off). */
  readonly elapsedSec = computed(() => {
    const a = this.active();
    return a ? Math.max(0, Math.floor((this.now() - Date.parse(a.startedAt)) / 1000)) : 0;
  });

  /** Estimated steps / km / kcal for the elapsed time, using the rates from the backend. */
  readonly live = computed(() => {
    const kind = this.active()?.kind ?? this.selectedKind();
    const rates = this.types().find((t) => t.kind === kind);
    const minutes = this.elapsedSec() / 60;
    if (!rates) return { steps: 0, km: 0, kcal: 0 };
    return {
      steps: Math.round(rates.stepsPerMin * minutes),
      km: Math.round(rates.kmPerMin * minutes * 100) / 100,
      kcal: Math.round(rates.kcalPerMin * minutes * 10) / 10,
    };
  });

  constructor() {
    // Logged out (or another user): forget everything and stop the timer.
    effect(() => {
      if (!this.auth.isLoggedIn()) untracked(() => this.reset());
    });
  }

  /** Call when the Activity page opens. */
  async init(): Promise<void> {
    this.error.set('');
    try {
      const [types, active] = await Promise.all([
        this.types().length ? Promise.resolve(this.types()) : firstValueFrom(this.api.types()),
        firstValueFrom(this.api.active()),
      ]);
      this.types.set(types);
      this.active.set(active);
      if (active) this.selectedKind.set(active.kind);
      this.syncTimer();
      this.ready.set(true);
    } catch (e) {
      this.error.set(describeHttpError(e, 'Could not load the workout tracker. Please try again.'));
    }
  }

  select(kind: WorkoutKind): void {
    if (!this.isRunning()) this.selectedKind.set(kind);
  }

  async start(): Promise<void> {
    if (this.busy() || this.isRunning()) return;
    this.busy.set(true);
    this.error.set('');
    try {
      const workout = await firstValueFrom(this.api.start(this.selectedKind()));
      this.lastResult.set(null);
      this.active.set(workout);
      this.syncTimer();
    } catch (e) {
      const message = describeHttpError(e, 'Could not start the workout.');
      await this.init(); // e.g. "already in progress" -> show the real state (init() clears the error)
      this.error.set(message);
    } finally {
      this.busy.set(false);
    }
  }

  async stop(): Promise<void> {
    const current = this.active();
    if (this.busy() || !current) return;
    this.busy.set(true);
    this.error.set('');
    try {
      const finished = await firstValueFrom(this.api.stop(current.id));
      this.active.set(null);
      this.lastResult.set(finished);
      this.syncTimer();
      await this.dashboard.load(); // dashboard numbers include the new workout straight away
    } catch (e) {
      this.error.set(describeHttpError(e, 'Could not stop the workout.'));
    } finally {
      this.busy.set(false);
    }
  }

  private syncTimer(): void {
    if (this.isRunning()) {
      this.now.set(Date.now());
      this.timer ??= setInterval(() => this.now.set(Date.now()), 1000);
    } else if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  private reset(): void {
    this.active.set(null);
    this.lastResult.set(null);
    this.types.set([]);
    this.ready.set(false);
    this.error.set('');
    this.syncTimer();
  }
}
