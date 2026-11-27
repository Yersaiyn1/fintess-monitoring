import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { DashboardDataService } from '../../core/services/dashboard-data.service';
import { AnalyticsApiService } from '../../core/services/api/analytics-api.service';
import { Analytics } from '../../core/models/workout.model';
import { ProgressRing } from '../../shared/progress-ring/progress-ring';
import { TranslatePipe } from '../../core/i18n/translate.pipe';

interface Goal { id: string; label: string; unit: string; target: number }
const GOALS_KEY = 'pulse.goals';
const DEFAULT_GOALS: Goal[] = [
  { id: 'steps', label: 'Daily steps', unit: 'steps', target: 10000 },
  { id: 'workouts', label: 'Weekly workouts', unit: 'workouts', target: 4 },
  { id: 'minutes', label: 'Weekly active minutes', unit: 'minutes', target: 150 },
];

@Component({
  selector: 'app-goals',
  imports: [DecimalPipe, FormsModule, ProgressRing, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './goals.html',
  styleUrl: './goals.scss',
})
export class Goals {
  private readonly dashboard = inject(DashboardDataService);
  private readonly analyticsApi = inject(AnalyticsApiService);
  protected readonly goals = signal<Goal[]>(this.loadGoals());
  protected readonly analytics = signal<Analytics | null>(null);
  protected readonly week = this.dashboard.week;
  protected readonly todaySteps = this.dashboard.today;
  protected readonly dashboardError = this.dashboard.error;
  protected readonly weeklyMinutes = computed(() => this.analytics()?.totals.durationMin ?? 0);
  protected readonly weeklyWorkouts = computed(() => this.analytics()?.totals.workouts ?? 0);
  protected busy = signal(true);
  protected analyticsFailed = signal(false);
  protected saved = false;

  constructor() {
    this.dashboard.setDailyStepGoal(this.goals()[0].target);
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

  protected save(): void {
    try { localStorage.setItem(GOALS_KEY, JSON.stringify(this.goals())); } catch { /* storage unavailable */ }
    this.dashboard.setDailyStepGoal(this.goals()[0].target);
    this.saved = true;
  }

  private async loadAnalytics(): Promise<void> {
    try { this.analytics.set(await firstValueFrom(this.analyticsApi.workouts('week'))); }
    catch { this.analyticsFailed.set(true); }
    finally { this.busy.set(false); }
  }

  private loadGoals(): Goal[] {
    try {
      const stored: unknown = JSON.parse(localStorage.getItem(GOALS_KEY) ?? 'null');
      if (Array.isArray(stored) && stored.length === DEFAULT_GOALS.length) {
        return DEFAULT_GOALS.map((fallback) => {
          const item = stored.find((candidate: unknown) => !!candidate && typeof candidate === 'object' && (candidate as Goal).id === fallback.id) as Partial<Goal> | undefined;
          return { ...fallback, target: Number.isFinite(item?.target) && Number(item?.target) > 0 ? Number(item?.target) : fallback.target };
        });
      }
    } catch { /* use defaults */ }
    return DEFAULT_GOALS.map((goal) => ({ ...goal }));
  }
}
