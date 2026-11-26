import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { SyncApiService, SyncReadingInput } from './api/sync-api.service';
import { DashboardDataService } from './dashboard-data.service';

export interface HrSample {
  timeMs: number;
  bpm: number;
}

export const HR_MIN = 30;
export const HR_MAX = 220;
export const HR_HISTORY_WINDOW_MS = 120_000;
export const FLUSH_INTERVAL_MS = 15_000;
export const MAX_BUFFER_SIZE = 5_000;
export const MAX_BACKOFF_MS = 300_000;
export const DASHBOARD_REFRESH_MIN_MS = 30_000;

/**
 * Formats a timestamp (ms) rounded down to whole UTC seconds for backend deduplication.
 */
export function toUtcSecondIso(timestampMs: number): string {
  const secMs = Math.floor(timestampMs / 1000) * 1000;
  return new Date(secMs).toISOString().replace('.000Z', 'Z');
}

/**
 * Appends a sample to a rolling 2-minute heart-rate history list.
 */
export function appendHrSample(
  current: HrSample[],
  bpm: number,
  nowMs = Date.now(),
  windowMs = HR_HISTORY_WINDOW_MS,
): HrSample[] {
  const cutoff = nowMs - windowMs;
  const pruned = current.filter((sample) => sample.timeMs >= cutoff);
  return [...pruned, { timeMs: nowMs, bpm }];
}

/**
 * Throttles dashboard reloads so live streaming sources refresh at most once every 30s.
 */
@Injectable({ providedIn: 'root' })
export class DashboardRefreshThrottler {
  private readonly dashboard = inject(DashboardDataService);
  private lastRefreshAt = 0;

  requestRefresh(now = Date.now()): void {
    if (now - this.lastRefreshAt < DASHBOARD_REFRESH_MIN_MS) return;
    this.lastRefreshAt = now;
    void this.dashboard.load();
  }

  reset(): void {
    this.lastRefreshAt = 0;
  }
}

export interface BatchSenderCallbacks {
  onSent?: (at: Date) => void;
  onError?: (err: unknown) => void;
  onRefresh?: () => void;
}

export interface EnqueueReadingInput {
  timestampMs?: number;
  heart_rate_bpm?: number | null;
  steps?: number | null;
  calories_kcal?: number | null;
  blood_pressure?: string | null;
}

/**
 * Shared buffered batch sender with per-second UTC deduplication, bounded capacity,
 * periodic 15s flushing, and exponential backoff on network errors.
 */
export class BatchSender {
  private readonly buffer = new Map<string, SyncReadingInput>();
  private deviceId: number | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private inFlight: Promise<boolean> | null = null;
  private consecutiveFailures = 0;
  private nextAllowedAt = 0;

  constructor(
    private readonly syncApi: SyncApiService,
    private readonly callbacks: BatchSenderCallbacks = {},
  ) {}

  get pendingCount(): number {
    return this.buffer.size;
  }

  start(deviceId: number): void {
    this.deviceId = deviceId;
    this.consecutiveFailures = 0;
    this.nextAllowedAt = 0;
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = setInterval(() => {
      void this.flush();
    }, FLUSH_INTERVAL_MS);
  }

  enqueue(input: EnqueueReadingInput): boolean {
    const validHr =
      input.heart_rate_bpm !== undefined &&
      input.heart_rate_bpm !== null &&
      Number.isFinite(input.heart_rate_bpm) &&
      input.heart_rate_bpm >= HR_MIN &&
      input.heart_rate_bpm <= HR_MAX
        ? Math.round(input.heart_rate_bpm)
        : undefined;

    const validSteps =
      input.steps !== undefined && input.steps !== null && Number.isFinite(input.steps) && input.steps >= 0
        ? Math.round(input.steps)
        : undefined;

    const validCalories =
      input.calories_kcal !== undefined &&
      input.calories_kcal !== null &&
      Number.isFinite(input.calories_kcal) &&
      input.calories_kcal >= 0
        ? input.calories_kcal
        : undefined;

    const validBp = input.blood_pressure ? input.blood_pressure : undefined;

    if (
      validHr === undefined &&
      validSteps === undefined &&
      validCalories === undefined &&
      validBp === undefined
    ) {
      return false;
    }

    const key = toUtcSecondIso(input.timestampMs ?? Date.now());
    const prev = this.buffer.get(key);
    const merged: SyncReadingInput = {
      ...(prev ?? { date_time: key }),
      date_time: key,
    };

    if (validHr !== undefined) merged.heart_rate_bpm = validHr;
    if (validSteps !== undefined) merged.steps = validSteps;
    if (validCalories !== undefined) merged.calories_kcal = validCalories;
    if (validBp !== undefined) merged.blood_pressure = validBp;

    if (prev !== undefined) {
      this.buffer.delete(key);
    }
    this.buffer.set(key, merged);
    this.trimToMax();
    return true;
  }

  async flush(options?: { ignoreBackoff?: boolean }): Promise<boolean> {
    if (this.inFlight) return this.inFlight;
    if (this.deviceId === null || this.buffer.size === 0) return false;
    if (!options?.ignoreBackoff && Date.now() < this.nextAllowedAt) return false;

    const run = this.executeFlush(this.deviceId);
    this.inFlight = run;
    try {
      return await run;
    } finally {
      if (this.inFlight === run) {
        this.inFlight = null;
      }
    }
  }

  async stop(options?: { flushRemaining?: boolean }): Promise<void> {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
    if (this.inFlight) {
      await this.inFlight;
    }
    if (options?.flushRemaining !== false) {
      await this.flush({ ignoreBackoff: true });
    }
    this.deviceId = null;
  }

  clear(): void {
    this.buffer.clear();
    this.consecutiveFailures = 0;
    this.nextAllowedAt = 0;
  }

  private async executeFlush(deviceId: number): Promise<boolean> {
    const snapshot = Array.from(this.buffer.entries());
    if (snapshot.length === 0) return false;
    this.buffer.clear();

    try {
      await firstValueFrom(
        this.syncApi.batch(
          deviceId,
          snapshot.map(([, reading]) => reading),
        ),
      );
      this.consecutiveFailures = 0;
      this.nextAllowedAt = 0;
      this.callbacks.onSent?.(new Date());
      this.callbacks.onRefresh?.();
      return true;
    } catch (err) {
      this.restoreFailedSnapshot(snapshot);
      this.consecutiveFailures += 1;
      const backoffMs = Math.min(
        FLUSH_INTERVAL_MS * 2 ** (this.consecutiveFailures - 1),
        MAX_BACKOFF_MS,
      );
      this.nextAllowedAt = Date.now() + backoffMs;
      this.callbacks.onError?.(err);
      return false;
    }
  }

  private restoreFailedSnapshot(snapshot: Array<[string, SyncReadingInput]>): void {
    const newerEntries = Array.from(this.buffer.entries());
    this.buffer.clear();
    for (const [key, reading] of snapshot) {
      this.buffer.set(key, reading);
    }
    for (const [key, reading] of newerEntries) {
      this.buffer.delete(key);
      this.buffer.set(key, reading);
    }
    this.trimToMax();
  }

  private trimToMax(): void {
    while (this.buffer.size > MAX_BUFFER_SIZE) {
      const oldestKey = this.buffer.keys().next().value;
      if (oldestKey === undefined) break;
      this.buffer.delete(oldestKey);
    }
  }
}
