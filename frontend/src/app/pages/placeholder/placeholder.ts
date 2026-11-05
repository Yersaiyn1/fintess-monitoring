import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

/** Temporary page for sections that are built in later phases. */
@Component({
  selector: 'app-placeholder',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './placeholder.html',
  styleUrl: './placeholder.scss',
})
export class Placeholder {
  protected readonly info = inject(ActivatedRoute).snapshot.data as {
    heading: string;
    text: string;
    phase: number;
  };
}
