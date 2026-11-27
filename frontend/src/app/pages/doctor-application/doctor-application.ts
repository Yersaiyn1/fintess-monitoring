import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { DoctorApplicationsService } from '../../core/services/doctor-applications.service';
import { emailValidators, notBlank, passwordStrength } from '../../core/validators/app-validators';
import { TranslatePipe } from '../../core/i18n/translate.pipe';

@Component({
  selector: 'app-doctor-application',
  imports: [ReactiveFormsModule, RouterLink, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './doctor-application.html',
  styleUrl: './doctor-application.scss',
})
export class DoctorApplicationPage {
  private readonly api = inject(DoctorApplicationsService);
  private readonly formBuilder = inject(FormBuilder).nonNullable;

  protected readonly form = this.formBuilder.group({
    fullName: ['', [Validators.required, notBlank, Validators.maxLength(255)]],
    email: ['', emailValidators],
    specialty: ['', [Validators.required, notBlank, Validators.maxLength(255)]],
    licenseNumber: ['', [Validators.required, notBlank, Validators.maxLength(100)]],
    password: ['', [Validators.required, Validators.minLength(8), Validators.maxLength(64), passwordStrength]],
  });
  protected readonly files = signal<File[]>([]);
  protected readonly fileNames = computed(() => this.files().map((file) => file.name).join(', '));
  protected readonly submitting = signal(false);
  protected readonly error = signal('');
  protected readonly success = signal(false);

  protected chooseFiles(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.files.set(Array.from(input.files ?? []));
    this.error.set('');
  }

  protected async submit(): Promise<void> {
    this.error.set('');
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.error.set('Enter valid details for every field before submitting.');
      return;
    }
    if (this.files().length === 0) {
      this.error.set('Attach at least one license or qualification document.');
      return;
    }
    const values = this.form.getRawValue();
    const body = new FormData();
    body.append('full_name', values.fullName.trim());
    body.append('email', values.email.trim().toLowerCase());
    body.append('specialty', values.specialty.trim());
    body.append('license_number', values.licenseNumber.trim());
    body.append('password', values.password);
    for (const file of this.files()) body.append('documents', file, file.name);

    this.submitting.set(true);
    try {
      await this.api.submit(body);
      this.success.set(true);
    } catch (error) {
      this.error.set(this.api.message(error, 'Could not submit the application. Please try again.'));
    } finally {
      this.submitting.set(false);
    }
  }
}
