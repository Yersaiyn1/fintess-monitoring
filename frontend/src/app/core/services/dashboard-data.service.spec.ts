import { TestBed } from '@angular/core/testing';
import { DashboardDataService } from './dashboard-data.service';

describe('DashboardDataService', () => {
  let service: DashboardDataService;
  beforeEach(() => { service = TestBed.inject(DashboardDataService); });

  it('provides 7 days of mock data, with today last', () => {
    expect(service.week().length).toBe(7);
    expect(service.today()).toBe(service.week()[6]);
  });

  it('calculates step progress and remaining steps', () => {
    expect(service.stepsProgress()).toBeCloseTo(7482 / 10000, 4);
    expect(service.stepsRemaining()).toBe(2518);
  });

  it('builds four stat cards', () => {
    expect(service.statCards().map((c) => c.id)).toEqual(['calories', 'distance', 'active', 'workouts']);
  });
});
