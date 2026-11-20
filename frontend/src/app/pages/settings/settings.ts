import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SidebarMode, UserPreferencesService } from '../../core/services/user-preferences.service';

@Component({
  selector: 'app-settings',
  imports: [FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './settings.html',
  styleUrl: './settings.scss',
})
export class Settings {
  private readonly preferenceService = inject(UserPreferencesService);
  protected readonly preferences = this.preferenceService.preferences;
  protected saved = false;

  protected setTheme(theme: 'light' | 'dark'): void {
    this.preferenceService.update({ theme });
    this.saved = true;
  }

  protected setDistanceUnit(distanceUnit: 'km' | 'mi'): void {
    this.preferenceService.update({ distanceUnit });
    this.saved = true;
  }

  protected setReducedMotion(reduceMotion: boolean): void {
    this.preferenceService.update({ reduceMotion });
    this.saved = true;
  }

  protected setSidebarMode(sidebarMode: SidebarMode): void {
    this.preferenceService.update({ sidebarMode });
    this.saved = true;
  }
}
