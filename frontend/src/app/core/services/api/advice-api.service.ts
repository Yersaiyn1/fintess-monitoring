import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from '../../config/api.config';

export type AdviceSeverity = 'info' | 'success' | 'warning';
export type AdviceSource = 'ai' | 'rules';

export interface AdviceItem {
  code: string;
  severity: AdviceSeverity;
  title: string;
  text: string;
  data: Record<string, unknown>;
}

export interface AdviceResponse {
  items: AdviceItem[];
  source: AdviceSource;
  generated_at: string;
  disclaimer: string;
  ai_available: boolean;
  ai_consent: boolean;
}

export interface AdviceConsentResponse {
  enabled: boolean;
}

@Injectable({ providedIn: 'root' })
export class AdviceApiService {
  private readonly http = inject(HttpClient);
  private readonly url = `${inject(API_BASE_URL)}/advice`;

  getAdvice(refresh = false, lang?: string): Observable<AdviceResponse> {
    let params = new HttpParams();
    if (refresh) {
      params = params.set('refresh', 'true');
    }
    if (lang) {
      params = params.set('lang', lang);
    }
    return this.http.get<AdviceResponse>(this.url, { params });
  }

  setConsent(enabled: boolean): Observable<AdviceConsentResponse> {
    return this.http.put<AdviceConsentResponse>(`${this.url}/consent`, { enabled });
  }
}
