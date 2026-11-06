import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Login } from './login';

describe('Login page', () => {
  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({ imports: [Login], providers: [provideRouter([])] }).compileComponents();
  });

  function setup() {
    const f = TestBed.createComponent(Login);
    f.detectChanges();
    return { f, el: f.nativeElement as HTMLElement };
  }

  it('shows validation errors when submitting an empty form', async () => {
    const { f, el } = setup();
    el.querySelector('form')!.dispatchEvent(new Event('submit'));
    await f.whenStable();
    f.detectChanges();
    const text = el.textContent!;
    expect(text).toContain('Email is required.');
    expect(text).toContain('Password is required.');
  });

  it('shows an error for a wrong email format', async () => {
    const { f, el } = setup();
    const input = el.querySelector<HTMLInputElement>('#email')!;
    input.value = 'not-an-email';
    input.dispatchEvent(new Event('input'));
    input.dispatchEvent(new Event('blur'));
    await f.whenStable();
    f.detectChanges();
    expect(el.textContent).toContain('Enter a valid email');
  });
});
