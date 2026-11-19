import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../../config/api.config';

export interface HealthConnectUploadResponse {
  filename: string;
  total_parsed: number;
  inserted: number;
  duplicates_skipped: number;
  metrics_breakdown: Record<string, number>;
}

/** HTTP client for Health Connect archive imports and device sync endpoints. */
@Injectable({ providedIn: 'root' })
export class SyncApiService {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE_URL);

  /** POST /api/v1/sync/upload-hc — import Android Health Connect .zip or .db export */
  uploadHealthConnectArchive(file: File): Observable<HealthConnectUploadResponse> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http.post<HealthConnectUploadResponse>(`${this.base}/sync/upload-hc`, formData);
  }
}
