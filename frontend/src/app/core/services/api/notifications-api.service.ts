import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { API_BASE_URL } from '../../config/api.config';

export interface Reminder {
  doctor_id: number;
  doctor_name: string;
  access_end: string;
  days_left: number;
  priority: 'HIGH' | 'NORMAL';
  is_read: boolean;
}

@Injectable({ providedIn: 'root' })
export class NotificationsApi {
  private readonly http = inject(HttpClient);
  private readonly url = inject(API_BASE_URL) + '/notifications';

  list() { return this.http.get<Reminder[]>(this.url); }
  markAll() { return this.http.post<void>(this.url + '/read-all', {}); }
  markOne(item: Reminder) {
    return this.http.post<void>(this.url + '/' + item.doctor_id + '/' + item.access_end + '/read', {});
  }
}
