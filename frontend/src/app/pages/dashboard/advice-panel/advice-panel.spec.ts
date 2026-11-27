import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AdviceResponse } from '../../../core/services/api/advice-api.service';
import { AdvicePanel } from './advice-panel';

function makeResponse(overrides: Partial<AdviceResponse> = {}): AdviceResponse {
  return {
    items: [
      {
        code: 'high_hr',
        severity: 'warning',
        title: 'Elevated 7-day heart rate',
        text: 'Your 7-day average heart rate is 110 bpm.',
        data: { avg_hr_7d: 110 },
      },
    ],
    source: 'rules',
    generated_at: '2026-11-26T12:00:00Z',
    disclaimer: 'This is not medical advice.',
    ai_available: false,
    ai_consent: false,
    ...overrides,
  };
}

describe('AdvicePanel', () => {
  let fixture: ComponentFixture<AdvicePanel>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AdvicePanel],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('shows loading state then renders advice cards, AI badge, consent toggle, and disclaimer', async () => {
    fixture = TestBed.createComponent(AdvicePanel);
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Analyzing your recent metrics');

    const req = http.expectOne('/api/v1/advice');
    req.flush(makeResponse({ source: 'ai', ai_available: true, ai_consent: true }));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.querySelector('.ai-badge')?.textContent?.trim()).toBe('AI');
    expect(el.querySelector('.consent-row')).not.toBeNull();
    expect(el.querySelectorAll('.advice-card').length).toBe(1);
    expect(el.querySelector('.advice-card')?.getAttribute('data-severity')).toBe('warning');
    expect(el.querySelector('.disclaimer')?.textContent).toContain('This is not medical advice.');
  });

  it('renders empty state when items list is empty and hides AI controls when unavailable', async () => {
    fixture = TestBed.createComponent(AdvicePanel);
    fixture.detectChanges();

    http.expectOne('/api/v1/advice').flush(makeResponse({ items: [], ai_available: false }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.ai-badge')).toBeNull();
    expect(el.querySelector('.consent-row')).toBeNull();
    expect(el.textContent).toContain('No recommendations right now');
  });

  it('renders error notice on HTTP failure and retries cleanly', async () => {
    fixture = TestBed.createComponent(AdvicePanel);
    fixture.detectChanges();

    http.expectOne('/api/v1/advice').flush('fail', { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    const retryBtn = el.querySelector('.status-box.error button') as HTMLButtonElement | null;
    expect(retryBtn).not.toBeNull();

    retryBtn!.click();
    fixture.detectChanges();
    http.expectOne('/api/v1/advice').flush(makeResponse());
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.querySelectorAll('.advice-card').length).toBe(1);
  });
});
