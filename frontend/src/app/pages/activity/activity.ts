import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { DashboardDataService } from '../../core/services/dashboard-data.service';
import { WorkoutTrackerService } from '../../core/services/workout-tracker.service';
import { formatClock, formatDuration } from '../../core/utils/format';
import { StatCard } from '../../shared/stat-card/stat-card';

@Component({
  selector: 'app-activity',
  imports: [DecimalPipe, StatCard],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './activity.html',
  styleUrl: './activity.scss',
})
export class Activity {
  protected readonly tracker = inject(WorkoutTrackerService);
  private readonly dashboard = inject(DashboardDataService);

  protected readonly cards = this.dashboard.activityCards;
  protected readonly recent = this.dashboard.recentWorkouts;
  protected readonly clock = computed(() => formatClock(this.tracker.elapsedSec()));
  protected readonly formatDuration = formatDuration;

  constructor() {
    void this.tracker.init();
    void this.dashboard.load();
  }
}
