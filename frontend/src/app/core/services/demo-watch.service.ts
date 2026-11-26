import { Injectable, effect, inject, signal, untracked } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { describeHttpError } from '../http/error-message';
import { SyncApiService } from './api/sync-api.service';
import { AuthService } from './auth.service';
import {
  BatchSender,
  DashboardRefreshThrottler,
  HrSample,
  appendHrSample,
} from './batch-sender';

export type DemoWatchStatus = 'idle' | 'starting' | 'running' | 'error';

export const DEMO_TICK_MS = 3_000;
export const DEMO_STEPS_INTERVAL_MS = 10_000;
export const DEMO_NORMAL_BASE_BPM = 72;
export const DEMO_HIGH_HR_BASE_BPM = 110;
export const DEMO_HIGH_HR_DURATION_MS = 180_000;
export const DEMO_HR_MIN = 55;
export const DEMO_HR_MAX = 120;

/**
 * Simulated wrist watch that streams realistic heart rate (every 3s) and steps (every 10s)
 * through the shared BatchSender to POST /api/v1/sync/batch.
 */
@Injectable({ providedIn: 'root' })
export class DemoWatchService {
  private readonly syncApi = inject(SyncApiService);
  private readonly auth = inject(AuthService);
  private readonly refreshThrottler = inject(DashboardRefreshThrottler);

  readonly status = signal<DemoWatchStatus>('idle');
  readonly bpm = signal<number | null>(null);
  readonly highHrActive = signal(false);
  readonly lastSentAt = signal<Date | null>(null);
  readonly error = signal('');
  readonly deviceId = signal<number | null>(null);
  readonly history = signal<HrSample[]>([]);

  private readonly batchSender = new BatchSender(this.syncApi, {
    onSent: (at) => this.lastSentAt.set(at),
    onRefresh: () => this.refreshThrottler.requestRefresh(),
    onError: (err) => {
      this.error.set(
        describeHttpError(err, 'Failed to sync demo watch readings. Retrying automatically.'),
      );
    },
  });

  private tickTimer: ReturnType<typeof setInterval> | null = null;
  private highHrTimer: ReturnType<typeof setTimeout> | null = null;
  private currentBpm = DEMO_NORMAL_BASE_BPM;
  private currentBase = DEMO_NORMAL_BASE_BPM;
  private targetBase = DEMO_NORMAL_BASE_BPM;
  private lastStepsAtMs = 0;

  constructor() {
    let wasLoggedIn = this.auth.isLoggedIn();
    effect(() => {
      const loggedIn = this.auth.isLoggedIn();
      if (wasLoggedIn && !loggedIn) {
        untracked(() => {
          void this.stop();
        });
      }
      wasLoggedIn = loggedIn;
    });
  }

  get pendingCount(): number {
    return this.batchSender.pendingCount;
  }

  async start(deviceId?: number): Promise<void> {
    if (this.status() === 'running' || this.status() === 'starting') return;

    this.error.set('');
    this.status.set('starting');

    try {
      const resolvedDeviceId =
        deviceId ??
        (await firstValueFrom(this.syncApi.ensureDevice('demo', 'Demo Watch'))).device_id;

      this.deviceId.set(resolvedDeviceId);
      this.currentBpm = DEMO_NORMAL_BASE_BPM;
      this.currentBase = DEMO_NORMAL_BASE_BPM;
      this.targetBase = DEMO_NORMAL_BASE_BPM;
      this.highHrActive.set(false);
      this.lastStepsAtMs = 0;

      this.batchSender.start(resolvedDeviceId);
      this.status.set('running');

      this.emitTick();
      this.tickTimer = setInterval(() => this.emitTick(), DEMO_TICK_MS);
    } catch (err) {
      this.status.set('error');
      this.error.set(describeHttpError(err, 'Could not start the demo watch simulator.'));
    }
  }

  simulateHighHr(durationMs = DEMO_HIGH_HR_DURATION_MS): void {
    if (this.status() !== 'running') return;

    this.highHrActive.set(true);
    this.targetBase = DEMO_HIGH_HR_BASE_BPM;
    if (this.highHrTimer !== null) {
      clearTimeout(this.highHrTimer);
    }
    this.highHrTimer = setTimeout(() => {
      this.highHrTimer = null;
      this.targetBase = DEMO_NORMAL_BASE_BPM;
      this.highHrActive.set(false);
    }, durationMs);
  }

  async stop(): Promise<void> {
    if (this.tickTimer !== null) {
      clearInterval(this.tickTimer);
      this.tickTimer = null;
    }
    if (this.highHrTimer !== null) {
      clearTimeout(this.highHrTimer);
      this.highHrTimer = null;
    }

    await this.batchSender.stop({ flushRemaining: true });
    this.highHrActive.set(false);
    this.bpm.set(null);
    this.deviceId.set(null);
    this.error.set('');
    this.status.set('idle');
  }

  private emitTick(): void {
    const nowMs = Date.now();
    const baseDiff = this.targetBase - this.currentBase;
    if (baseDiff !== 0) {
      this.currentBase += Math.sign(baseDiff) * Math.min(Math.abs(baseDiff), 8);
    }

    const direction = Math.random() < 0.5 ? -1 : 1;
    const step = direction * (1 + Math.floor(Math.random() * 3));
    const drift = Math.round((this.currentBase - this.currentBpm) * 0.25);
    const nextBpm = Math.max(
      DEMO_HR_MIN,
      Math.min(DEMO_HR_MAX, this.currentBpm + step + drift),
    );
    this.currentBpm = nextBpm;

    this.bpm.set(nextBpm);
    this.history.update((items) => appendHrSample(items, nextBpm, nowMs));

    let steps: number | undefined;
    let calories: number | undefined;
    if (this.lastStepsAtMs === 0 || nowMs - this.lastStepsAtMs >= DEMO_STEPS_INTERVAL_MS) {
      this.lastStepsAtMs = nowMs;
      steps = this.highHrActive()
        ? 20 + Math.floor(Math.random() * 16)
        : 8 + Math.floor(Math.random() * 11);
      calories = Math.round(steps * 0.045 * 100) / 100;
    }

    this.batchSender.enqueue({
      timestampMs: nowMs,
      heart_rate_bpm: nextBpm,
      steps,
      calories_kcal: calories,
    });
  }
}
