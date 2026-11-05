import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { StatCardData } from '../../core/models/stat.model';
import { Icon } from '../icon/icon';

@Component({
  selector: 'app-stat-card',
  imports: [Icon, DecimalPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './stat-card.html',
  styleUrl: './stat-card.scss',
})
export class StatCard {
  readonly data = input.required<StatCardData>();

  protected readonly digits = computed(() => `1.${this.data().decimals}-${this.data().decimals}`);
  protected readonly trend = computed(() => {
    const c = this.data().change;
    return c > 0 ? 'up' : c < 0 ? 'down' : 'flat';
  });
}
