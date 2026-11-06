import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import {
  LIMITS, birthDate, emailValidators, errorMessage, fieldsMatch, notBlank, passwordStrength,
} from '../../../core/validators/app-validators';

type Field = 'fullName' | 'birthDate' | 'email' | 'password' | 'confirmPassword';

const LABELS: Record<Field, string> = {
  fullName: 'Full name',
  birthDate: 'Date of birth',
  email: 'Email',
  password: 'Password',
  confirmPassword: 'Password confirmation',
};

@Component({
  selector: 'app-register',
  imports: [ReactiveFormsModule, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './register.html',
  styleUrl: '../auth-form.scss',
})
export class Register {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  /** Used by the date input (max attribute) so future dates cannot be picked. */
  protected readonly today = new Date().toISOString().slice(0, 10);
  protected readonly limits = LIMITS;

  protected readonly form = inject(FormBuilder).nonNullable.group(
    {
      fullName: ['', [Validators.required, notBlank, Validators.maxLength(LIMITS.fullNameMax)]],
      birthDate: ['', [Validators.required, birthDate]],
      email: ['', emailValidators],
      password: ['', [
        Validators.required,
        Validators.minLength(LIMITS.passwordMin),
        Validators.maxLength(LIMITS.passwordMax),
        passwordStrength,
      ]],
      confirmPassword: ['', [Validators.required]],
    },
    { validators: fieldsMatch('password', 'confirmPassword') },
  );

  protected readonly showPassword = signal(false);
  protected readonly submitting = signal(false);
  protected readonly serverError = signal('');

  protected error(name: Field): string {
    const c = this.form.controls[name];
    if (!(c.touched || c.dirty)) return '';
    if (name === 'confirmPassword' && !c.errors && this.form.errors?.['mismatch']) {
      return 'Passwords do not match.';
    }
    return errorMessage(c, LABELS[name]);
  }

  protected async submit(): Promise<void> {
    this.serverError.set('');
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.submitting.set(true);
    const { fullName, birthDate, email, password } = this.form.getRawValue();
    const result = await this.auth.register({ fullName, birthDate, email, password });
    this.submitting.set(false);
    if (result.ok) await this.router.navigateByUrl('/dashboard');
    else this.serverError.set(result.error);
  }
}
