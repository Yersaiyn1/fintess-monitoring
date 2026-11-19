import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../../config/api.config';

export interface DoctorDirectoryEntry {
  doctor_id: number;
  full_name: string;
  specialty: string | null;
  license_number: string;
  email: string | null;
  is_active: boolean;
}

export interface DoctorAccessRecord {
  user_id: number;
  doctor_id: number;
  doctor_name: string;
  specialty: string | null;
  license_number: string;
  access_start: string;
  access_end: string;
  is_active: boolean;
}

@Injectable({ providedIn: 'root' })
export class DoctorAccessApiService {
  private readonly http = inject(HttpClient);
  private readonly url = `${inject(API_BASE_URL)}/doctor`;

  directory(): Observable<DoctorDirectoryEntry[]> {
    return this.http.get<DoctorDirectoryEntry[]>(`${this.url}/directory`);
  }

  listAccess(): Observable<DoctorAccessRecord[]> {
    return this.http.get<DoctorAccessRecord[]>(`${this.url}/access`);
  }

  grantAccess(
    doctorId: number,
    accessStart: string,
    accessEnd: string,
  ): Observable<DoctorAccessRecord> {
    return this.http.post<DoctorAccessRecord>(`${this.url}/access`, {
      doctor_id: doctorId,
      access_start: accessStart,
      access_end: accessEnd,
    });
  }

  revokeAccess(doctorId: number): Observable<void> {
    return this.http.delete<void>(`${this.url}/access/${doctorId}`);
  }
}
