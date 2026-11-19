import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import {
  DoctorAccessApiService,
  DoctorAccessRecord,
  DoctorDirectoryEntry,
} from '../../core/services/api/doctor-access-api.service';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-settings',
  imports: [FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './settings.html',
  styleUrl: './settings.scss',
})
export class Settings {
  protected readonly auth = inject(AuthService);
  private readonly doctorApi = inject(DoctorAccessApiService);

  protected readonly doctors = signal<DoctorDirectoryEntry[]>([]);
  protected readonly permissions = signal<DoctorAccessRecord[]>([]);
  protected readonly busy = signal(false);
  protected readonly message = signal('');
  protected readonly error = signal('');

  protected selectedDoctorId = 0;
  protected accessStart = new Date().toISOString().slice(0, 10);
  protected accessEnd = new Date(Date.now() + 30 * 86400_000).toISOString().slice(0, 10);

  constructor() {
    void this.loadAll();
  }

  protected async loadAll(): Promise<void> {
    try {
      const [docs, perms] = await Promise.all([
        firstValueFrom(this.doctorApi.directory()),
        firstValueFrom(this.doctorApi.listAccess()),
      ]);
      this.doctors.set(docs);
      this.permissions.set(perms);
      if (!this.selectedDoctorId && docs.length > 0) {
        this.selectedDoctorId = docs[0].doctor_id;
      }
    } catch {
      this.error.set('Could not load doctor access settings.');
    }
  }

  protected async grantAccess(): Promise<void> {
    this.error.set('');
    this.message.set('');
    if (!this.selectedDoctorId) {
      this.error.set('Select a doctor first.');
      return;
    }
    this.busy.set(true);
    try {
      await firstValueFrom(
        this.doctorApi.grantAccess(this.selectedDoctorId, this.accessStart, this.accessEnd),
      );
      await this.loadAll();
      this.message.set('Doctor access updated.');
    } catch {
      this.error.set('Could not save doctor access. Ensure end date is on or after start date.');
    } finally {
      this.busy.set(false);
    }
  }

  protected async revokeAccess(doctorId: number): Promise<void> {
    this.error.set('');
    this.message.set('');
    this.busy.set(true);
    try {
      await firstValueFrom(this.doctorApi.revokeAccess(doctorId));
      await this.loadAll();
      this.message.set('Doctor access revoked.');
    } catch {
      this.error.set('Could not revoke doctor access.');
    } finally {
      this.busy.set(false);
    }
  }
}
