import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { DashboardRefreshThrottler } from './batch-sender';
import {
  BluetoothHrService,
  parseHeartRateMeasurement,
} from './bluetooth-hr.service';

interface MockCharacteristic {
  value: DataView | null;
  startNotifications: ReturnType<typeof vi.fn>;
  stopNotifications: ReturnType<typeof vi.fn>;
  addEventListener: (type: string, listener: EventListener) => void;
  removeEventListener: (type: string, listener: EventListener) => void;
  emit: (bytes: number[]) => void;
}

interface MockBluetoothHandle {
  device: BluetoothDevice;
  characteristic: MockCharacteristic;
  gattConnect: ReturnType<typeof vi.fn>;
  requestDevice: ReturnType<typeof vi.fn>;
  triggerDisconnect: () => void;
}

function createMockBluetooth(name = 'Polar H10'): MockBluetoothHandle {
  const charListeners = new Map<string, Set<EventListener>>();
  const devListeners = new Map<string, Set<EventListener>>();

  const characteristic: MockCharacteristic = {
    value: null,
    startNotifications: vi.fn().mockResolvedValue(undefined),
    stopNotifications: vi.fn().mockResolvedValue(undefined),
    addEventListener(type: string, listener: EventListener) {
      const set = charListeners.get(type) ?? new Set<EventListener>();
      set.add(listener);
      charListeners.set(type, set);
    },
    removeEventListener(type: string, listener: EventListener) {
      charListeners.get(type)?.delete(listener);
    },
    emit(bytes: number[]) {
      characteristic.value = new DataView(new Uint8Array(bytes).buffer);
      const evt = { target: characteristic } as unknown as Event;
      for (const listener of charListeners.get('characteristicvaluechanged') ?? []) {
        listener(evt);
      }
    },
  };

  const server = {
    getPrimaryService: vi.fn().mockResolvedValue({
      getCharacteristic: vi.fn().mockResolvedValue(characteristic),
    }),
  };

  const gatt = {
    connected: false,
    connect: vi.fn().mockImplementation(async () => {
      gatt.connected = true;
      return server;
    }),
    disconnect: vi.fn().mockImplementation(() => {
      gatt.connected = false;
    }),
  };

  const device = {
    name,
    gatt,
    addEventListener(type: string, listener: EventListener) {
      const set = devListeners.get(type) ?? new Set<EventListener>();
      set.add(listener);
      devListeners.set(type, set);
    },
    removeEventListener(type: string, listener: EventListener) {
      devListeners.get(type)?.delete(listener);
    },
  } as unknown as BluetoothDevice;

  const requestDevice = vi.fn().mockResolvedValue(device);

  return {
    device,
    characteristic,
    gattConnect: gatt.connect,
    requestDevice,
    triggerDisconnect() {
      gatt.connected = false;
      const evt = new Event('gattserverdisconnected');
      for (const listener of devListeners.get('gattserverdisconnected') ?? []) {
        listener(evt);
      }
    },
  };
}

describe('parseHeartRateMeasurement', () => {
  it('parses uint8 heart rate values and validates range 30..220', () => {
    expect(parseHeartRateMeasurement(new DataView(new Uint8Array([0x00, 72]).buffer))).toBe(72);
    expect(parseHeartRateMeasurement(new DataView(new Uint8Array([0x00, 30]).buffer))).toBe(30);
    expect(parseHeartRateMeasurement(new DataView(new Uint8Array([0x00, 220]).buffer))).toBe(220);
    expect(parseHeartRateMeasurement(new DataView(new Uint8Array([0x00, 0]).buffer))).toBeNull();
    expect(parseHeartRateMeasurement(new DataView(new Uint8Array([0x00, 29]).buffer))).toBeNull();
    expect(parseHeartRateMeasurement(new DataView(new Uint8Array([0x00, 221]).buffer))).toBeNull();
    expect(parseHeartRateMeasurement(new DataView(new Uint8Array([0x00]).buffer))).toBeNull();
  });

  it('parses little-endian uint16 heart rate values when flag bit 0 is set', () => {
    // 0x00C8 = 200 (little-endian: 0xC8, 0x00)
    expect(
      parseHeartRateMeasurement(new DataView(new Uint8Array([0x01, 0xc8, 0x00]).buffer)),
    ).toBe(200);
    // 0x0100 = 256 -> out of range
    expect(
      parseHeartRateMeasurement(new DataView(new Uint8Array([0x01, 0x00, 0x01]).buffer)),
    ).toBeNull();
    // Truncated uint16 buffer
    expect(parseHeartRateMeasurement(new DataView(new Uint8Array([0x01, 0x50]).buffer))).toBeNull();
  });
});

describe('BluetoothHrService', () => {
  let service: BluetoothHrService;
  let http: HttpTestingController;
  let originalBluetoothDesc: PropertyDescriptor | undefined;
  let originalSecureContextDesc: PropertyDescriptor | undefined;

  function setBluetoothMock(value: unknown): void {
    Object.defineProperty(navigator, 'bluetooth', {
      configurable: true,
      writable: true,
      value,
    });
  }

  function removeBluetoothMock(): void {
    if (originalBluetoothDesc) {
      Object.defineProperty(navigator, 'bluetooth', originalBluetoothDesc);
    } else {
      delete (navigator as unknown as Record<string, unknown>)['bluetooth'];
    }
  }

  function setSecureContext(value: boolean): void {
    Object.defineProperty(window, 'isSecureContext', {
      configurable: true,
      writable: true,
      value,
    });
  }

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-26T12:00:00.100Z'));
    localStorage.clear();
    const payload = btoa(JSON.stringify({ sub: '1', exp: Math.floor(Date.now() / 1000) + 3600 }));
    localStorage.setItem(
      'pulse.session',
      JSON.stringify({
        token: `x.${payload}.y`,
        user: { id: 1, fullName: 'Ana B', email: 'a@b.co', birthDate: '2000-01-01' },
      }),
    );

    originalBluetoothDesc = Object.getOwnPropertyDescriptor(navigator, 'bluetooth');
    originalSecureContextDesc = Object.getOwnPropertyDescriptor(window, 'isSecureContext');
    setSecureContext(true);

    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    TestBed.inject(DashboardRefreshThrottler).reset();
    service = TestBed.inject(BluetoothHrService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(async () => {
    if (service.status() !== 'idle') {
      const disconnecting = service.disconnect();
      await vi.advanceTimersByTimeAsync(0);
      for (const req of http.match('/api/v1/sync/batch')) {
        req.flush({ device_id: 1, synced_count: 0, skipped_count: 0 });
      }
      await disconnecting;
    }
    vi.useRealTimers();
    removeBluetoothMock();
    if (originalSecureContextDesc) {
      Object.defineProperty(window, 'isSecureContext', originalSecureContextDesc);
    }
    http.verify();
  });

  it('requires HTTPS or localhost when context is insecure', async () => {
    setBluetoothMock({ requestDevice: vi.fn() });
    setSecureContext(false);

    await service.connect();

    expect(service.status()).toBe('idle');
    expect(service.error()).toContain('HTTPS or localhost');
  });

  it('returns to idle without an error when the user cancels requestDevice (NotFoundError)', async () => {
    const err = Object.assign(new Error('User cancelled'), { name: 'NotFoundError' });
    setBluetoothMock({ requestDevice: vi.fn().mockRejectedValue(err) });

    await service.connect();

    expect(service.status()).toBe('idle');
    expect(service.error()).toBe('');
  });

  it('deduplicates readings per UTC second, flushes on 15s timer, and ignores out-of-range HR', async () => {
    const mock = createMockBluetooth();
    setBluetoothMock({ requestDevice: mock.requestDevice });

    const connecting = service.connect();
    await vi.advanceTimersByTimeAsync(0);
    const ensureReq = http.expectOne('/api/v1/sync/devices/ensure');
    expect(ensureReq.request.body).toEqual({ provider: 'bluetooth', name: 'Polar H10' });
    ensureReq.flush({
      device_id: 7,
      user_id: 1,
      model: 'Polar H10',
      serial_number: 'BLE-1',
      provider: 'bluetooth',
      is_active: true,
      last_sync_time: null,
    });
    await connecting;

    expect(service.status()).toBe('connected');

    // Out-of-range (0 = no skin contact) is ignored
    mock.characteristic.emit([0x00, 0]);
    expect(service.bpm()).toBeNull();

    // Two readings in the same UTC second -> deduplicated to the latest one
    mock.characteristic.emit([0x00, 74]);
    vi.setSystemTime(new Date('2026-11-26T12:00:00.800Z'));
    mock.characteristic.emit([0x00, 78]);
    expect(service.bpm()).toBe(78);
    expect(service.pendingCount).toBe(1);

    // Advance 15s -> triggers batch upload and dashboard refresh
    await vi.advanceTimersByTimeAsync(15_000);
    const batchReq = http.expectOne('/api/v1/sync/batch');
    expect(batchReq.request.body).toEqual({
      device_id: 7,
      readings: [
        {
          device_id: 7,
          date_time: '2026-11-26T12:00:00Z',
          heart_rate_bpm: 78,
        },
      ],
    });
    batchReq.flush({ device_id: 7, synced_count: 1, skipped_count: 0 });
    await vi.advanceTimersByTimeAsync(0);

    http.expectOne('/api/v1/dashboard').flush({ user_id: 1, week: [] });
    http
      .expectOne((r) => r.url === '/api/v1/workouts')
      .flush({ items: [], total: 0, limit: 4, offset: 0 });

    expect(service.pendingCount).toBe(0);
    expect(service.lastSentAt()).not.toBeNull();

    // Another reading flushed on disconnect()
    vi.setSystemTime(new Date('2026-11-26T12:00:18.000Z'));
    mock.characteristic.emit([0x00, 82]);
    const disconnecting = service.disconnect();
    await vi.advanceTimersByTimeAsync(0);
    const finalReq = http.expectOne('/api/v1/sync/batch');
    expect(finalReq.request.body.readings).toEqual([
      {
        device_id: 7,
        date_time: '2026-11-26T12:00:18Z',
        heart_rate_bpm: 82,
      },
    ]);
    finalReq.flush({ device_id: 7, synced_count: 1, skipped_count: 0 });
    await disconnecting;

    expect(service.status()).toBe('idle');
    expect(service.bpm()).toBeNull();
  });

  it('restores failed batch into buffer and backs off on network errors', async () => {
    const mock = createMockBluetooth();
    setBluetoothMock({ requestDevice: mock.requestDevice });

    await service.connect(9);
    mock.characteristic.emit([0x00, 80]);
    expect(service.pendingCount).toBe(1);

    // First 15s flush fails -> buffer restored, backoff set for 15s
    await vi.advanceTimersByTimeAsync(15_000);
    http.expectOne('/api/v1/sync/batch').error(new ProgressEvent('error'));
    await vi.advanceTimersByTimeAsync(0);
    expect(service.pendingCount).toBe(1);

    // Next 15s tick occurs right as backoff expires or fails again -> second failure sets 30s backoff
    await vi.advanceTimersByTimeAsync(15_000);
    http.expectOne('/api/v1/sync/batch').error(new ProgressEvent('error'));
    await vi.advanceTimersByTimeAsync(0);

    // 15s later (only 15s into 30s backoff) -> must NOT spam backend
    await vi.advanceTimersByTimeAsync(15_000);
    http.expectNone('/api/v1/sync/batch');

    // Another 15s (30s elapsed) -> retries and succeeds
    await vi.advanceTimersByTimeAsync(15_000);
    const retryReq = http.expectOne('/api/v1/sync/batch');
    retryReq.flush({ device_id: 9, synced_count: 1, skipped_count: 0 });
    await vi.advanceTimersByTimeAsync(0);
    http.expectOne('/api/v1/dashboard').flush({ user_id: 1, week: [] });
    http
      .expectOne((r) => r.url === '/api/v1/workouts')
      .flush({ items: [], total: 0, limit: 4, offset: 0 });

    expect(service.pendingCount).toBe(0);
  });

  it('reconnects on gattserverdisconnected and enters error state after 5 failed attempts', async () => {
    const mock = createMockBluetooth();
    setBluetoothMock({ requestDevice: mock.requestDevice });

    await service.connect(11);
    expect(service.status()).toBe('connected');

    // Simulate link drop where first reconnect fails and second succeeds
    mock.gattConnect
      .mockRejectedValueOnce(new Error('transient'))
      .mockImplementationOnce(async () => {
        return {
          getPrimaryService: vi.fn().mockResolvedValue({
            getCharacteristic: vi.fn().mockResolvedValue(mock.characteristic),
          }),
        };
      });

    mock.triggerDisconnect();
    expect(service.status()).toBe('reconnecting');

    await vi.advanceTimersByTimeAsync(1_000);
    expect(service.status()).toBe('reconnecting');

    await vi.advanceTimersByTimeAsync(2_000);
    expect(service.status()).toBe('connected');

    // Now fail all 5 reconnect attempts (1 + 2 + 4 + 8 + 16 = 31s)
    mock.gattConnect.mockRejectedValue(new Error('offline'));
    mock.triggerDisconnect();
    expect(service.status()).toBe('reconnecting');

    await vi.advanceTimersByTimeAsync(31_000);
    expect(service.status()).toBe('error');
    expect(service.canReconnect()).toBe(true);
  });
});
