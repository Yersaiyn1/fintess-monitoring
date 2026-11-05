export type IconName =
  | 'dashboard' | 'activity' | 'history' | 'goals' | 'settings'
  | 'flame' | 'route' | 'clock' | 'bolt' | 'menu' | 'close' | 'bell'
  | 'arrow-up' | 'arrow-down' | 'footsteps';

export type Tone = 'cobalt' | 'mint' | 'amber' | 'coral';

export interface StatCardData {
  id: string;
  label: string;
  value: number;
  unit: string;
  icon: IconName;
  tone: Tone;
  /** Percent change versus yesterday (can be negative) */
  change: number;
  /** Digits after the decimal point, used for formatting */
  decimals: number;
}

export interface NavItem {
  label: string;
  path: string;
  icon: IconName;
}
