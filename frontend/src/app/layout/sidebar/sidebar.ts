import { ChangeDetectionStrategy, Component, output } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { NavItem } from '../../core/models/stat.model';
import { Icon } from '../../shared/icon/icon';

@Component({
  selector: 'app-sidebar',
  imports: [RouterLink, RouterLinkActive, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.scss',
})
export class Sidebar {
  /** Emitted after a link is chosen, so the mobile drawer can close. */
  readonly navigated = output<void>();
  readonly closeRequested = output<void>();

  protected readonly items: NavItem[] = [
    { label: 'Dashboard', path: '/dashboard', icon: 'dashboard' },
    { label: 'Activity', path: '/activity', icon: 'activity' },
    { label: 'History', path: '/history', icon: 'history' },
    { label: 'Goals', path: '/goals', icon: 'goals' },
    { label: 'Settings', path: '/settings', icon: 'settings' },
  ];
}
