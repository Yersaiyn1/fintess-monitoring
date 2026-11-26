import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { HrSample, HR_HISTORY_WINDOW_MS } from '../../core/services/batch-sender';

interface ChartGeometry {
  polyline: string;
  areaPath: string;
  lastX: number;
  lastY: number;
  minLabel: number;
  midLabel: number;
  maxLabel: number;
}

const WIDTH = 600;
const HEIGHT = 180;
const PAD_X = 36;
const PAD_TOP = 14;
const PAD_BOTTOM = 22;

@Component({
  selector: 'app-hr-chart',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './hr-chart.html',
  styleUrl: './hr-chart.scss',
})
export class HrChart {
  readonly samples = input.required<HrSample[]>();
  readonly title = input('Live heart rate (last 2 min)');
  readonly sourceLabel = input('');

  protected readonly viewWidth = WIDTH;
  protected readonly viewHeight = HEIGHT;
  protected readonly padX = PAD_X;
  protected readonly topY = PAD_TOP;
  protected readonly midY = Math.round((PAD_TOP + (HEIGHT - PAD_BOTTOM)) / 2);
  protected readonly bottomY = HEIGHT - PAD_BOTTOM;

  protected readonly latestBpm = computed(() => {
    const items = this.samples();
    return items.length ? items[items.length - 1].bpm : null;
  });

  protected readonly geometry = computed<ChartGeometry | null>(() => {
    const items = this.samples();
    if (items.length === 0) return null;

    const endMs = items[items.length - 1].timeMs;
    const startMs = endMs - HR_HISTORY_WINDOW_MS;

    const bpms = items.map((s) => s.bpm);
    const rawMin = Math.min(...bpms);
    const rawMax = Math.max(...bpms);
    const yMin = Math.max(30, Math.floor((rawMin - 8) / 5) * 5);
    const yMax = Math.min(220, Math.max(yMin + 20, Math.ceil((rawMax + 8) / 5) * 5));

    const plotW = WIDTH - PAD_X - 12;
    const plotH = HEIGHT - PAD_TOP - PAD_BOTTOM;

    const points = items.map((sample) => {
      const ratioX = Math.max(0, Math.min(1, (sample.timeMs - startMs) / HR_HISTORY_WINDOW_MS));
      const ratioY = (sample.bpm - yMin) / (yMax - yMin);
      const x = Number((PAD_X + ratioX * plotW).toFixed(1));
      const y = Number((PAD_TOP + (1 - ratioY) * plotH).toFixed(1));
      return { x, y };
    });

    const polyline = points.map((p) => `${p.x},${p.y}`).join(' ');
    const first = points[0];
    const last = points[points.length - 1];
    const baselineY = HEIGHT - PAD_BOTTOM;
    const areaPath =
      points.length > 1
        ? `M ${first.x},${baselineY} L ${points.map((p) => `${p.x},${p.y}`).join(' L ')} L ${last.x},${baselineY} Z`
        : '';

    return {
      polyline,
      areaPath,
      lastX: last.x,
      lastY: last.y,
      minLabel: yMin,
      midLabel: Math.round((yMin + yMax) / 2),
      maxLabel: yMax,
    };
  });

  protected readonly ariaLabel = computed(() => {
    const latest = this.latestBpm();
    const count = this.samples().length;
    if (latest === null) return `${this.title()}: no heart rate samples yet`;
    return `${this.title()}: ${count} samples, latest ${latest} bpm`;
  });
}
