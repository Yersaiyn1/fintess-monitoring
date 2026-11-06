import { TestBed } from '@angular/core/testing';
import { AuthService } from './auth.service';

const data = { fullName: 'Ana Test', email: 'Ana@Example.com', birthDate: '2003-04-15', password: 'abcd1234' };

describe('AuthService', () => {
  let auth: AuthService;
  beforeEach(() => {
    localStorage.clear();
    auth = TestBed.inject(AuthService);
  });

  it('registers a user and starts a session', async () => {
    expect(await auth.register(data)).toEqual({ ok: true });
    expect(auth.isLoggedIn()).toBe(true);
    expect(auth.initials()).toBe('AT');
  });

  it('does not allow the same email twice (case-insensitive)', async () => {
    await auth.register(data);
    const again = await auth.register({ ...data, email: 'ana@example.com' });
    expect(again.ok).toBe(false);
  });

  it('logs in with the right password and rejects the wrong one', async () => {
    await auth.register(data);
    auth.logout();
    expect(auth.isLoggedIn()).toBe(false);
    expect((await auth.login('ana@example.com', 'wrong')).ok).toBe(false);
    expect((await auth.login('ana@example.com', 'abcd1234')).ok).toBe(true);
    expect(auth.isLoggedIn()).toBe(true);
  });

  it('does not store the plain password', async () => {
    await auth.register(data);
    expect(localStorage.getItem('pulse.users')).not.toContain('abcd1234');
  });
});
