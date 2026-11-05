import { Routes } from '@angular/router';
import { Shell } from './layout/shell/shell';

const placeholder = () => import('./pages/placeholder/placeholder').then((m) => m.Placeholder);

export const routes: Routes = [
  {
    path: '',
    component: Shell,
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
        loadComponent: placeholder,
        data: { heading: 'Activity tracking', text: 'Start and stop workouts, follow the timer and see steps, calories and distance update live.', phase: 2 },
      },
      {
        path: 'history',
        title: 'History',
        loadComponent: placeholder,
        data: { heading: 'Workout history', text: 'Browse saved workouts, filter them by date and type, and review weekly and monthly analytics.', phase: 3 },
      },
      {
        path: 'goals',
        title: 'Goals',
        loadComponent: placeholder,
        data: { heading: 'Goals and progress', text: 'Set daily and weekly targets, follow progress bars and get notified after 7 inactive days.', phase: 4 },
      },
      {
        path: 'settings',
        title: 'Settings',
        loadComponent: placeholder,
        data: { heading: 'Profile and settings', text: 'Manage your profile and preferences. Everything is stored in your browser.', phase: 4 },
      },
      { path: '**', redirectTo: 'dashboard' },
    ],
  },
];
