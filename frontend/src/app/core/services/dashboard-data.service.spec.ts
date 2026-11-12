import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { DailyActivity } from '../models/activity.model';
import { Workout } from '../models/workout.model';
import { DashboardDataService } from './dashboard-data.service';

function week(todaySteps = 7482, yesterdaySteps = 5390): DailyActivity[] {
  return Array.from({ length: 7 }, (_, i) => {
    const steps = i === 6 ? todaySteps : i === 5 ? yesterdaySteps : 1000;
    return { date: `2026-11-0${i + 1}`, label: 'Day', steps, calories: steps * 0.05, distanceKm: steps * 0.00075, activeMinutes: Math.round(steps / 100) };
  });
}

function workout(id: number, startedAt: string): Workout {
  return { id, kind: 'Run', startedAt, endedAt: startedAt, durationSec: 1920, steps: 5120, distanceKm: 5.12, caloriesKcal: 352, inProgress: false };
}

describe('DashboardDataService', () => {
  let service: DashboardDataService;
  let http: HttpTestingController;

  /** The dashboard asks for the week AND the latest workouts. */
  function answer(weekData: DailyActivity[] | 'fail', workouts: Workout[] = []): void {
    const dash = http.expectOne('/api/v1/dashboard');
    if (weekData === 'fail') dash.error(new ProgressEvent('error'));
    else dash.flush({ user_id: 1, week: weekData });
    http.expectOne((r) => r.url === '/api/v1/workouts' && r.params.get('limit') === '4')
      .flush({ items: workouts, total: workouts.length, limit: 4, offset: 0 });
  }

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
    answer(week());
    await done;

    expect(service.loading()).toBe(false);
    expect(service.today().steps).toBe(7482);
    expect(service.stepsProgress()).toBeCloseTo(0.7482, 4);
    expect(service.stepsRemaining()).toBe(2518);
  });

  it('builds stat cards for the dashboard and the activity page', async () => {
    const done = service.load();
    answer(week(6000, 3000));
    await done;
    expect(service.statCards().map((c) => c.id)).toEqual(['calories', 'distance', 'active', 'workouts']);
    expect(service.activityCards().map((c) => c.id)).toEqual(['steps', 'calories', 'distance', 'active']);
    expect(service.activityCards()[0].value).toBe(6000);
    expect(service.activityCards()[0].change).toBe(100); // 6000 vs 3000 steps
  });

  it('shows the latest workouts and counts those of today', async () => {
    const done = service.load();
    answer(week(), [workout(2, new Date().toISOString()), workout(1, '2020-01-01T08:00:00Z')]);
    await done;
    const recent = service.recentWorkouts();
    expect(recent.map((w) => w.id)).toEqual([2, 1]);
    expect(recent[0]).toMatchObject({ kind: 'Run', durationMin: 32, calories: 352 });
    expect(recent[0].when).toMatch(/^Today, \d\d:\d\d$/);
    expect(service.workoutsToday()).toBe(1);
  });

  it('reports an error when the server is not reachable, and recovers on retry', async () => {
    const failed = service.load();
    answer('fail');
    await failed;
    expect(service.error()).toContain('Cannot reach the server');

    const retry = service.load();
    answer(week());
    await retry;
    expect(service.error()).toBe('');
    expect(service.today().steps).toBe(7482);
  });

  it('keeps the page working when only the latest-workouts request fails', async () => {
    const done = service.load();
    http.expectOne('/api/v1/dashboard').flush({ user_id: 1, week: week() });
    http.expectOne((r) => r.url === '/api/v1/workouts').flush('x', { status: 500, statusText: 'Server Error' });
    await done;
    expect(service.error()).toBe('');
    expect(service.today().steps).toBe(7482);
    expect(service.recentWorkouts()).toEqual([]);
  });
});
