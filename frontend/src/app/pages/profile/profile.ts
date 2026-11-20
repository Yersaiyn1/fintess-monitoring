import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-profile',
  imports: [FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './profile.html',
  styleUrl: './profile.scss',
})
export class Profile {
  protected readonly auth = inject(AuthService);
  protected fullName = this.auth.user()?.fullName ?? '';
  protected email = this.auth.user()?.email ?? '';
  protected currentPassword = '';
  protected newPassword = '';
  protected changingPassword = false;
  protected error = '';
  protected message = '';
  protected saving = false;

  protected async save(): Promise<void> {
    this.error = '';
    this.message = '';
    this.saving = true;
    const result = await this.auth.updateAccount({
      fullName: this.fullName,
      email: this.email,
      ...(this.changingPassword ? {
        currentPassword: this.currentPassword,
        newPassword: this.newPassword,
      } : {}),
    });
    this.saving = false;
    if (!result.ok) {
      this.error = result.error;
      return;
    }
    this.currentPassword = '';
    this.newPassword = '';
    this.changingPassword = false;
    this.message = 'Account details updated.';
  }
}
