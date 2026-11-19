import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import {
  GoalMetric,
  GoalPeriod,
  GoalProgress,
  GoalsApiService,
  HealthAlerts,
} from '../../core/services/api/goals-api.service';
import { ProgressRing } from '../../shared/progress-ring/progress-ring';

const METRIC_LABELS: Record<GoalMetric, string> = {
  steps: 'Steps',
  calories_kcal: 'Calories (kcal)',
  distance_km: 'Distance (km)',
  active_minutes: 'Active minutes',
  workouts: 'Workouts',
};

@Component({
  selector: 'app-goals',
  imports: [DecimalPipe, FormsModule, ProgressRing],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './goals.html',
  styleUrl: './goals.scss',
})
export class Goals {
  private readonly goalsApi = inject(GoalsApiService);

  protected readonly goals = signal<GoalProgress[]>([]);
  protected readonly alerts = signal<HealthAlerts | null>(null);
  protected readonly busy = signal(false);
  protected readonly message = signal('');
  protected readonly error = signal('');

  protected period: GoalPeriod = 'daily';
  protected metric: GoalMetric = 'steps';
  protected targetValue = 8000;

  protected readonly metricOptions: { value: GoalMetric; label: string }[] = [
    { value: 'steps', label: 'Steps' },
    { value: 'calories_kcal', label: 'Calories (kcal)' },
    { value: 'distance_km', label: 'Distance (km)' },
    { value: 'active_minutes', label: 'Active minutes' },
    { value: 'workouts', label: 'Workouts' },
  ];

  constructor() {
    void this.load();
  }

  protected metricLabel(metric: GoalMetric): string {
    return METRIC_LABELS[metric] ?? metric;
  }

  protected async load(): Promise<void> {
    try {
      const data = await firstValueFrom(this.goalsApi.summary());
      this.goals.set(data.goals);
      this.alerts.set(data.alerts);
    } catch {
      this.error.set('Could not load goals and health alerts.');
    }
  }

  protected async saveGoal(): Promise<void> {
    this.error.set('');
    this.message.set('');
    if (!this.targetValue || this.targetValue <= 0) {
      this.error.set('Target value must be positive.');
      return;
    }
    this.busy.set(true);
    try {
      await firstValueFrom(
        this.goalsApi.upsertGoal(this.period, this.metric, this.targetValue),
      );
      await this.load();
      this.message.set('Goal saved.');
    } catch {
      this.error.set('Could not save goal.');
    } finally {
      this.busy.set(false);
    }
  }

  protected async deleteGoal(goalId: number): Promise<void> {
    this.error.set('');
    this.message.set('');
    this.busy.set(true);
    try {
      await firstValueFrom(this.goalsApi.deleteGoal(goalId));
      await this.load();
      this.message.set('Goal deleted.');
    } catch {
      this.error.set('Could not delete goal.');
    } finally {
      this.busy.set(false);
    }
  }
}
