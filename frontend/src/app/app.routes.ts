import { Routes } from '@angular/router';
import { Shell } from './layout/shell/shell';
import { authGuard, guestGuard } from './core/guards/auth.guard';

const placeholder = () => import('./pages/placeholder/placeholder').then((m) => m.Placeholder);

export const routes: Routes = [
  {
    path: 'login',
    title: 'Log in',
    canActivate: [guestGuard],
    loadComponent: () => import('./pages/auth/login/login').then((m) => m.Login),
  },
  {
    path: 'register',
    title: 'Create account',
    canActivate: [guestGuard],
    loadComponent: () => import('./pages/auth/register/register').then((m) => m.Register),
  },
  {
    path: '',
    component: Shell,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      {
        path: 'dashboard',
        title: 'Dashboard',
        loadComponent: () => import('./pages/dashboard/dashboard').then((m) => m.Dashboard),
      },
      {
        path: 'activity',
        title: 'Activity',
        loadComponent: () => import('./pages/activity/activity').then((m) => m.Activity),
      },
      {
        path: 'history',
        title: 'History',
        loadComponent: () => import('./pages/history/history').then((m) => m.History),
      },
      {
        path: 'history/:id',
        title: 'Workout details',
        loadComponent: () => import('./pages/workout-details/workout-details').then((m) => m.WorkoutDetails),
      },
      {
        path: 'goals',
        title: 'Goals',
        loadComponent: () => import('./pages/goals/goals').then((m) => m.Goals),
      },
      {
        path: 'settings',
        title: 'Settings',
        loadComponent: () => import('./pages/settings/settings').then((m) => m.Settings),
      },
      { path: '**', redirectTo: 'dashboard' },
    ],
  },
];
