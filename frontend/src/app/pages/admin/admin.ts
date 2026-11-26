import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { DoctorApplication, DoctorApplicationsService } from '../../core/services/doctor-applications.service';

@Component({
  selector: 'app-admin',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './admin.html',
  styleUrl: './admin.scss',
})
export class Admin {
  protected readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly api = inject(DoctorApplicationsService);
  protected readonly applications = signal<DoctorApplication[]>([]);
  protected readonly loading = signal(true);
  protected readonly busyId = signal<number | null>(null);
  protected readonly error = signal('');
  protected readonly notice = signal('');

  constructor() { void this.load(); }

  protected async load(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try { this.applications.set(await this.api.list()); }
    catch (error) { this.error.set(this.api.message(error, 'Could not load applications.')); }
    finally { this.loading.set(false); }
  }

  protected async approve(application: DoctorApplication): Promise<void> {
    if (!window.confirm(`Approve ${application.full_name} and create the doctor account?`)) return;
    await this.decide(application, true);
  }

  protected async reject(application: DoctorApplication): Promise<void> {
    if (!window.confirm(`Reject the application from ${application.full_name}?`)) return;
    await this.decide(application, false);
  }

  protected async download(application: DoctorApplication, doc: DoctorApplication['documents'][number]): Promise<void> {
    this.error.set('');
    try { await this.api.download(application.application_id, doc); }
    catch (error) { this.error.set(this.api.message(error, 'Could not download this document.')); }
  }

  protected async logout(): Promise<void> {
    this.auth.logout();
    await this.router.navigateByUrl('/login');
  }

  private async decide(application: DoctorApplication, approve: boolean): Promise<void> {
    this.busyId.set(application.application_id);
    this.error.set('');
    this.notice.set('');
    try {
      if (approve) {
        await this.api.approve(application.application_id);
        this.notice.set(`${application.full_name} was approved. They can now sign in as a doctor.`);
      } else {
        await this.api.reject(application.application_id, '');
        this.notice.set(`${application.full_name}'s application was rejected.`);
      }
      this.applications.update((items) => items.filter((item) => item.application_id !== application.application_id));
    } catch (error) {
      this.error.set(this.api.message(error, 'Could not update this application.'));
    } finally { this.busyId.set(null); }
  }
}
