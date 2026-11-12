import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { describeHttpError } from '../../core/http/error-message';
import { Workout } from '../../core/models/workout.model';
import { WorkoutsApiService } from '../../core/services/api/workouts-api.service';
import { formatDuration, formatFullDate, formatTime } from '../../core/utils/format';

/** One workout in detail (route /history/:id, the id is bound to the `id` input by the router). */
@Component({
  selector: 'app-workout-details',
  imports: [RouterLink, DecimalPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './workout-details.html',
  styleUrl: './workout-details.scss',
})
export class WorkoutDetails implements OnInit {
  private readonly api = inject(WorkoutsApiService);

  readonly id = input.required<string>();

  protected readonly workout = signal<Workout | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal('');

  protected readonly formatDuration = formatDuration;
  protected readonly formatFullDate = formatFullDate;
  protected readonly formatTime = formatTime;

  /** Average speed in km/h (only when the workout has a distance) */
  protected readonly speed = computed(() => {
    const w = this.workout();
    return w?.durationSec && w.distanceKm > 0 ? w.distanceKm / (w.durationSec / 3600) : null;
  });

  /** Average pace as "5:30" min per km */
  protected readonly pace = computed(() => {
    const w = this.workout();
    if (!w?.durationSec || w.distanceKm <= 0) return null;
    const secPerKm = w.durationSec / w.distanceKm;
    return `${Math.floor(secPerKm / 60)}:${String(Math.round(secPerKm % 60) % 60).padStart(2, '0')}`;
  });

  protected readonly kcalPerMin = computed(() => {
    const w = this.workout();
    return w?.durationSec ? w.caloriesKcal / (w.durationSec / 60) : null;
  });

  async ngOnInit(): Promise<void> {
    const id = Number(this.id());
    if (!Number.isInteger(id) || id < 1) {
      this.error.set('Workout not found.');
      this.loading.set(false);
      return;
    }
    try {
      this.workout.set(await firstValueFrom(this.api.get(id)));
    } catch (e) {
      this.error.set(describeHttpError(e, 'Could not load this workout. Please try again.'));
    } finally {
      this.loading.set(false);
    }
  }
}
