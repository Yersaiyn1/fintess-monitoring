import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { API_BASE_URL } from '../config/api.config';

export interface ApplicationDocument {
  filename: string;
  content_type: string;
  size: number;
  document_id: string;
}

export interface DoctorApplication {
  application_id: number;
  full_name: string;
  email: string;
  specialty: string;
  license_number: string;
  status: 'pending' | 'approved' | 'rejected';
  documents: ApplicationDocument[];
  submitted_at: string;
  reviewed_at: string | null;
  rejection_reason: string | null;
}

@Injectable({ providedIn: 'root' })
export class DoctorApplicationsService {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE_URL);

  submit(data: FormData): Promise<DoctorApplication> {
    return firstValueFrom(this.http.post<DoctorApplication>(`${this.base}/doctor-applications`, data));
  }

  list(): Promise<DoctorApplication[]> {
    return firstValueFrom(this.http.get<DoctorApplication[]>(`${this.base}/admin/doctor-applications`));
  }

  approve(id: number): Promise<DoctorApplication> {
    return firstValueFrom(this.http.post<DoctorApplication>(`${this.base}/admin/doctor-applications/${id}/approve`, {}));
  }

  reject(id: number, reason: string): Promise<DoctorApplication> {
    return firstValueFrom(this.http.post<DoctorApplication>(`${this.base}/admin/doctor-applications/${id}/reject`, { reason }));
  }

  async download(applicationId: number, doc: ApplicationDocument): Promise<void> {
    const blob = await firstValueFrom(this.http.get(
      `${this.base}/admin/doctor-applications/${applicationId}/documents/${doc.document_id}`,
      { responseType: 'blob' },
    ));
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = doc.filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  message(error: unknown, fallback: string): string {
    if (error instanceof HttpErrorResponse && typeof error.error?.detail === 'string') {
      return error.error.detail;
    }
    if (error instanceof HttpErrorResponse && Array.isArray(error.error?.detail) && error.error.detail[0]?.msg) {
      return String(error.error.detail[0].msg);
    }
    if (error instanceof HttpErrorResponse && error.status === 0) {
      return 'Cannot reach the server. Make sure the backend is running.';
    }
    return fallback;
  }
}
