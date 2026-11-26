import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { describeHttpError } from '../../core/http/error-message';
import {
  DeviceProvider,
  DeviceRecord,
  SyncApiService,
} from '../../core/services/api/sync-api.service';
import { ConnectDevice } from '../devices/connect-device/connect-device';

@Component({
  selector: 'app-settings',
  imports: [DatePipe, ReactiveFormsModule, ConnectDevice],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './settings.html',
  styleUrl: './settings.scss',
})
export class Settings {
  private readonly syncApi = inject(SyncApiService);
  private readonly fb = inject(NonNullableFormBuilder);

  protected readonly devices = signal<DeviceRecord[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly saving = signal(false);
  protected readonly formError = signal('');

  protected readonly providers: { value: DeviceProvider; label: string }[] = [
    { value: 'manual', label: 'Manual' },
    { value: 'health_connect', label: 'Health Connect' },
    { value: 'fitbit', label: 'Fitbit' },
    { value: 'garmin', label: 'Garmin' },
    { value: 'bluetooth', label: 'Bluetooth' },
    { value: 'demo', label: 'Demo' },
  ];

  protected readonly form = this.fb.group({
    model: ['', [Validators.required, Validators.maxLength(255)]],
    serial_number: ['', [Validators.required, Validators.maxLength(255)]],
    provider: ['manual' as DeviceProvider],
  });

  constructor() {
    void this.loadDevices();
  }

  protected async loadDevices(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const items = await firstValueFrom(this.syncApi.listDevices());
      this.devices.set(items);
    } catch (err) {
      this.error.set(describeHttpError(err, 'Could not load your devices. Please try again.'));
    } finally {
      this.loading.set(false);
    }
  }

  protected async addDevice(): Promise<void> {
    if (this.form.invalid || this.saving()) {
      this.form.markAllAsTouched();
      return;
    }

    const raw = this.form.getRawValue();
    this.saving.set(true);
    this.formError.set('');
    try {
      const created = await firstValueFrom(
        this.syncApi.createDevice({
          model: raw.model.trim(),
          serial_number: raw.serial_number.trim(),
          provider: raw.provider,
        }),
      );
      this.devices.update((list) => [...list, created]);
      this.form.reset({ model: '', serial_number: '', provider: 'manual' });
    } catch (err) {
      this.formError.set(describeHttpError(err, 'Could not register the device.'));
    } finally {
      this.saving.set(false);
    }
  }
}
