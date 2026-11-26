import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../../config/api.config';

export interface DeviceRecord {
  device_id: number;
  model: string;
  serial_number: string;
  provider: string;
  last_sync_time: string | null;
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
    return this.http.get<DeviceRecord[]>(`${this.url}/devices`);
  }

  addDevice(model: string, serialNumber: string): Observable<DeviceRecord> {
    return this.http.post<DeviceRecord>(`${this.url}/devices`, {
      model,
      serial_number: serialNumber,
    });
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
}
