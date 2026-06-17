# Save as: yourapp/management/commands/import_drugs.py
#
# Setup:
#   mkdir -p yourapp/management/commands
#   touch yourapp/management/__init__.py
#   touch yourapp/management/commands/__init__.py
#
# Run:
#   python manage.py import_drugs --file /path/to/NOMENCLATURE_VERSION_AVRIL__2026-.xlsx --dry-run
#   python manage.py import_drugs --file /path/to/NOMENCLATURE_VERSION_AVRIL__2026-.xlsx

from django.core.management.base import BaseCommand
import pandas as pd

FORM_MAP = {
    'tablet': [
        'COMPRIME', 'COMPRIME ', 'COMPRIME PELLICULE', 'COMPRIME PELLICULE ',
        'COMPRIME PELLICULE SECABLE', 'COMPRIME SECABLE', 'COMPRIME SECABLE ',
        'COMPRIME A CROQUER', 'COMPRIME A SUCER', 'COMPRIME EFFERVESCENT',
        'COMPRIME ORODISPERSIBLE', 'COMPRIME DISPERSIBLE', 'COMPRIME ENROBE',
        'COMPRIME GASTRO-RESISTANT', 'COMPRIME A LIBERATION PROLONGEE',
        'COMPRIME PELLICULE A LIBERATION PROLONGEE', 'COMPRIME VAGINAL',
        'COMPRIME A LIB PROLONGEE', 'COMPRIMES A LIB PRO',
        'GELULE', 'GELULE A LIBERATION PROLONGEE', 'GELULE GASTRO-RESISTANT',
        'GELULE GASTRO-RESISTANTE', 'GELULE LP',
        'CAPSULE DURE', 'CAPSULE MOLLE', 'CAPSULE ORALE',
        'PASTILLE', 'DRAGEE', 'LYOPHILISAT ORAL',
        'GRANULE', 'GRANULES', 'GRANULES EFFERVESCENTS',
        'COMPRIME PELLICULE SECABLE A LIBERATION PROLONGEE',
        'COMPRIME PELLICULE A LIB PRO', 'COMPRIME PELLICULE BICOUCHE',
        'COMPRIME PELLICULE QUADRISECABLE', 'COMPRIME QUADRI SECABLE',
        'COMPRIME DISPERSIBLE SECABLE', 'COMPRIME EFFERVESSANT',
        'COMPRIME A CROQUER ET A SUCER', 'COMPRIME A CROQUER OU A SUCER',
        'COMPRIME A CROQUER SANS SUCRE', 'COMPRIME AVEC BARRE DE CASSEURE',
        'COMPRIME SEC. ADULTE', 'COMP.GASTRORESIST.',
        'COMPRIME LIBERATION MODIFIEE', 'COMPRIME PELLICULE A LIBERATION MODIFIEE',
        'COMPRIME ENROBE GASTRO-RESISTANT', 'COMPRIME ENROBE SECABLE',
        'COMPRIME SECABLE A LIBERATION PROLONGEE',
        'COMPRIME SECABLE A LIBERATION MODIFIEE',
        'COMPRIME OPELL SECABLES', 'COMPRIME . ENRO. LP',
        'COMPRIME PELLICULE A LIBERATION PROLONGE', 'COMPRIMES EFFERVESCENTS',
        'COMPRIME DISPERS. OU. A CROQUER', 'COMPRIME QUADRI-SECABLE',
    ],
    'syrup': [
        'SIROP', 'SOLUTION BUVABLE', 'SOL. BUVABLE', 'SOLUTION BUVABLE EN GOUTTES',
        'SUSPENSION BUVABLE', 'SUSPENSION BUVABLE ', 'SUSPENSION BUVABLE RECONST.',
        'POUDRE POUR SUSPENSION BUVABLE', 'POUDRE P. SUSP. BUV.',
        'PDRE.PR SUSP.BUV', 'POUDRE POUR SOLUTION BUVABLE',
        'SOLUTION BUVABLE EN RECIPIENT UNIDOSE', 'SOLUTION BUVABLE EN UNIDOSES',
        'AMP.BUV.', 'ELIXIR', 'EMULSION BUVABLE', 'SOLUTION ORALE',
        'SOLUTION ORALE EN GOUTTES', 'SUSPENSION ORALE',
        'POUDRE POUR SOLUTION ORALE', 'GRANULES POUR SOLUTION BUVABLE',
        'GRANULES POUR SUSPENSION BUVABLE', 'SACHET',
        'PDRE.P.SOL.BUV', 'PDRE P.SOL.BUV.',
    ],
    'injection': [
        'SOLUTION INJECTABLE', 'SOLUTION INJECTABLE IV', 'SOLUTION INJECTABLE IV /IM',
        'SOLUTION INJECTABLE  SAUF IV', 'SOLUTION INJECTABLE IV, IM ,SC OU PERIDURALE',
        'SOLUTION INJECTABLE IV OU PERIDURALE', 'SUSPENSION INJECTABLE',
        'POUDRE POUR SOLUTION INJECTABLE', 'POUDRE POUR SOL INJ OU POUR PERF IV',
        'EMULSION INJ. IV ET POUR PERF.IV', 'EMULSION INJ IV ET POUR PERFUSION',
        'EMULSION IV PERF.', 'SOLUTION POUR INJECTABLE', 'SOLUTION POUR PERFUSION',
        'LYOPHILISAT POUR SOLUTION INJECTABLE', 'LYOPHILISAT P.SOL.INJ.',
        'SOL INJ A USAGE DENTAIRE', 'SOLUTION INJECTABLE IM', 'SOLUTION INJECTABLE SC',
        'SUSPENSION INJECTABLE LP', 'POUDRE POUR SUSPENSION INJECTABLE',
        'CONCENTRE POUR SOLUTION POUR PERFUSION', 'CONCENTRE POUR SOL. POUR PERF.',
        'CONC.P.SOL.P.PERF.', 'POUDRE P.SOL PERF.',
        'IMPLANT', 'IMPLANT SOUS-CUTANE',
    ],
    'cream': [
        'CREME', 'CREME DERMIQUE', 'GEL', 'GEL POUR APPLICATION CUTANEE',
        'GEL ORAL', 'Gel ORAL', 'POMMADE', 'POMMADE DERMIQUE',
        'POMMADE OPHTALMIQUE', 'POMMADE AURICULAIRE',
        'SOLUTION CUTANEE', 'SOLUTION DERMIQUE', 'LOTION', 'MOUSSE', 'MOUSSE CUTANEE',
        'SHAMPOOING', 'BAUME', 'BAIN DE BOUCHE',
        'COLLYRE', 'COLLYRE ', 'COLLYRE EN SOLUTION', 'COLLYRE EN SOLUTION ',
        'COLLYRE EN SUSPENSION', 'COLLYRE VISQUEUX',
        'COLLYRE EN SOLUTION STERILE', 'COLLYRE EN SOLUTION EN RECIPIENT UNIDOSE',
        'COLLYRE EN SOLUTION A LIBERATION PROLONGEE', 'COLLYRE (SANS CONSERVATEUR)',
        'SOLUTION OPHTALMIQUE', 'SUSPENSION OPHTALMIQUE', 'GEL OPHTALMIQUE',
        'EMULSION POUR APPLICATION CUTANEE', 'SOLUTION AURICULAIRE',
        'SUSPENSION AURICULAIRE', 'SOLUTION NASALE', 'SUSPENSION NASALE', 'GEL NASAL',
        'SOLUTION NASALE EN RECIPIENT UNIDOSE', 'OVULE', 'OVULE VAGINAL',
        'CREME VAGINALE', 'GEL VAGINAL', 'SUPPOSITOIRE', 'SUPPOSITOIRE NOURRISSON',
        'SUPPOSITOIRE ADULTE', 'SUPPOSITOIRE ENFANT',
        'SUPPOSITOIRE ENFANT ET NOURRISSON', 'SOLUTION RECTALE',
        'SUSPENSION RECTALE', 'LAVEMENT', 'DISPOSITIF TRANSDERMIQUE', 'PATCH',
        'COLLUTOIRE', 'COLLY. - SOL AURIC. - SOL. NAS.',
        'POUDRE POUR APPLICATION CUTANEE', 'POUDRE CUTANEE',
    ],
}

FORM_LOOKUP = {}
for choice, french_list in FORM_MAP.items():
    for f in french_list:
        FORM_LOOKUP[f.strip().upper()] = choice


def map_form(french_form):
    if not french_form or str(french_form).strip() in ('', 'nan', '---'):
        return 'other'
    f = str(french_form).strip().upper()
    if f in FORM_LOOKUP:
        return FORM_LOOKUP[f]
    if any(k in f for k in ['COMPRIME', 'GELULE', 'CAPSULE', 'PASTILLE', 'DRAGEE', 'GRANULE']):
        return 'tablet'
    if any(k in f for k in ['SIROP', 'BUVABLE', 'ORAL', 'SACHET', 'ELIXIR']):
        return 'syrup'
    if any(k in f for k in ['INJECT', 'PERFUSION', 'IV', 'IM', 'IMPLANT']):
        return 'injection'
    if any(k in f for k in ['CREME', 'POMMADE', 'GEL', 'LOTION', 'COLLYRE',
                              'SUPPOSITOIRE', 'CUTANE', 'VAGINAL', 'OPHTALMIQUE',
                              'AURICULAIRE', 'NASAL', 'RECTAL', 'PATCH', 'OVULE']):
        return 'cream'
    return 'other'


class Command(BaseCommand):
    help = 'Import drugs from Algerian national pharmaceutical nomenclature (2037 unique drugs by CODE)'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, required=True, help='Path to NOMENCLATURE Excel file')
        parser.add_argument('--dry-run', action='store_true', help='Preview without saving')

    def handle(self, *args, **options):
        from ghadapi.models import Drug   # ← change 'pharmacy' to your app name

        path = options['file']
        dry_run = options['dry_run']

        self.stdout.write(f'📂 Reading: {path}')

        df = pd.read_excel(
            path,
            sheet_name='Nomenclature Avril 2026',
            header=13,
            dtype=str,
        )

        df = df.dropna(how='all')
        df = df[['CODE', 'DENOMINATION COMMUNE INTERNATIONALE', 'FORME', 'DOSAGE']]
        df.columns = ['code', 'dci_name', 'forme', 'dosage']

        for col in df.columns:
            df[col] = df[col].fillna('').str.strip()

        # Drop rows with no code or name
        df = df[df['code'] != '']
        df = df[df['dci_name'] != '']

        # ── KEY STEP: deduplicate by CODE ──────────────────────
        # Same CODE = same drug (DCI + dosage + form), just different brand names
        # Keep the first occurrence — they all have the same DCI/form/dosage
        before = len(df)
        df = df.drop_duplicates(subset=['code'], keep='first')
        after = len(df)
        self.stdout.write(f'✅ {before} rows → {after} unique drugs (after dedup by CODE)')

        df['form'] = df['forme'].apply(map_form)

        self.stdout.write('Form distribution:')
        for form, count in df['form'].value_counts().items():
            self.stdout.write(f'   {form}: {count}')

        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN — nothing saved. Sample:'))
            for _, row in df.head(8).iterrows():
                self.stdout.write(f"  [{row['form']:10}] {row['code']}  {row['dci_name']} {row['dosage']}")
            return

        self.stdout.write('\nImporting to database...')
        created = updated = errors = 0

        for _, row in df.iterrows():
            try:
                _, was_created = Drug.objects.update_or_create(
                    code=row['code'],          # unique key = CODE (e.g. "01 A 003")
                    defaults={
                        'dci_name': row['dci_name'][:255],
                        'form':     row['form'],
                        'dosage':   row['dosage'][:100],
                    }
                )
                if was_created:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                errors += 1
                self.stderr.write(f'  ⚠ {row["code"]}: {e}')

        self.stdout.write(self.style.SUCCESS(
            f'\n🎉 Done!  Created: {created} | Updated: {updated} | Errors: {errors}'
        ))
