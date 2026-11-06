import { AbstractControl, ValidationErrors, ValidatorFn, Validators } from '@angular/forms';

/**
 * Validation rules that mirror the database (database/schema.sql):
 *  Users.full_name  VARCHAR(100) NOT NULL
 *  Users.email      VARCHAR(100) NOT NULL UNIQUE
 *  Users.birth_date DATE NOT NULL, not in the future
 */
export const LIMITS = {
  fullNameMax: 100,
  emailMax: 100,
  passwordMin: 8,
  passwordMax: 64,
  minBirthYear: 1900,
} as const;

/** Email format: something@something.tld (no spaces). */
export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/** Field must not be empty or only spaces. */
export const notBlank: ValidatorFn = (c: AbstractControl): ValidationErrors | null =>
  typeof c.value === 'string' && c.value.length > 0 && c.value.trim().length === 0
    ? { blank: true }
    : null;

/** Password: at least one letter and one digit. */
export const passwordStrength: ValidatorFn = (c: AbstractControl): ValidationErrors | null => {
  const v = c.value as string;
  if (!v) return null; // "required" handles empty values
  return /[A-Za-zЀ-ӿ]/.test(v) && /\d/.test(v) ? null : { weakPassword: true };
};

/** Date (yyyy-mm-dd) must be real, not in the future, and not before 1900. */
export const birthDate: ValidatorFn = (c: AbstractControl): ValidationErrors | null => {
  const v = c.value as string;
  if (!v) return null;
  const d = new Date(`${v}T00:00:00`);
  if (Number.isNaN(d.getTime())) return { invalidDate: true };
  if (d > new Date()) return { futureDate: true };
  if (d.getFullYear() < LIMITS.minBirthYear) return { tooOld: true };
  return null;
};

/** Group validator: two fields must have the same value. */
export function fieldsMatch(field: string, confirmField: string): ValidatorFn {
  return (group: AbstractControl): ValidationErrors | null => {
    const a = group.get(field)?.value;
    const b = group.get(confirmField)?.value;
    return a && b && a !== b ? { mismatch: true } : null;
  };
}

export const emailValidators: ValidatorFn[] = [
  Validators.required,
  notBlank,
  Validators.maxLength(LIMITS.emailMax),
  Validators.pattern(EMAIL_PATTERN),
];

/** Human-readable message for the first error of a control, or '' if valid. */
export function errorMessage(control: AbstractControl | null, label: string): string {
  const e = control?.errors;
  if (!e) return '';
  if (e['required'] || e['blank']) return `${label} is required.`;
  if (e['pattern'] || e['email']) return 'Enter a valid email, e.g. name@example.com.';
  if (e['maxlength']) return `${label} must be at most ${e['maxlength'].requiredLength} characters.`;
  if (e['minlength']) return `${label} must be at least ${e['minlength'].requiredLength} characters.`;
  if (e['weakPassword']) return 'Password must contain at least one letter and one digit.';
  if (e['invalidDate']) return 'Enter a valid date.';
  if (e['futureDate']) return 'Date of birth cannot be in the future.';
  if (e['tooOld']) return `Year must be ${LIMITS.minBirthYear} or later.`;
  return 'Invalid value.';
}
