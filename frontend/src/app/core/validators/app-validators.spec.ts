import { FormControl, FormGroup } from '@angular/forms';
import { birthDate, emailValidators, fieldsMatch, notBlank, passwordStrength } from './app-validators';

const email = (v: string) => new FormControl(v, emailValidators);

describe('app validators', () => {
  it('accepts a valid email and rejects bad ones', () => {
    expect(email('user@example.com').valid).toBe(true);
    for (const bad of ['', '   ', 'user', 'user@', 'user@example', 'us er@example.com', 'a@b.c']) {
      expect(email(bad).invalid).toBe(true);
    }
  });

  it('limits email length to 100 characters (like the database)', () => {
    expect(email('a'.repeat(95) + '@x.com').invalid).toBe(true);
  });

  it('rejects blank text', () => {
    expect(new FormControl('   ', notBlank).errors).toEqual({ blank: true });
    expect(new FormControl('Ana', notBlank).errors).toBeNull();
  });

  it('requires a letter and a digit in the password', () => {
    expect(new FormControl('abcdefgh', passwordStrength).errors).toEqual({ weakPassword: true });
    expect(new FormControl('12345678', passwordStrength).errors).toEqual({ weakPassword: true });
    expect(new FormControl('abcd1234', passwordStrength).errors).toBeNull();
  });

  it('birth date cannot be in the future or before 1900', () => {
    const future = new Date(Date.now() + 86_400_000 * 2).toISOString().slice(0, 10);
    expect(new FormControl(future, birthDate).errors).toEqual({ futureDate: true });
    expect(new FormControl('1850-01-01', birthDate).errors).toEqual({ tooOld: true });
    expect(new FormControl('2003-04-15', birthDate).errors).toBeNull();
  });

  it('checks that two fields match', () => {
    const g = (a: string, b: string) =>
      new FormGroup({ p: new FormControl(a), c: new FormControl(b) }, fieldsMatch('p', 'c'));
    expect(g('abc12345', 'abc12345').errors).toBeNull();
    expect(g('abc12345', 'abc12346').errors).toEqual({ mismatch: true });
  });
});
