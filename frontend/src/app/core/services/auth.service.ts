import { Injectable, computed, signal } from '@angular/core';

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

export type AuthResult = { ok: true } | { ok: false; error: string };

interface StoredUser extends User {
  passwordHash: string;
}

const USERS_KEY = 'pulse.users';
const SESSION_KEY = 'pulse.session';

/**
 * Phase 1: MOCK authentication stored in the browser (localStorage).
 * Later it is replaced by calls to the FastAPI backend (POST /auth/login,
 * POST /auth/register); the public methods below stay the same, so the
 * login and register pages do not change.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly _user = signal<User | null>(this.loadSession());

  readonly user = this._user.asReadonly();
  readonly isLoggedIn = computed(() => this._user() !== null);
  readonly initials = computed(() => {
    const name = this._user()?.fullName.trim() ?? '';
    return name.split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? '').join('') || '?';
  });

  async register(data: RegisterData): Promise<AuthResult> {
    const users = this.loadUsers();
    const email = data.email.trim().toLowerCase();
    if (users.some((u) => u.email === email)) {
      return { ok: false, error: 'An account with this email already exists.' };
    }
    const stored: StoredUser = {
      id: Math.max(0, ...users.map((u) => u.id)) + 1,
      fullName: data.fullName.trim(),
      email,
      birthDate: data.birthDate,
      passwordHash: await this.hash(data.password),
    };
    this.save(USERS_KEY, [...users, stored]);
    this.startSession(stored);
    return { ok: true };
  }

  async login(email: string, password: string): Promise<AuthResult> {
    const found = this.loadUsers().find((u) => u.email === email.trim().toLowerCase());
    // Same message for "no user" and "wrong password" (does not reveal which emails exist).
    if (!found || found.passwordHash !== (await this.hash(password))) {
      return { ok: false, error: 'Incorrect email or password.' };
    }
    this.startSession(found);
    return { ok: true };
  }

  logout(): void {
    this._user.set(null);
    try { localStorage.removeItem(SESSION_KEY); } catch { /* storage unavailable */ }
  }

  private startSession(u: StoredUser): void {
    const user: User = { id: u.id, fullName: u.fullName, email: u.email, birthDate: u.birthDate };
    this._user.set(user);
    this.save(SESSION_KEY, user);
  }

  private async hash(text: string): Promise<string> {
    const bytes = new TextEncoder().encode(text);
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, '0')).join('');
  }

  private loadUsers(): StoredUser[] { return this.load<StoredUser[]>(USERS_KEY) ?? []; }
  private loadSession(): User | null { return this.load<User>(SESSION_KEY); }

  private load<T>(key: string): T | null {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : null;
    } catch { return null; }
  }

  private save(key: string, value: unknown): void {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
  }
}
