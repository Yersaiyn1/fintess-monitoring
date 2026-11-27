import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { describeHttpError } from '../../core/http/error-message';
import { DashboardDataService } from '../../core/services/dashboard-data.service';
import { AnalyticsApiService } from '../../core/services/api/analytics-api.service';
import { GoalsApiService } from '../../core/services/api/goals-api.service';
import { Analytics } from '../../core/models/workout.model';
import { ProgressRing } from '../../shared/progress-ring/progress-ring';

interface Goal { id: string; label: string; unit: string; target: number }
const GOALS_KEY = 'pulse.goals';
const MIN_STEPS_DAILY = 1000;
const MAX_STEPS_DAILY = 100000;
const MIN_WORKOUTS_WEEKLY = 0;
const MAX_WORKOUTS_WEEKLY = 14;
const DEFAULT_GOALS: Goal[] = [
  { id: 'steps', label: 'Daily steps', unit: 'steps', target: 10000 },
  { id: 'workouts', label: 'Weekly workouts', unit: 'workouts', target: 3 },
  { id: 'minutes', label: 'Weekly active minutes', unit: 'minutes', target: 150 },
];

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(Math.round(value), min), max);
}

@Component({
  selector: 'app-goals',
  imports: [DecimalPipe, FormsModule, ProgressRing],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './goals.html',
  styleUrl: './goals.scss',
})
export class Goals {
  private readonly dashboard = inject(DashboardDataService);
  private readonly analyticsApi = inject(AnalyticsApiService);
  private readonly goalsApi = inject(GoalsApiService);
  protected readonly goals = signal<Goal[]>(DEFAULT_GOALS.map((goal) => ({ ...goal })));
  protected readonly analytics = signal<Analytics | null>(null);
  protected readonly week = this.dashboard.week;
  protected readonly todaySteps = this.dashboard.today;
  protected readonly dashboardError = this.dashboard.error;
  protected readonly weeklyMinutes = computed(() => this.analytics()?.totals.durationMin ?? 0);
  protected readonly weeklyWorkouts = computed(() => this.analytics()?.totals.workouts ?? 0);
  protected busy = signal(true);
  protected analyticsFailed = signal(false);
  protected saving = signal(false);
  protected saveError = signal('');
  protected saved = signal(false);

  constructor() {
    void this.initGoals();
    void this.dashboard.load();
    void this.loadAnalytics();
  }

  protected current(goal: Goal): number {
    if (goal.id === 'steps') return this.todaySteps().steps;
    if (goal.id === 'workouts') return this.weeklyWorkouts();
    return this.weeklyMinutes();
  }

  protected percent(goal: Goal): number {
    return Math.min(Math.round((this.current(goal) / Math.max(goal.target, 1)) * 100), 100);
  }

  protected remainingToday(): number {
    return Math.max(this.goals()[0].target - this.todaySteps().steps, 0);
  }

  protected barHeight(steps: number): number {
    const target = Math.max(this.goals()[0].target, 1);
    return Math.max(Math.min((steps / target) * 100, 100), steps > 0 ? 5 : 0);
  }

  protected async save(): Promise<void> {
    this.saved.set(false);
    this.saveError.set('');
    const currentGoals = this.goals();
    const steps = Math.round(Number(currentGoals[0].target));
    const workouts = Math.round(Number(currentGoals[1].target));
    if (!Number.isFinite(steps) || steps < MIN_STEPS_DAILY || steps > MAX_STEPS_DAILY) {
      this.saveError.set(`Daily steps target must be between ${MIN_STEPS_DAILY} and ${MAX_STEPS_DAILY}.`);
      return;
    }
    if (!Number.isFinite(workouts) || workouts < MIN_WORKOUTS_WEEKLY || workouts > MAX_WORKOUTS_WEEKLY) {
      this.saveError.set(`Weekly workouts target must be between ${MIN_WORKOUTS_WEEKLY} and ${MAX_WORKOUTS_WEEKLY}.`);
      return;
    }

    this.saving.set(true);
    try {
      const updated = await firstValueFrom(
        this.goalsApi.updateGoals({ steps_daily: steps, workouts_weekly: workouts }),
      );
      this.applyServerGoals(updated.steps_daily, updated.workouts_weekly);
      this.saved.set(true);
    } catch (err) {
      this.saveError.set(describeHttpError(err, 'Could not save goals.'));
    } finally {
      this.saving.set(false);
    }
  }

  private async initGoals(): Promise<void> {
    const legacy = this.readLegacyLocalGoals();
    try {
      if (legacy !== null) {
        const migrated = await firstValueFrom(this.goalsApi.updateGoals(legacy));
        this.applyServerGoals(migrated.steps_daily, migrated.workouts_weekly);
        try { localStorage.removeItem(GOALS_KEY); } catch { /* storage unavailable */ }
      } else {
        const remote = await firstValueFrom(this.goalsApi.getGoals());
        this.applyServerGoals(remote.steps_daily, remote.workouts_weekly);
      }
    } catch {
      if (legacy !== null) {
        this.applyServerGoals(legacy.steps_daily, legacy.workouts_weekly);
      }
    }
  }

  private applyServerGoals(stepsDaily: number, workoutsWeekly: number): void {
    this.goals.update((items) =>
      items.map((g) => {
        if (g.id === 'steps') return { ...g, target: stepsDaily };
        if (g.id === 'workouts') return { ...g, target: workoutsWeekly };
        return g;
      }),
    );
    this.dashboard.setDailyStepGoal(stepsDaily);
  }

  private readLegacyLocalGoals(): { steps_daily: number; workouts_weekly: number } | null {
    try {
      const raw = localStorage.getItem(GOALS_KEY);
      if (!raw) return null;
      const stored: unknown = JSON.parse(raw);
      if (!Array.isArray(stored)) return null;
      const stepsEntry = stored.find((c) => !!c && typeof c === 'object' && (c as Goal).id === 'steps') as Partial<Goal> | undefined;
      const workoutsEntry = stored.find((c) => !!c && typeof c === 'object' && (c as Goal).id === 'workouts') as Partial<Goal> | undefined;
      const stepsRaw = Number(stepsEntry?.target);
      const workoutsRaw = Number(workoutsEntry?.target);
      return {
        steps_daily: Number.isFinite(stepsRaw) && stepsRaw > 0 ? clamp(stepsRaw, MIN_STEPS_DAILY, MAX_STEPS_DAILY) : 10000,
        workouts_weekly: Number.isFinite(workoutsRaw) && workoutsRaw >= 0 ? clamp(workoutsRaw, MIN_WORKOUTS_WEEKLY, MAX_WORKOUTS_WEEKLY) : 3,
      };
    } catch {
      return null;
    }
  }

  private async loadAnalytics(): Promise<void> {
    try { this.analytics.set(await firstValueFrom(this.analyticsApi.workouts('week'))); }
    catch { this.analyticsFailed.set(true); }
    finally { this.busy.set(false); }
  }
}
