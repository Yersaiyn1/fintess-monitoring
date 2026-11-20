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

export type AuthResult = { ok: true } | { ok: false; error: string };

/** Shapes returned by the FastAPI backend (backend/app/schemas/auth.py). */
interface ApiUser { user_id: number; full_name: string; email: string; birth_date: string }
interface TokenResponse { access_token: string; token_type: string; user: ApiUser }

interface Session { token: string; user: User }

const SESSION_KEY = 'pulse.session';

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

  readonly user = computed(() => this._session()?.user ?? null);
  readonly token = computed(() => this._session()?.token ?? null);
  readonly isLoggedIn = computed(() => this._session() !== null);
  readonly initials = computed(() => {
    const name = this.user()?.fullName.trim() ?? '';
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

  logout(): void {
    this._session.set(null);
    try { localStorage.removeItem(SESSION_KEY); } catch { /* storage unavailable */ }
  }

  async updateAccount(data: AccountUpdateData): Promise<AuthResult> {
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
      this._session.update((session) => session ? {
        ...session,
        user: { id: user.user_id, fullName: user.full_name, email: user.email, birthDate: user.birth_date },
      } : session);
      const session = this._session();
      if (session) this.save(session);
      return { ok: true };
    } catch (e) {
      return { ok: false, error: this.messageFrom(e, 'Could not update your account.') };
    }
  }

  private async authenticate(path: string, body: object, fallbackError: string): Promise<AuthResult> {
    try {
      const res = await firstValueFrom(this.http.post<TokenResponse>(`${this.base}${path}`, body));
      const session: Session = {
        token: res.access_token,
        user: {
          id: res.user.user_id,
          fullName: res.user.full_name,
          email: res.user.email,
          birthDate: res.user.birth_date,
        },
      };
      this._session.set(session);
      this.save(session);
      return { ok: true };
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
      const raw = localStorage.getItem(SESSION_KEY);
      if (!raw) return null;
      const s = JSON.parse(raw) as Partial<Session>;
      if (typeof s.token !== 'string' || !s.user || this.isExpired(s.token)) {
        localStorage.removeItem(SESSION_KEY);
        return null;
      }
      return s as Session;
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

  private save(session: Session): void {
    try { localStorage.setItem(SESSION_KEY, JSON.stringify(session)); } catch { /* storage unavailable */ }
  }
}
