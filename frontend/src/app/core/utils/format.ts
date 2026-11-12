/** Small formatting helpers shared by the Activity, History and Dashboard pages. */

/** 3725 -> "01:02:05" (timer) */
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(h)}:${pad(m)}:${pad(s % 60)}`;
}

/** 1920 -> "32 min", 3725 -> "1 h 02 min", 45 -> "45 s" */
export function formatDuration(totalSeconds: number | null): string {
  if (totalSeconds === null) return '—';
  const s = Math.max(0, Math.round(totalSeconds));
  if (s < 60) return `${s} s`;
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  if (h === 0) return `${m} min`;
  return `${h} h ${String(m).padStart(2, '0')} min`;
}

const time = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit' });
const weekday = new Intl.DateTimeFormat('en-US', { weekday: 'short' });
const dayMonth = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' });
const full = new Intl.DateTimeFormat('en-US', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** "Today, 07:30" / "Yesterday, 18:10" / "Tue, 17:45" (last 6 days) / "3 Nov, 08:00" (local time) */
export function formatWhen(iso: string, now: Date = new Date()): string {
  const d = new Date(iso);
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const t = time.format(d);
  if (sameDay(d, now)) return `Today, ${t}`;
  if (sameDay(d, yesterday)) return `Yesterday, ${t}`;
  const ageDays = (now.getTime() - d.getTime()) / 86_400_000;
  return ageDays < 6 ? `${weekday.format(d)}, ${t}` : `${dayMonth.format(d)}, ${t}`;
}

/** "Tuesday, 3 November 2026" */
export function formatFullDate(iso: string): string {
  return full.format(new Date(iso));
}

/** "07:30" */
export function formatTime(iso: string): string {
  return time.format(new Date(iso));
}
