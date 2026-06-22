"""
Django Management Command: import_donors
Place this file at:
    your_app/management/commands/import_donors.py

Usage:
    python manage.py import_donors --file path/to/BASE1.xlsx

Requirements:
    pip install openpyxl pandas
"""

import pandas as pd
from datetime import date, datetime
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from ghadapi.models import Person, Donor   # ← adjust app name if different


class Command(BaseCommand):
    help = 'Import donors from BASE1.xlsx into Person + Donor tables'

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True, help='Path to the .xlsx file')
        parser.add_argument('--dry-run', action='store_true', help='Preview without saving')

    def handle(self, *args, **options):
        filepath = options['file']
        dry_run  = options['dry_run']

        try:
            df = pd.read_excel(filepath)
        except Exception as e:
            raise CommandError(f'Cannot read file: {e}')

        required_cols = {'NOM', 'PRENOM', 'NUM_TEL', 'DATE_N', 'RESIDENC', 'SEX', 'GROUPAGE'}
        missing = required_cols - set(df.columns)
        if missing:
            raise CommandError(f'Missing columns in Excel: {missing}')

        created_count = 0
        skipped_count = 0
        errors        = []

        with transaction.atomic():
            for idx, row in df.iterrows():
                row_num = idx + 2  # 1-based + header row
                try:
                    # ── Gender mapping ─────────────────────────────────
                    sex_raw = str(row['SEX']).strip()
                    if sex_raw == 'ذكر':
                        gender = 'M'
                    elif sex_raw == 'أنثى':
                        gender = 'F'
                    else:
                        errors.append(f'Row {row_num}: Unknown SEX value "{sex_raw}", skipped')
                        skipped_count += 1
                        continue

                    # ── Date of birth ───────────────────────────────────
                    dob_raw = str(row['DATE_N']).strip()
                    try:
                        dob = datetime.strptime(dob_raw, '%d-%m-%Y').date()
                    except ValueError:
                        errors.append(f'Row {row_num}: Cannot parse DATE_N "{dob_raw}", skipped')
                        skipped_count += 1
                        continue

                    # ── Phone: keep as string, handle NaN ──────────────
                    phone_raw = row['NUM_TEL']
                    if pd.isna(phone_raw):
                        phone = None
                    else:
                        phone = str(int(phone_raw))

                    # ── Blood type ──────────────────────────────────────
                    blood_type = str(row['GROUPAGE']).strip()

                    if dry_run:
                        self.stdout.write(
                            f'[DRY-RUN] Row {row_num}: {row["PRENOM"]} {row["NOM"]} '
                            f'| {dob} | {gender} | {blood_type}'
                        )
                        created_count += 1
                        continue

                    # ── Create Person ───────────────────────────────────
                    person = Person.objects.create(
                        first_name    = str(row['PRENOM']).strip(),
                        last_name     = str(row['NOM']).strip(),
                        nin           = None,
                        phone         = phone,
                        address       = str(row['RESIDENC']).strip(),
                        date_of_birth = dob,
                        gender        = gender,
                        is_active     = True,
                        # created_at is auto_now_add — set automatically to today
                    )

                    # ── Create Donor ────────────────────────────────────
                    Donor.objects.create(
                        person             = person,
                        blood_type         = blood_type,
                        date_last_donation = date(2026, 1, 1),
                        is_approved        = True,
                        description        = None,
                    )

                    created_count += 1

                except Exception as e:
                    errors.append(f'Row {row_num}: Unexpected error — {e}')
                    skipped_count += 1

            if dry_run:
                transaction.set_rollback(True)

        # ── Summary ─────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            f'\n{"[DRY-RUN] " if dry_run else ""}Done: {created_count} donors imported, {skipped_count} skipped.'
        ))
        if errors:
            self.stdout.write(self.style.WARNING('\nIssues:'))
            for err in errors:
                self.stdout.write(f'  {err}')