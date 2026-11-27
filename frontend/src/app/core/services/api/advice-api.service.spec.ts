import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';
import { AdviceApiService, AdviceResponse } from './advice-api.service';

describe('AdviceApiService', () => {
  let service: AdviceApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AdviceApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('requests GET /api/v1/advice with optional refresh and lang params', async () => {
    const sample: AdviceResponse = {
      items: [],
      source: 'rules',
      generated_at: '2026-11-26T12:00:00Z',
      disclaimer: 'This is not medical advice.',
      ai_available: false,
      ai_consent: false,
    };

    const p1 = firstValueFrom(service.getAdvice());
    const req1 = http.expectOne('/api/v1/advice');
    expect(req1.request.method).toBe('GET');
    req1.flush(sample);
    expect(await p1).toEqual(sample);

    const p2 = firstValueFrom(service.getAdvice(true, 'ru'));
    const req2 = http.expectOne(
      (r) => r.url === '/api/v1/advice' && r.params.get('refresh') === 'true' && r.params.get('lang') === 'ru',
    );
    expect(req2.request.method).toBe('GET');
    req2.flush(sample);
    await p2;
  });

  it('sends PUT /api/v1/advice/consent with enabled flag', async () => {
    const p = firstValueFrom(service.setConsent(true));
    const req = http.expectOne('/api/v1/advice/consent');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ enabled: true });
    req.flush({ enabled: true });
    expect(await p).toEqual({ enabled: true });
  });
});
