import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { API_BASE_URL } from '../config/api.config';

export interface User {
  id: number;
  fullName: string;
  email: string;
  birthDate: string;
}

export interface DoctorAccount {
  id: number;
  fullName: string;
  email: string;
  specialty: string | null;
  licenseNumber?: string;
}

export interface RegisterData {
  fullName: string;
  email: string;
  birthDate: string;
  password: string;
}

export interface AccountUpdateData {
  fullName: string;
  email: string;
  currentPassword?: string;
  newPassword?: string;
}

export type AuthResult = { ok: true; role: 'patient' | 'doctor' | 'admin' } | { ok: false; error: string };

/** Shapes returned by the FastAPI backend (backend/app/schemas/auth.py). */
interface ApiUser { user_id: number; full_name: string; email: string; birth_date: string }
interface TokenResponse { access_token: string; token_type: string; role?: 'patient' | 'admin'; user: ApiUser }
interface ApiDoctor { doctor_id: number; full_name: string; email: string; specialty: string | null; license_number: string }
interface DoctorTokenResponse { access_token: string; token_type: string; doctor: ApiDoctor }

type Session =
  | { token: string; role: 'patient' | 'admin'; user: User }
  | { token: string; role: 'doctor'; doctor: DoctorAccount };

const SESSION_KEY = 'pulse.session';
const DOCTOR_SESSION_KEY = 'pulse.doctor.session';
const ACTIVE_ROLE_KEY = 'pulse.active-role';

/**
 * Authentication against the FastAPI backend (POST /auth/register, POST /auth/login).
 * The public API (register, login, logout, user, isLoggedIn, initials) is the same as in the
 * first mock version, so the login and register pages did not need to change.
 *
 * The JWT is kept in localStorage so the session survives a page refresh.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE_URL);

  private readonly _session = signal<Session | null>(this.loadSession());

  readonly role = computed(() => this._session()?.role ?? null);
  readonly user = computed(() => {
    const session = this._session();
    return session && session.role !== 'doctor' ? session.user : null;
  });
  readonly doctor = computed(() => {
    const session = this._session();
    return session?.role === 'doctor' ? session.doctor : null;
  });
  readonly accountName = computed(() => this.user()?.fullName ?? this.doctor()?.fullName ?? '');
  readonly token = computed(() => this._session()?.token ?? null);
  readonly isLoggedIn = computed(() => this._session() !== null);
  readonly initials = computed(() => {
    const name = this.accountName().trim();
    return name.split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? '').join('') || '?';
  });

  async register(data: RegisterData): Promise<AuthResult> {
    return this.authenticate('/auth/register', {
      full_name: data.fullName.trim(),
      email: data.email.trim().toLowerCase(),
      birth_date: data.birthDate,
      password: data.password,
    }, 'Registration failed. Please try again.');
  }

  async login(email: string, password: string): Promise<AuthResult> {
    return this.authenticate('/auth/login', {
      email: email.trim().toLowerCase(),
      password,
    }, 'Login failed. Please try again.');
  }

  async loginDoctor(email: string, password: string): Promise<AuthResult> {
    try {
      const result = await firstValueFrom(this.http.post<DoctorTokenResponse>(`${this.base}/auth/doctor/login`, {
        email: email.trim().toLowerCase(),
        password,
      }));
      this.activateSession({
        token: result.access_token,
        role: 'doctor',
        doctor: {
          id: result.doctor.doctor_id,
          fullName: result.doctor.full_name,
          email: result.doctor.email,
          specialty: result.doctor.specialty,
          licenseNumber: result.doctor.license_number,
        },
      });
      return { ok: true, role: 'doctor' };
    } catch (e) {
      return { ok: false, error: this.messageFrom(e, 'Doctor login failed. Please try again.') };
    }
  }

  logout(): void {
    this._session.set(null);
    try {
      localStorage.removeItem(SESSION_KEY);
      localStorage.removeItem(DOCTOR_SESSION_KEY);
      localStorage.removeItem(ACTIVE_ROLE_KEY);
    } catch { /* storage unavailable */ }
  }

  async updateAccount(data: AccountUpdateData): Promise<AuthResult> {
    if (this.role() !== 'patient' && this.role() !== 'admin') return { ok: false, error: 'Only patient accounts can update these details.' };
    const body: Record<string, string> = {
      full_name: data.fullName.trim(),
      email: data.email.trim().toLowerCase(),
    };
    if (data.newPassword) {
      body['current_password'] = data.currentPassword ?? '';
      body['new_password'] = data.newPassword;
    }
    try {
      const user = await firstValueFrom(this.http.patch<ApiUser>(`${this.base}/auth/me`, body));
      this._session.update((session) => session && session.role !== 'doctor' ? {
        ...session,
        user: { id: user.user_id, fullName: user.full_name, email: user.email, birthDate: user.birth_date },
      } : session);
      const session = this._session();
      if (session && session.role !== 'doctor') this.activateSession(session);
      return { ok: true, role: session?.role === 'admin' ? 'admin' : 'patient' };
    } catch (e) {
      return { ok: false, error: this.messageFrom(e, 'Could not update your account.') };
    }
  }

  private async authenticate(path: string, body: object, fallbackError: string): Promise<AuthResult> {
    try {
      const res = await firstValueFrom(this.http.post<TokenResponse>(`${this.base}${path}`, body));
      const session: Session = {
        token: res.access_token,
        role: res.role === 'admin' ? 'admin' : 'patient',
        user: {
          id: res.user.user_id,
          fullName: res.user.full_name,
          email: res.user.email,
          birthDate: res.user.birth_date,
        },
      };
      this.activateSession(session);
      return { ok: true, role: res.role === 'admin' ? 'admin' : 'patient' };
    } catch (e) {
      return { ok: false, error: this.messageFrom(e, fallbackError) };
    }
  }

  private messageFrom(e: unknown, fallback: string): string {
    if (e instanceof HttpErrorResponse) {
      if (e.status === 0) return 'Cannot reach the server. Make sure the backend is running.';
      const detail = e.error?.detail;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail) && detail[0]?.msg) {
        return String(detail[0].msg).replace(/^Value error,\s*/, '');
      }
    }
    return fallback;
  }

  /** Restores the session after a page refresh; drops it if the token has expired. */
  private loadSession(): Session | null {
    try {
      const activeRole = localStorage.getItem(ACTIVE_ROLE_KEY);
      const storageKey = activeRole === 'doctor' ? DOCTOR_SESSION_KEY : SESSION_KEY;
      const raw = localStorage.getItem(storageKey);
      if (!raw) return null;
      const s = JSON.parse(raw) as Partial<Session> & { user?: User; doctor?: DoctorAccount };
      if (typeof s.token !== 'string' || this.isExpired(s.token)) {
        localStorage.removeItem(storageKey);
        localStorage.removeItem(ACTIVE_ROLE_KEY);
        return null;
      }
      if (activeRole === 'doctor' && s.doctor && typeof s.doctor.id === 'number') {
        return { token: s.token, role: 'doctor', doctor: s.doctor };
      }
      if (activeRole !== 'doctor' && s.user && typeof s.user.id === 'number') {
        return { token: s.token, role: activeRole === 'admin' || s.role === 'admin' ? 'admin' : 'patient', user: s.user };
      }
      localStorage.removeItem(storageKey);
      localStorage.removeItem(ACTIVE_ROLE_KEY);
      return null;
    } catch {
      return null;
    }
  }

  private isExpired(token: string): boolean {
    try {
      const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
      return typeof payload.exp === 'number' && payload.exp * 1000 <= Date.now();
    } catch {
      return true;
    }
  }

  private activateSession(session: Session): void {
    this._session.set(session);
    try {
      const doctor = session.role === 'doctor';
      localStorage.setItem(ACTIVE_ROLE_KEY, session.role);
      localStorage.setItem(doctor ? DOCTOR_SESSION_KEY : SESSION_KEY, JSON.stringify(session));
      localStorage.removeItem(doctor ? SESSION_KEY : DOCTOR_SESSION_KEY);
    } catch { /* storage unavailable */ }
  }
}
