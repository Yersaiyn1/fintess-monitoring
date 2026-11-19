import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { AuthService } from '../services/auth.service';
import { authInterceptor } from './auth.interceptor';

function fakeToken(): string {
  return `x.${btoa(JSON.stringify({ sub: '1', exp: Math.floor(Date.now() / 1000) + 3600 }))}.y`;
}

describe('authInterceptor', () => {
  let http: HttpClient;
  let ctrl: HttpTestingController;

  function setup(loggedIn: boolean) {
    localStorage.clear();
    if (loggedIn) {
      localStorage.setItem('pulse.session', JSON.stringify({
        token: fakeToken(), user: { id: 1, fullName: 'A B', email: 'a@b.co', birthDate: '2000-01-01' },
      }));
    }
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpClient);
    ctrl = TestBed.inject(HttpTestingController);
  }
  afterEach(() => ctrl.verify());

  it('adds the Bearer token to API requests only', () => {
    setup(true);
    http.get('/api/v1/dashboard').subscribe();
    expect(ctrl.expectOne('/api/v1/dashboard').request.headers.get('Authorization')).toMatch(/^Bearer x\./);

    http.get('https://other.example.com/data').subscribe();
    expect(ctrl.expectOne('https://other.example.com/data').request.headers.has('Authorization')).toBe(false);
  });

  it('adds Bearer token to FormData uploads without overriding Content-Type', () => {
    setup(true);
    const body = new FormData();
    body.append('file', new Blob(['zip'], { type: 'application/zip' }), 'export.zip');

    http.post('/api/v1/sync/upload-hc', body).subscribe();
    const req = ctrl.expectOne('/api/v1/sync/upload-hc').request;
    expect(req.headers.get('Authorization')).toMatch(/^Bearer x\./);
    expect(req.headers.has('Content-Type')).toBe(false);
  });

  it('logs the user out and goes to /login when the API answers 401', () => {
    setup(true);
    const auth = TestBed.inject(AuthService);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);

    http.get('/api/v1/dashboard').subscribe({ error: () => undefined });
    ctrl.expectOne('/api/v1/dashboard').flush({ detail: 'Not authenticated.' }, { status: 401, statusText: 'Unauthorized' });

    expect(auth.isLoggedIn()).toBe(false);
    expect(navigate).toHaveBeenCalledWith('/login');
  });

  it('does not redirect when a login attempt itself fails with 401', () => {
    setup(false);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    http.post('/api/v1/auth/login', {}).subscribe({ error: () => undefined });
    ctrl.expectOne('/api/v1/auth/login').flush({ detail: 'x' }, { status: 401, statusText: 'Unauthorized' });
    expect(navigate).not.toHaveBeenCalled();
  });
});
