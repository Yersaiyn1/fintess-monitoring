import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { DashboardDataService } from '../../core/services/dashboard-data.service';
import { WorkoutTrackerService } from '../../core/services/workout-tracker.service';
import { DeviceRecord, SyncApiService } from '../../core/services/api/sync-api.service';
import { formatClock, formatDuration } from '../../core/utils/format';
import { StatCard } from '../../shared/stat-card/stat-card';
import { UserPreferencesService } from '../../core/services/user-preferences.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';

@Component({
  selector: 'app-activity',
  imports: [DecimalPipe, FormsModule, RouterLink, StatCard, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './activity.html',
  styleUrl: './activity.scss',
})
export class Activity {
  protected readonly tracker = inject(WorkoutTrackerService);
  private readonly dashboard = inject(DashboardDataService);
  private readonly syncApi = inject(SyncApiService);
  protected readonly preferences = inject(UserPreferencesService);

  protected readonly cards = this.dashboard.activityCards;
  protected readonly recent = this.dashboard.recentWorkouts;
  protected readonly clock = computed(() => formatClock(this.tracker.elapsedSec()));
  protected readonly formatDuration = formatDuration;
  protected readonly devices = signal<DeviceRecord[]>([]);
  protected selectedDeviceId = 0;
  protected model = '';
  protected serialNumber = '';
  protected heartRate: number | null = null;
  protected steps: number | null = null;
  protected calories: number | null = null;
  protected bloodPressure = '';
  protected syncMessage = '';
  protected syncError = '';
  protected readonly enteringReading = signal(false);
  protected readonly savingReading = signal(false);

  constructor() {
    void this.tracker.init();
    void this.dashboard.load();
    void this.loadDevices();
  }

  protected async loadDevices(): Promise<void> {
    try {
      const devices = await firstValueFrom(this.syncApi.devices());
      this.devices.set(devices);
      this.selectedDeviceId = devices[0]?.device_id ?? 0;
    } catch {
      this.devices.set([]);
    }
  }

  protected async addDevice(): Promise<void> {
    this.syncError = '';
    this.syncMessage = '';
    try {
      const device = await firstValueFrom(this.syncApi.addDevice(this.model, this.serialNumber));
      await this.loadDevices();
      this.selectedDeviceId = device.device_id;
      this.model = '';
      this.serialNumber = '';
      this.syncMessage = 'Device saved.';
    } catch {
      this.syncError = 'Could not save the device.';
    }
  }

  protected cancelReading(): void {
    this.resetReading();
    this.syncError = '';
    this.syncMessage = '';
  }

  private resetReading(): void {
    this.heartRate = null;
    this.steps = null;
    this.calories = null;
    this.bloodPressure = '';
    this.enteringReading.set(false);
  }

  protected async saveReading(): Promise<void> {
    if (this.savingReading()) return;
    this.syncError = '';
    this.syncMessage = '';
    if (!this.selectedDeviceId) {
      this.syncError = 'Add or select a device first.';
      return;
    }
    this.savingReading.set(true);
    try {
      await firstValueFrom(this.syncApi.createReading({
        device_id: this.selectedDeviceId,
        date_time: new Date().toISOString(),
        heart_rate_bpm: this.heartRate,
        steps: this.steps,
        calories_kcal: this.calories,
        blood_pressure: this.bloodPressure || null,
      }));
      this.resetReading();
      this.syncMessage = 'Reading saved.';
      await this.dashboard.load();
    } catch {
      this.syncError = 'Could not save the reading.';
    } finally {
      this.savingReading.set(false);
    }
  }
}
