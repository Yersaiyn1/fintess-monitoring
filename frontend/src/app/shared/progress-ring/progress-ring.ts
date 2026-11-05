import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

@Component({
  selector: 'app-progress-ring',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './progress-ring.html',
  styleUrl: './progress-ring.scss',
})
export class ProgressRing {
  /** Value from 0 to 1 */
  readonly progress = input.required<number>();
  readonly size = input(220);
  readonly stroke = input(16);
  readonly label = input('Progress');

  protected readonly radius = computed(() => (this.size() - this.stroke()) / 2);
  protected readonly circumference = computed(() => 2 * Math.PI * this.radius());
  protected readonly offset = computed(
    () => this.circumference() * (1 - Math.min(Math.max(this.progress(), 0), 1)),
  );
  protected readonly percent = computed(() => Math.round(this.progress() * 100));
}
