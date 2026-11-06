import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import { emailValidators, errorMessage } from '../../../core/validators/app-validators';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './login.html',
  styleUrl: '../auth-form.scss',
})
export class Login {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly form = inject(FormBuilder).nonNullable.group({
    email: ['', emailValidators],
    password: ['', [Validators.required]],
  });

  protected readonly showPassword = signal(false);
  protected readonly submitting = signal(false);
  protected readonly serverError = signal('');

  protected error(name: 'email' | 'password'): string {
    const c = this.form.controls[name];
    return c.touched || c.dirty ? errorMessage(c, name === 'email' ? 'Email' : 'Password') : '';
  }

  protected async submit(): Promise<void> {
    this.serverError.set('');
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.submitting.set(true);
    const { email, password } = this.form.getRawValue();
    const result = await this.auth.login(email, password);
    this.submitting.set(false);
    if (result.ok) await this.router.navigateByUrl('/dashboard');
    else this.serverError.set(result.error);
  }
}
