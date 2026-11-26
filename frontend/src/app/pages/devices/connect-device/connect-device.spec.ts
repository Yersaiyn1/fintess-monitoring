import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ConnectDevice } from './connect-device';

describe('ConnectDevice', () => {
  let originalBluetoothDesc: PropertyDescriptor | undefined;

  beforeEach(() => {
    originalBluetoothDesc = Object.getOwnPropertyDescriptor(navigator, 'bluetooth');
  });

  afterEach(() => {
    if (originalBluetoothDesc) {
      Object.defineProperty(navigator, 'bluetooth', originalBluetoothDesc);
    } else {
      delete (navigator as unknown as Record<string, unknown>)['bluetooth'];
    }
  });

  it('disables the Bluetooth card and shows the browser hint when Web Bluetooth is unsupported', () => {
    Object.defineProperty(navigator, 'bluetooth', {
      configurable: true,
      writable: true,
      value: undefined,
    });

    TestBed.configureTestingModule({
      imports: [ConnectDevice],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });

    const fixture = TestBed.createComponent(ConnectDevice);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;

    const text = el.textContent ?? '';
    expect(text).toContain('Open in Chrome or Edge (desktop or Android)');
    expect(text).toContain('Demo watch');
    expect(text).toContain('Health Connect file');

    const connectBtn = el.querySelector(
      'button[aria-label="Connect Bluetooth heart rate device"]',
    ) as HTMLButtonElement | null;
    expect(connectBtn).not.toBeNull();
    expect(connectBtn!.disabled).toBe(true);

    const liveStatuses = el.querySelectorAll('[aria-live="polite"]');
    expect(liveStatuses.length).toBeGreaterThanOrEqual(2);

    const hcLink = el.querySelector('a[href="/dashboard"]');
    expect(hcLink).not.toBeNull();
  });
});
