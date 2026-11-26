import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

/** Only patient accounts can open the patient application. */
export const patientGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.role() === 'patient') return true;
  return router.createUrlTree([auth.role() === 'doctor' ? '/doctor' : auth.role() === 'admin' ? '/admin' : '/login']);
};

/** Only doctor accounts can open the doctor area. */
export const doctorGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.role() === 'doctor') return true;
  return router.createUrlTree([auth.role() === 'admin' ? '/admin' : auth.role() === 'patient' ? '/dashboard' : '/login']);
};

/** Only users explicitly marked as administrators can open the review portal. */
export const adminGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.role() === 'admin') return true;
  return router.createUrlTree([auth.role() === 'doctor' ? '/doctor' : auth.role() === 'patient' ? '/dashboard' : '/login']);
};

/** Logged-in users do not need the login/register pages. */
export const guestGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  return auth.isLoggedIn()
    ? inject(Router).createUrlTree([auth.role() === 'doctor' ? '/doctor' : auth.role() === 'admin' ? '/admin' : '/dashboard'])
    : true;
};
