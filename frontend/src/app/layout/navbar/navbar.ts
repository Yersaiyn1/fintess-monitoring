import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { Icon } from '../../shared/icon/icon';

@Component({
  selector: 'app-navbar',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './navbar.html',
  styleUrl: './navbar.scss',
})
export class Navbar {
  readonly title = input('Dashboard');
  readonly menuToggle = output<void>();

  protected readonly today = new Intl.DateTimeFormat('en-US', {
    weekday: 'long', day: 'numeric', month: 'long',
  }).format(new Date());
}
