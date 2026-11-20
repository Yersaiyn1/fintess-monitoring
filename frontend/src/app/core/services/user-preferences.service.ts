import { Injectable, computed, signal } from '@angular/core';

export type DistanceUnit = 'km' | 'mi';
export type ColorTheme = 'light' | 'dark';
export type SidebarMode = 'hover' | 'expanded' | 'collapsed';

export interface UserPreferences {
  theme: ColorTheme;
  reduceMotion: boolean;
  distanceUnit: DistanceUnit;
  sidebarMode: SidebarMode;
}

const PREFERENCES_KEY = 'pulse.preferences';
const KM_TO_MILES = 0.621371;

@Injectable({ providedIn: 'root' })
export class UserPreferencesService {
  private readonly state = signal<UserPreferences>(this.load());
  readonly preferences = this.state.asReadonly();
  readonly distanceUnitLabel = computed(() => this.state().distanceUnit);
  readonly speedUnitLabel = computed(() => this.state().distanceUnit === 'mi' ? 'mph' : 'km/h');
  readonly paceUnitLabel = computed(() => this.state().distanceUnit === 'mi' ? 'min/mi' : 'min/km');

  constructor() { this.apply(); }

  update(changes: Partial<UserPreferences>): void {
    this.state.update((current) => ({ ...current, ...changes }));
    this.apply();
    try { localStorage.setItem(PREFERENCES_KEY, JSON.stringify(this.state())); } catch { /* storage unavailable */ }
  }

  distanceFromKm(km: number): number {
    return this.state().distanceUnit === 'mi' ? km * KM_TO_MILES : km;
  }

  speedFromKmh(kmh: number): number {
    return this.state().distanceUnit === 'mi' ? kmh * KM_TO_MILES : kmh;
  }

  paceSecondsFromKm(secondsPerKm: number): number {
    return this.state().distanceUnit === 'mi' ? secondsPerKm / KM_TO_MILES : secondsPerKm;
  }

  private apply(): void {
    const prefs = this.state();
    document.documentElement.dataset['theme'] = prefs.theme;
    document.documentElement.dataset['reduceMotion'] = String(prefs.reduceMotion);
    document.documentElement.dataset['sidebarMode'] = prefs.sidebarMode;
  }

  private load(): UserPreferences {
    try {
      const value = JSON.parse(localStorage.getItem(PREFERENCES_KEY) ?? 'null') as Partial<UserPreferences> | null;
      return {
        theme: value?.theme === 'dark' ? 'dark' : 'light',
        reduceMotion: value?.reduceMotion === true,
        distanceUnit: value?.distanceUnit === 'mi' ? 'mi' : 'km',
        sidebarMode: value?.sidebarMode === 'expanded' || value?.sidebarMode === 'collapsed' ? value.sidebarMode : 'hover',
      };
    } catch {
      return { theme: 'light', reduceMotion: false, distanceUnit: 'km', sidebarMode: 'hover' };
    }
  }
}
