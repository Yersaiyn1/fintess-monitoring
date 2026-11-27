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
  end_time?: string | null;
  heart_rate_bpm?: number | null;
  steps?: number | null;
  calories_kcal?: number | null;
  blood_pressure?: string | null;
  spo2_percent?: number | null;
}

export interface SyncBatchResponse {
  device_id: number;
  synced_count: number;
  skipped_count: number;
}

export interface HealthConnectUploadResponse {
  filename: string;
  total_parsed: number;
  inserted: number;
  updated: number;
  unchanged_skipped: number;
  duplicates_skipped: number;
  sleep_sessions: number;
  metrics_breakdown: Record<string, number>;
}

/**
 * Typed HTTP client for device management, Health Connect archive uploads,
 * and batch reading synchronization.
 */
@Injectable({ providedIn: 'root' })
export class SyncApiService {
  private readonly http = inject(HttpClient);
  private readonly url = `${inject(API_BASE_URL)}/sync`;

  uploadHealthConnectArchive(file: File): Observable<HealthConnectUploadResponse> {
    const body = new FormData();
    body.append('file', file);
    return this.http.post<HealthConnectUploadResponse>(`${this.url}/upload-hc`, body);
  }

  devices(): Observable<DeviceRecord[]> {
    return this.listDevices();
  }

  listDevices(): Observable<DeviceRecord[]> {
    return this.http.get<DeviceRecord[]>(`${this.url}/devices`);
  }

  addDevice(model: string, serialNumber: string): Observable<DeviceRecord> {
    return this.createDevice({ model, serial_number: serialNumber });
  }

  createDevice(payload: CreateDeviceInput): Observable<DeviceRecord> {
    return this.http.post<DeviceRecord>(`${this.url}/devices`, payload);
  }

  ensureDevice(provider: DeviceProvider, name: string): Observable<DeviceRecord> {
    return this.http.post<DeviceRecord>(`${this.url}/devices/ensure`, { provider, name });
  }

  createReading(body: {
    device_id: number;
    date_time: string;
    heart_rate_bpm: number | null;
    steps: number | null;
    calories_kcal: number | null;
    blood_pressure: string | null;
  }): Observable<{ reading_id: number; status: string }> {
    return this.http.post<{ reading_id: number; status: string }>(`${this.url}/reading`, body);
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
