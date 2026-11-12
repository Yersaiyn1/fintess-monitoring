import { formatClock, formatDuration, formatWhen } from './format';

describe('format helpers', () => {
  it('formats the timer as HH:MM:SS', () => {
    expect(formatClock(0)).toBe('00:00:00');
    expect(formatClock(65)).toBe('00:01:05');
    expect(formatClock(3725)).toBe('01:02:05');
    expect(formatClock(-5)).toBe('00:00:00');
  });

  it('formats durations for lists', () => {
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(45)).toBe('45 s');
    expect(formatDuration(1920)).toBe('32 min');
    expect(formatDuration(3725)).toBe('1 h 02 min');
  });

  it('says Today / Yesterday / weekday / date', () => {
    const now = new Date(2026, 10, 12, 15, 0); // local time
    expect(formatWhen(new Date(2026, 10, 12, 7, 30).toISOString(), now)).toBe('Today, 07:30');
    expect(formatWhen(new Date(2026, 10, 11, 18, 10).toISOString(), now)).toBe('Yesterday, 18:10');
    expect(formatWhen(new Date(2026, 10, 9, 17, 45).toISOString(), now)).toBe('Mon, 17:45');
    expect(formatWhen(new Date(2026, 9, 20, 8, 0).toISOString(), now)).toBe('20 Oct, 08:00');
  });
});
