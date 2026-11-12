import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AuthService } from './auth.service';

const data = { fullName: 'Ana Test', email: 'Ana@Example.com', birthDate: '2003-04-15', password: 'abcd1234' };

/** Builds a JWT-shaped string with the given expiry (the service only reads the payload). */
function fakeToken(expiresInSeconds: number): string {
  const payload = btoa(JSON.stringify({ sub: '1', exp: Math.floor(Date.now() / 1000) + expiresInSeconds }));
  return `x.${payload}.y`;
}

const apiResponse = (token = fakeToken(3600)) => ({
  access_token: token,
  token_type: 'bearer',
  user: { user_id: 7, full_name: 'Ana Test', email: 'ana@example.com', birth_date: '2003-04-15' },
});

describe('AuthService', () => {
  let auth: AuthService;
  let http: HttpTestingController;

  function create(): void {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    auth = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  }

  beforeEach(() => localStorage.clear());
  afterEach(() => http.verify());

  it('registers through the API, normalises the email and starts a session', async () => {
    create();
    const result = auth.register(data);
    const req = http.expectOne('/api/v1/auth/register');
    expect(req.request.body).toEqual({
      full_name: 'Ana Test', email: 'ana@example.com', birth_date: '2003-04-15', password: 'abcd1234',
    });
    req.flush(apiResponse());

    expect(await result).toEqual({ ok: true });
    expect(auth.isLoggedIn()).toBe(true);
    expect(auth.user()?.id).toBe(7);
    expect(auth.initials()).toBe('AT');
    expect(auth.token()).toBeTruthy();
  });

  it('shows the backend message when the email already exists (409)', async () => {
    create();
    const result = auth.register(data);
    http.expectOne('/api/v1/auth/register').flush(
      { detail: 'An account with this email already exists.' }, { status: 409, statusText: 'Conflict' });
    expect(await result).toEqual({ ok: false, error: 'An account with this email already exists.' });
    expect(auth.isLoggedIn()).toBe(false);
  });

  it('logs in and rejects wrong credentials (401)', async () => {
    create();
    const bad = auth.login('ana@example.com', 'wrong');
    http.expectOne('/api/v1/auth/login').flush(
      { detail: 'Incorrect email or password.' }, { status: 401, statusText: 'Unauthorized' });
    expect(await bad).toEqual({ ok: false, error: 'Incorrect email or password.' });

    const good = auth.login(' ANA@example.com ', 'abcd1234');
    const req = http.expectOne('/api/v1/auth/login');
    expect(req.request.body).toEqual({ email: 'ana@example.com', password: 'abcd1234' });
    req.flush(apiResponse());
    expect((await good).ok).toBe(true);
    expect(auth.isLoggedIn()).toBe(true);
  });

  it('explains when the server cannot be reached', async () => {
    create();
    const result = auth.login('ana@example.com', 'abcd1234');
    http.expectOne('/api/v1/auth/login').error(new ProgressEvent('error'));
    const r = await result;
    expect(r.ok).toBe(false);
    expect(!r.ok && r.error).toContain('Cannot reach the server');
  });

  it('keeps the session after a page refresh and clears it on logout', async () => {
    create();
    const result = auth.login('ana@example.com', 'abcd1234');
    http.expectOne('/api/v1/auth/login').flush(apiResponse());
    await result;

    TestBed.resetTestingModule();             // simulates a page reload
    create();
    expect(auth.isLoggedIn()).toBe(true);

    auth.logout();
    expect(auth.isLoggedIn()).toBe(false);
    expect(localStorage.getItem('pulse.session')).toBeNull();
  });

  it('ignores a stored session whose token has expired', () => {
    localStorage.setItem('pulse.session', JSON.stringify({
      token: fakeToken(-60),
      user: { id: 1, fullName: 'Old', email: 'o@example.com', birthDate: '1990-01-01' },
    }));
    create();
    expect(auth.isLoggedIn()).toBe(false);
  });

  it('ignores the old mock-version session (no token)', () => {
    localStorage.setItem('pulse.session', JSON.stringify({ id: 1, fullName: 'Old', email: 'o@example.com', birthDate: '1990-01-01' }));
    create();
    expect(auth.isLoggedIn()).toBe(false);
  });

  it('never stores the plain password', async () => {
    create();
    const result = auth.register(data);
    http.expectOne('/api/v1/auth/register').flush(apiResponse());
    await result;
    expect(JSON.stringify(localStorage)).not.toContain('abcd1234');
  });
});
