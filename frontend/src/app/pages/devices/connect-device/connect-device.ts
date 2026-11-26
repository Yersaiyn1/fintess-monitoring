import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, output, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { BluetoothHrService } from '../../../core/services/bluetooth-hr.service';
import { DemoWatchService } from '../../../core/services/demo-watch.service';
import { HrChart } from '../../../shared/hr-chart/hr-chart';
import { Icon } from '../../../shared/icon/icon';

type ChartSource = 'bluetooth' | 'demo';

/**
 * "Connect a device" panel with Web Bluetooth Heart Rate, Demo watch simulator,
 * and a shortcut to the Dashboard Health Connect import.
 *
 * Connections are intentionally NOT torn down in ngOnDestroy so streaming continues
 * when the user switches to the Dashboard to inspect live readings.
 */
@Component({
  selector: 'app-connect-device',
  imports: [DatePipe, RouterLink, HrChart, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './connect-device.html',
  styleUrl: './connect-device.scss',
})
export class ConnectDevice {
  protected readonly bt = inject(BluetoothHrService);
  protected readonly demo = inject(DemoWatchService);

  readonly deviceConnected = output<void>();

  protected readonly selectedSource = signal<ChartSource | null>(null);

  protected readonly btStatusLabel = computed(() => {
    switch (this.bt.status()) {
      case 'connecting':
        return 'Connecting…';
      case 'connected':
        return this.bt.deviceName() ? `Connected · ${this.bt.deviceName()}` : 'Connected';
      case 'reconnecting':
        return 'Reconnecting…';
      case 'error':
        return 'Disconnected';
      default:
        return this.bt.supported ? 'Ready to pair' : 'Unsupported browser';
    }
  });

  protected readonly demoStatusLabel = computed(() => {
    switch (this.demo.status()) {
      case 'starting':
        return 'Starting…';
      case 'running':
        return this.demo.highHrActive() ? 'Streaming · High HR mode' : 'Streaming';
      case 'error':
        return 'Error';
      default:
        return 'Idle';
    }
  });

  protected readonly showSourceToggle = computed(
    () => this.bt.history().length > 0 && this.demo.history().length > 0,
  );

  protected readonly activeChartSource = computed<ChartSource>(() => {
    const manual = this.selectedSource();
    if (manual) return manual;
    if (this.bt.status() === 'connected' || this.bt.status() === 'reconnecting') {
      return 'bluetooth';
    }
    if (this.demo.status() === 'running') return 'demo';
    if (this.bt.history().length > 0) return 'bluetooth';
    return 'demo';
  });

  protected readonly activeSamples = computed(() =>
    this.activeChartSource() === 'bluetooth' ? this.bt.history() : this.demo.history(),
  );

  protected readonly activeChartLabel = computed(() =>
    this.activeChartSource() === 'bluetooth'
      ? this.bt.deviceName() || 'Bluetooth Heart Rate'
      : 'Demo Watch',
  );

  protected async connectBluetooth(): Promise<void> {
    await this.bt.connect();
    if (this.bt.status() === 'connected') {
      this.selectedSource.set('bluetooth');
      this.deviceConnected.emit();
    }
  }

  protected async reconnectBluetooth(): Promise<void> {
    await this.bt.reconnect();
    if (this.bt.status() === 'connected') {
      this.selectedSource.set('bluetooth');
    }
  }

  protected async disconnectBluetooth(): Promise<void> {
    await this.bt.disconnect();
  }

  protected async startDemo(): Promise<void> {
    await this.demo.start();
    if (this.demo.status() === 'running') {
      this.selectedSource.set('demo');
      this.deviceConnected.emit();
    }
  }

  protected async stopDemo(): Promise<void> {
    await this.demo.stop();
  }

  protected simulateHighHr(): void {
    this.demo.simulateHighHr();
  }

  protected pickChartSource(source: ChartSource): void {
    this.selectedSource.set(source);
  }
}
