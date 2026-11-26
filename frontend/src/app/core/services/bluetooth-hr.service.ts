import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { describeHttpError } from '../http/error-message';
import { SyncApiService } from './api/sync-api.service';
import { AuthService } from './auth.service';
import {
  BatchSender,
  DashboardRefreshThrottler,
  HR_MAX,
  HR_MIN,
  HrSample,
  appendHrSample,
} from './batch-sender';

export type BluetoothConnectionStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'error';

export const RECONNECT_DELAYS_MS = [1_000, 2_000, 4_000, 8_000, 16_000] as const;

/**
 * Parses a BLE Heart Rate Measurement (0x2A37) characteristic payload per GATT spec.
 * Bit 0 of flags (byte 0): 0 = uint8 BPM at byte 1, 1 = little-endian uint16 BPM at bytes 1..2.
 * Returns null if the packet is malformed or outside [30, 220] (e.g. 0 = no skin contact).
 */
export function parseHeartRateMeasurement(value: DataView): number | null {
  if (value.byteLength < 2) return null;
  const flags = value.getUint8(0);
  const isUint16 = (flags & 0x01) !== 0;

  let bpm: number;
  if (isUint16) {
    if (value.byteLength < 3) return null;
    bpm = value.getUint16(1, true);
  } else {
    bpm = value.getUint8(1);
  }

  if (bpm < HR_MIN || bpm > HR_MAX) return null;
  return bpm;
}

/**
 * Manages Web Bluetooth Heart Rate connections, packet parsing, buffered batching,
 * and automatic exponential-backoff reconnection on GATT disconnects.
 */
@Injectable({ providedIn: 'root' })
export class BluetoothHrService {
  private readonly syncApi = inject(SyncApiService);
  private readonly auth = inject(AuthService);
  private readonly refreshThrottler = inject(DashboardRefreshThrottler);

  readonly status = signal<BluetoothConnectionStatus>('idle');
  readonly bpm = signal<number | null>(null);
  readonly error = signal('');
  readonly lastSentAt = signal<Date | null>(null);
  readonly deviceName = signal('');
  readonly deviceId = signal<number | null>(null);
  readonly history = signal<HrSample[]>([]);

  readonly canReconnect = computed(
    () => this.status() === 'error' && this.gattDevice !== null && this.deviceId() !== null,
  );

  private readonly batchSender = new BatchSender(this.syncApi, {
    onSent: (at) => this.lastSentAt.set(at),
    onRefresh: () => this.refreshThrottler.requestRefresh(),
    onError: (err) => {
      this.error.set(
        describeHttpError(err, 'Failed to upload readings. Buffered locally for retry.'),
      );
    },
  });

  private gattDevice: BluetoothDevice | null = null;
  private hrCharacteristic: BluetoothRemoteGATTCharacteristic | null = null;
  private manualDisconnect = false;
  private reconnectGeneration = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  private readonly onCharacteristicValueChanged = (event: Event): void => {
    const target = event.target as BluetoothRemoteGATTCharacteristic | null;
    const value = target?.value;
    if (!value) return;

    const bpm = parseHeartRateMeasurement(value);
    if (bpm === null) return;

    const nowMs = Date.now();
    this.bpm.set(bpm);
    this.history.update((items) => appendHrSample(items, bpm, nowMs));
    this.batchSender.enqueue({ timestampMs: nowMs, heart_rate_bpm: bpm });
  };

  private readonly onGattServerDisconnected = (): void => {
    if (this.manualDisconnect) return;
    void this.attemptReconnectLoop();
  };

  constructor() {
    let wasLoggedIn = this.auth.isLoggedIn();
    effect(() => {
      const loggedIn = this.auth.isLoggedIn();
      if (wasLoggedIn && !loggedIn) {
        untracked(() => {
          void this.disconnect();
        });
      }
      wasLoggedIn = loggedIn;
    });
  }

  get supported(): boolean {
    return typeof navigator !== 'undefined' && 'bluetooth' in navigator && Boolean(navigator.bluetooth);
  }

  get secureContext(): boolean {
    return typeof window === 'undefined' ? true : window.isSecureContext;
  }

  get pendingCount(): number {
    return this.batchSender.pendingCount;
  }

  async connect(deviceId?: number): Promise<void> {
    if (!this.supported) {
      this.status.set('idle');
      this.error.set('Open in Chrome or Edge (desktop or Android) to use Web Bluetooth.');
      return;
    }
    if (!this.secureContext) {
      this.status.set('idle');
      this.error.set('Web Bluetooth requires HTTPS or localhost.');
      return;
    }

    this.error.set('');
    this.status.set('connecting');

    let picked: BluetoothDevice;
    try {
      picked = await navigator.bluetooth.requestDevice({
        filters: [{ services: ['heart_rate'] }],
      });
    } catch (err) {
      if (this.isUserCancelled(err)) {
        this.status.set('idle');
        this.error.set('');
        return;
      }
      this.status.set('error');
      this.error.set(this.describeBluetoothError(err));
      return;
    }

    await this.cleanupTransport({ flushRemaining: true, clearStoredDevice: true });
    this.manualDisconnect = false;
    this.reconnectGeneration += 1;
    this.gattDevice = picked;
    this.deviceName.set(picked.name?.trim() || 'Bluetooth Heart Rate');

    try {
      const resolvedDeviceId =
        deviceId ??
        (
          await firstValueFrom(
            this.syncApi.ensureDevice('bluetooth', picked.name?.trim() || 'Bluetooth Heart Rate'),
          )
        ).device_id;

      this.deviceId.set(resolvedDeviceId);
      await this.subscribeHeartRate(picked);
      this.batchSender.start(resolvedDeviceId);
      this.status.set('connected');
    } catch (err) {
      await this.cleanupTransport({ flushRemaining: false, clearStoredDevice: false });
      this.status.set('error');
      this.error.set(this.describeBluetoothError(err));
    }
  }

  async reconnect(): Promise<void> {
    const device = this.gattDevice;
    const resolvedDeviceId = this.deviceId();
    if (!device || resolvedDeviceId === null) {
      await this.connect();
      return;
    }

    this.manualDisconnect = false;
    this.cancelReconnectTimer();
    this.reconnectGeneration += 1;
    this.error.set('');
    this.status.set('connecting');

    try {
      await this.subscribeHeartRate(device);
      this.batchSender.start(resolvedDeviceId);
      this.status.set('connected');
    } catch (err) {
      this.status.set('error');
      this.error.set(this.describeBluetoothError(err));
    }
  }

  async disconnect(): Promise<void> {
    this.manualDisconnect = true;
    this.reconnectGeneration += 1;
    this.cancelReconnectTimer();
    await this.cleanupTransport({ flushRemaining: true, clearStoredDevice: true });
    this.deviceId.set(null);
    this.deviceName.set('');
    this.bpm.set(null);
    this.error.set('');
    this.status.set('idle');
  }

  private async subscribeHeartRate(device: BluetoothDevice): Promise<void> {
    this.detachCharacteristicListener();
    device.removeEventListener('gattserverdisconnected', this.onGattServerDisconnected);

    if (!device.gatt) {
      throw new Error('Selected device does not expose a GATT server.');
    }

    const server = device.gatt.connected ? device.gatt : await device.gatt.connect();
    const service = await server.getPrimaryService('heart_rate');
    const characteristic = await service.getCharacteristic('heart_rate_measurement');

    this.hrCharacteristic = characteristic;
    characteristic.addEventListener(
      'characteristicvaluechanged',
      this.onCharacteristicValueChanged,
    );
    await characteristic.startNotifications();
    device.addEventListener('gattserverdisconnected', this.onGattServerDisconnected);
  }

  private async attemptReconnectLoop(): Promise<void> {
    const device = this.gattDevice;
    if (!device) return;

    const generation = ++this.reconnectGeneration;
    this.status.set('reconnecting');
    this.error.set('');
    this.detachCharacteristicListener();

    for (const delayMs of RECONNECT_DELAYS_MS) {
      const slept = await this.waitForReconnectDelay(delayMs, generation);
      if (!slept || this.manualDisconnect || generation !== this.reconnectGeneration) {
        return;
      }

      try {
        await this.subscribeHeartRate(device);
        if (this.manualDisconnect || generation !== this.reconnectGeneration) {
          return;
        }
        this.status.set('connected');
        this.error.set('');
        return;
      } catch {
        // Retry on next backoff step.
      }
    }

    if (this.manualDisconnect || generation !== this.reconnectGeneration) return;
    this.status.set('error');
    this.error.set('Bluetooth connection lost after 5 retries. Click Reconnect to try again.');
    await this.batchSender.flush({ ignoreBackoff: true });
  }

  private waitForReconnectDelay(delayMs: number, generation: number): Promise<boolean> {
    this.cancelReconnectTimer();
    return new Promise((resolve) => {
      this.reconnectTimer = setTimeout(() => {
        this.reconnectTimer = null;
        resolve(!this.manualDisconnect && generation === this.reconnectGeneration);
      }, delayMs);
    });
  }

  private cancelReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private detachCharacteristicListener(): void {
    const characteristic = this.hrCharacteristic;
    if (!characteristic) return;
    characteristic.removeEventListener(
      'characteristicvaluechanged',
      this.onCharacteristicValueChanged,
    );
    try {
      void characteristic.stopNotifications()?.catch(() => undefined);
    } catch {
      // Ignore stopNotifications failures on an already-disconnected GATT link.
    }
    this.hrCharacteristic = null;
  }

  private async cleanupTransport(options: {
    flushRemaining: boolean;
    clearStoredDevice: boolean;
  }): Promise<void> {
    this.detachCharacteristicListener();
    if (this.gattDevice) {
      this.gattDevice.removeEventListener('gattserverdisconnected', this.onGattServerDisconnected);
      if (this.gattDevice.gatt?.connected) {
        try {
          this.gattDevice.gatt.disconnect();
        } catch {
          // Ignore disconnect errors during cleanup.
        }
      }
      if (options.clearStoredDevice) {
        this.gattDevice = null;
      }
    }
    await this.batchSender.stop({ flushRemaining: options.flushRemaining });
  }

  private isUserCancelled(err: unknown): boolean {
    if (!err || typeof err !== 'object') return false;
    const name = 'name' in err ? String((err as { name: unknown }).name) : '';
    return name === 'NotFoundError' || name === 'AbortError';
  }

  private describeBluetoothError(err: unknown): string {
    if (err && typeof err === 'object' && 'name' in err) {
      const name = String((err as { name: unknown }).name);
      if (name === 'NotAllowedError' || name === 'SecurityError') {
        return 'Bluetooth permission was denied. Allow Bluetooth access on HTTPS or localhost.';
      }
      if (name === 'NotSupportedError') {
        return 'This device does not support the standard Heart Rate service.';
      }
      if (name === 'NetworkError') {
        return 'Could not connect to the Bluetooth device. Check that Bluetooth is turned on and the sensor is nearby.';
      }
    }
    if (err instanceof Error && err.message) {
      return err.message;
    }
    return describeHttpError(err, 'Could not connect to the Bluetooth Heart Rate device.');
  }
}
