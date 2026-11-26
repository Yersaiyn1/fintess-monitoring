import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../../config/api.config';

export type DeviceProvider =
  | 'manual'
  | 'health_connect'
  | 'bluetooth'
  | 'fitbit'
  | 'garmin'
  | 'demo';

export interface DeviceRecord {
  device_id: number;
  user_id: number;
  model: string;
  serial_number: string;
  provider: DeviceProvider;
  is_active: boolean;
  last_sync_time: string | null;
}

export interface CreateDeviceInput {
  model: string;
  serial_number: string;
  provider?: DeviceProvider;
}

export interface SyncReadingInput {
  device_id?: number;
  date_time: string;
  heart_rate_bpm?: number | null;
  steps?: number | null;
  calories_kcal?: number | null;
  blood_pressure?: string | null;
}

export interface SyncBatchResponse {
  device_id: number;
  synced_count: number;
  skipped_count: number;
}

/**
 * Typed HTTP client for device management and batch reading synchronization.
 */
@Injectable({ providedIn: 'root' })
export class SyncApiService {
  private readonly http = inject(HttpClient);
  private readonly url = `${inject(API_BASE_URL)}/sync`;

  listDevices(): Observable<DeviceRecord[]> {
    return this.http.get<DeviceRecord[]>(`${this.url}/devices`);
  }

  createDevice(payload: CreateDeviceInput): Observable<DeviceRecord> {
    return this.http.post<DeviceRecord>(`${this.url}/devices`, payload);
  }

  ensureDevice(provider: DeviceProvider, name: string): Observable<DeviceRecord> {
    return this.http.post<DeviceRecord>(`${this.url}/devices/ensure`, { provider, name });
  }

  batch(deviceId: number, readings: SyncReadingInput[]): Observable<SyncBatchResponse> {
    return this.http.post<SyncBatchResponse>(`${this.url}/batch`, {
      device_id: deviceId,
      readings: readings.map((reading) => ({
        ...reading,
        device_id: deviceId,
      })),
    });
  }
}
