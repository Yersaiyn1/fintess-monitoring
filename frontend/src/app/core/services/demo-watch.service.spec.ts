import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { DashboardRefreshThrottler } from './batch-sender';
import {
  DEMO_HR_MAX,
  DEMO_HR_MIN,
  DemoWatchService,
} from './demo-watch.service';

describe('DemoWatchService', () => {
  let service: DemoWatchService;
  let http: HttpTestingController;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-26T12:00:00.000Z'));
    localStorage.clear();
    const payload = btoa(JSON.stringify({ sub: '1', exp: Math.floor(Date.now() / 1000) + 3600 }));
    localStorage.setItem(
      'pulse.session',
      JSON.stringify({
        token: `x.${payload}.y`,
        user: { id: 1, fullName: 'Ana B', email: 'a@b.co', birthDate: '2000-01-01' },
      }),
    );
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    TestBed.inject(DashboardRefreshThrottler).reset();
    service = TestBed.inject(DemoWatchService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(async () => {
    if (service.status() !== 'idle') {
      const stopping = service.stop();
      await vi.advanceTimersByTimeAsync(0);
      for (const req of http.match('/api/v1/sync/batch')) {
        req.flush({ device_id: 3, synced_count: 1, skipped_count: 0 });
      }
      await stopping;
    }
    vi.restoreAllMocks();
    vi.useRealTimers();
    http.verify();
  });

  it('generates heart rate within 55..120 every 3s, batches every 15s, and throttles dashboard refresh to 30s', async () => {
    const starting = service.start();
    await vi.advanceTimersByTimeAsync(0);

    const ensureReq = http.expectOne('/api/v1/sync/devices/ensure');
    expect(ensureReq.request.body).toEqual({ provider: 'demo', name: 'Demo Watch' });
    ensureReq.flush({
      device_id: 3,
      user_id: 1,
      model: 'Demo Watch',
      serial_number: 'DEMO-1',
      provider: 'demo',
      is_active: true,
      last_sync_time: null,
    });
    await starting;

    expect(service.status()).toBe('running');
    const observedBpms: number[] = [];
    if (service.bpm() !== null) observedBpms.push(service.bpm()!);

    for (let i = 0; i < 4; i++) {
      await vi.advanceTimersByTimeAsync(3_000);
      if (service.bpm() !== null) observedBpms.push(service.bpm()!);
    }

    expect(observedBpms.length).toBe(5);
    for (const bpm of observedBpms) {
      expect(bpm).toBeGreaterThanOrEqual(DEMO_HR_MIN);
      expect(bpm).toBeLessThanOrEqual(DEMO_HR_MAX);
    }

    // At 15s total, first batch flush runs and triggers dashboard refresh
    await vi.advanceTimersByTimeAsync(3_000);
    const firstBatch = http.expectOne('/api/v1/sync/batch');
    expect(firstBatch.request.body.device_id).toBe(3);
    expect(firstBatch.request.body.readings.some((r: { steps?: number }) => (r.steps ?? 0) > 0)).toBe(
      true,
    );
    firstBatch.flush({ device_id: 3, synced_count: 6, skipped_count: 0 });
    await vi.advanceTimersByTimeAsync(0);

    http.expectOne('/api/v1/dashboard').flush({ user_id: 1, week: [] });
    http
      .expectOne((r) => r.url === '/api/v1/workouts')
      .flush({ items: [], total: 0, limit: 4, offset: 0 });

    // At 30s total (15s after first refresh), second batch flushes WITHOUT refreshing dashboard (<30s)
    await vi.advanceTimersByTimeAsync(15_000);
    const secondBatch = http.expectOne('/api/v1/sync/batch');
    secondBatch.flush({ device_id: 3, synced_count: 5, skipped_count: 0 });
    await vi.advanceTimersByTimeAsync(0);
    http.expectNone('/api/v1/dashboard');

    // Stop flushes remaining buffered points
    const stopping = service.stop();
    await vi.advanceTimersByTimeAsync(0);
    for (const req of http.match('/api/v1/sync/batch')) {
      req.flush({ device_id: 3, synced_count: 1, skipped_count: 0 });
    }
    await stopping;

    expect(service.status()).toBe('idle');
    expect(service.bpm()).toBeNull();
  });

  it('simulateHighHr smoothly raises heart rate toward ~110 bpm within 55..120', async () => {
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    await service.start(15);

    service.simulateHighHr(180_000);
    expect(service.highHrActive()).toBe(true);

    for (let i = 0; i < 10; i++) {
      await vi.advanceTimersByTimeAsync(3_000);
      for (const req of http.match('/api/v1/sync/batch')) {
        req.flush({ device_id: 15, synced_count: 1, skipped_count: 0 });
      }
      for (const req of http.match('/api/v1/dashboard')) {
        req.flush({ user_id: 1, week: [] });
      }
      for (const req of http.match((r) => r.url === '/api/v1/workouts')) {
        req.flush({ items: [], total: 0, limit: 4, offset: 0 });
      }
    }

    expect(service.bpm()).toBeGreaterThanOrEqual(98);
    expect(service.bpm()).toBeLessThanOrEqual(DEMO_HR_MAX);
  });
});
