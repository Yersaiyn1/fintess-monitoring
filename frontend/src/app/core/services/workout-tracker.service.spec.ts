import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivityType, Workout } from '../models/workout.model';
import { WorkoutTrackerService } from './workout-tracker.service';

const TYPES: ActivityType[] = [
  { kind: 'Run', label: 'Run', stepsPerMin: 160, kmPerMin: 0.16, kcalPerMin: 11 },
  { kind: 'Yoga', label: 'Yoga', stepsPerMin: 0, kmPerMin: 0, kcalPerMin: 3 },
];

function running(startedAt: Date, kind: Workout['kind'] = 'Run'): Workout {
  return { id: 5, kind, startedAt: startedAt.toISOString(), endedAt: null, durationSec: null, steps: 0, distanceKm: 0, caloriesKcal: 0, inProgress: true };
}

function session(): void {
  const payload = btoa(JSON.stringify({ sub: '1', exp: Math.floor(Date.now() / 1000) + 3600 }));
  localStorage.setItem('pulse.session', JSON.stringify({
    token: `x.${payload}.y`, user: { id: 1, fullName: 'Ana B', email: 'a@b.co', birthDate: '2000-01-01' },
  }));
}

describe('WorkoutTrackerService', () => {
  let tracker: WorkoutTrackerService;
  let http: HttpTestingController;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-12T10:00:00Z'));
    localStorage.clear();
    session();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    tracker = TestBed.inject(WorkoutTrackerService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    vi.useRealTimers();
    http.verify();
  });

  /** Opens the page: loads the types and the (maybe running) workout. */
  async function init(active: Workout | null = null): Promise<void> {
    const done = tracker.init();
    http.expectOne('/api/v1/workouts/types').flush(TYPES);
    http.expectOne('/api/v1/workouts/active').flush(active);
    await done;
  }

  it('loads the activity types and is ready', async () => {
    await init();
    expect(tracker.types().length).toBe(2);
    expect(tracker.ready()).toBe(true);
    expect(tracker.isRunning()).toBe(false);
  });

  it('start -> the timer counts seconds -> stop saves and refreshes the dashboard', async () => {
    await init();
    tracker.select('Run');

    const starting = tracker.start();
    const req = http.expectOne('/api/v1/workouts/start');
    expect(req.request.body).toEqual({ kind: 'Run' });
    req.flush(running(new Date('2026-11-12T10:00:00Z')));
    await starting;
    expect(tracker.isRunning()).toBe(true);

    vi.advanceTimersByTime(90_000); // 1 min 30 s
    expect(tracker.elapsedSec()).toBe(90);
    expect(tracker.live()).toEqual({ steps: 240, km: 0.24, kcal: 16.5 }); // estimates from the backend rates

    const stopping = tracker.stop();
    http.expectOne('/api/v1/workouts/5/stop').flush({ ...running(new Date()), endedAt: new Date().toISOString(), durationSec: 90, steps: 240, distanceKm: 0.24, caloriesKcal: 16.5, inProgress: false });
    await vi.advanceTimersByTimeAsync(0);
    http.expectOne('/api/v1/dashboard').flush({ user_id: 1, week: [] });
    http.expectOne((r) => r.url === '/api/v1/workouts').flush({ items: [], total: 0, limit: 4, offset: 0 });
    await stopping;

    expect(tracker.isRunning()).toBe(false);
    expect(tracker.lastResult()?.steps).toBe(240);
    expect(tracker.elapsedSec()).toBe(0);
  });

  it('continues a workout that is already running (after a page refresh)', async () => {
    vi.setSystemTime(new Date('2026-11-12T10:20:00Z'));
    await init(running(new Date('2026-11-12T10:00:00Z'), 'Yoga'));
    expect(tracker.isRunning()).toBe(true);
    expect(tracker.selectedKind()).toBe('Yoga');
    expect(tracker.elapsedSec()).toBe(1200);
  });

  it('does not let the user change the type while a workout runs', async () => {
    await init(running(new Date(), 'Run'));
    tracker.select('Yoga');
    expect(tracker.selectedKind()).toBe('Run');
  });

  it('never shows a negative time when the PC clock is behind the server', async () => {
    await init(running(new Date('2026-11-12T10:00:30Z')));
    expect(tracker.elapsedSec()).toBe(0);
  });

  it('shows the server message and the real state when starting fails (already running)', async () => {
    await init();
    const starting = tracker.start();
    http.expectOne('/api/v1/workouts/start').flush({ detail: 'A workout is already in progress. Stop it first.' }, { status: 409, statusText: 'Conflict' });
    await vi.advanceTimersByTimeAsync(0);
    http.expectOne('/api/v1/workouts/active').flush(running(new Date()));
    await starting;
    expect(tracker.isRunning()).toBe(true);
    expect(tracker.error()).toBe('A workout is already in progress. Stop it first.');
  });
});
