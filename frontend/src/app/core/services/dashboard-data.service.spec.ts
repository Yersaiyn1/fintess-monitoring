import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { DailyActivity } from '../models/activity.model';
import { DashboardDataService } from './dashboard-data.service';

function week(todaySteps = 7482, yesterdaySteps = 5390): DailyActivity[] {
  return Array.from({ length: 7 }, (_, i) => {
    const steps = i === 6 ? todaySteps : i === 5 ? yesterdaySteps : 1000;
    return { date: `2026-11-0${i + 1}`, label: 'Day', steps, calories: steps * 0.05, distanceKm: steps * 0.00075, activeMinutes: Math.round(steps / 100) };
  });
}

describe('DashboardDataService', () => {
  let service: DashboardDataService;
  let http: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(DashboardDataService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('starts with 7 empty days (so the page can render before data arrives)', () => {
    expect(service.week().length).toBe(7);
    expect(service.today().steps).toBe(0);
    expect(service.stepsRemaining()).toBe(10_000);
  });

  it('loads the week from GET /api/v1/dashboard', async () => {
    const done = service.load();
    expect(service.loading()).toBe(true);
    http.expectOne('/api/v1/dashboard').flush({ user_id: 1, week: week() });
    await done;

    expect(service.loading()).toBe(false);
    expect(service.today().steps).toBe(7482);
    expect(service.stepsProgress()).toBeCloseTo(0.7482, 4);
    expect(service.stepsRemaining()).toBe(2518);
  });

  it('builds four stat cards with the change versus yesterday', async () => {
    const done = service.load();
    http.expectOne('/api/v1/dashboard').flush({ user_id: 1, week: week(6000, 3000) });
    await done;
    const cards = service.statCards();
    expect(cards.map((c) => c.id)).toEqual(['calories', 'distance', 'active', 'workouts']);
    expect(cards[0].change).toBe(100); // 6000 vs 3000 steps -> calories doubled
  });

  it('reports an error when the server is not reachable, and recovers on retry', async () => {
    const failed = service.load();
    http.expectOne('/api/v1/dashboard').error(new ProgressEvent('error'));
    await failed;
    expect(service.error()).toContain('Cannot reach the server');

    const retry = service.load();
    http.expectOne('/api/v1/dashboard').flush({ user_id: 1, week: week() });
    await retry;
    expect(service.error()).toBe('');
    expect(service.today().steps).toBe(7482);
  });

  it('has no fake workouts: that data arrives with Phase 2', () => {
    expect(service.recentWorkouts()).toEqual([]);
    expect(service.workoutsToday()).toBe(0);
  });
});
