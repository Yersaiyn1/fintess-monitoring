import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { DecimalPipe } from '@angular/common';

export interface ChartBar {
  label: string;
  value: number;
  isToday?: boolean;
}

@Component({
  selector: 'app-bar-chart',
  imports: [DecimalPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './bar-chart.html',
  styleUrl: './bar-chart.scss',
})
export class BarChart {
  readonly bars = input.required<ChartBar[]>();
  /** Optional goal line, in the same unit as the bars */
  readonly goal = input<number | null>(null);
  readonly unit = input('');
  readonly decimals = input(0);

  /** Axis maximum chosen so that all 4 grid steps are "nice" numbers. */
  protected readonly axisMax = computed(() => {
    const raw = Math.max(...this.bars().map((b) => b.value), this.goal() ?? 0, 1);
    const magnitude = Math.pow(10, Math.floor(Math.log10(raw / 4)));
    const step = [1, 1.5, 2, 2.5, 3, 4, 5, 10]
      .map((m) => m * magnitude)
      .find((s) => s * 4 >= raw * 1.02)!;
    return step * 4;
  });

  protected readonly ticks = computed(() =>
    [1, 0.75, 0.5, 0.25, 0].map((f) => f * this.axisMax()),
  );

  protected readonly view = computed(() =>
    this.bars().map((b) => ({ ...b, height: (b.value / this.axisMax()) * 100 })),
  );

  protected readonly goalBottom = computed(() =>
    this.goal() ? (this.goal()! / this.axisMax()) * 100 : null,
  );

  protected readonly digits = computed(() => `1.${this.decimals()}-${this.decimals()}`);
}
