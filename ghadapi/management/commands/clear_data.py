from django.core.management.base import BaseCommand
from django.db import connection, transaction

# Exact table names from \dt output — in FK-safe deletion order
TABLES_TO_CLEAR = [
    "ghadapi_distributionitem",
    "ghadapi_drugdistribution",
    "ghadapi_donationitem",
    "ghadapi_drugstock",
    "ghadapi_drugdonation",
    "ghadapi_member",
    "ghadapi_activity",
    "ghadapi_department",
    "persons",
]

# ghadapi_drug is NEVER touched


class Command(BaseCommand):
    help = "Clear all data except ghadapi_drug. Run with --confirm to execute."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Actually delete the data. Without this flag the command is a dry-run.",
        )

    def handle(self, *args, **options):
        confirm = options["confirm"]

        self.stdout.write("\n=== clear_data ===")
        if not confirm:
            self.stdout.write(self.style.WARNING("DRY-RUN — nothing will be deleted. Add --confirm to execute.\n"))
        else:
            self.stdout.write(self.style.ERROR("LIVE mode — data WILL be permanently deleted!\n"))

        with connection.cursor() as cur:

            self.stdout.write("Row counts before deletion:")
            counts = {}
            for table in TABLES_TO_CLEAR:
                cur.execute('SELECT COUNT(*) FROM "%s"' % table)
                n = cur.fetchone()[0]
                counts[table] = n
                self.stdout.write("  %s: %d rows" % (table, n))

            cur.execute('SELECT COUNT(*) FROM "ghadapi_drug"')
            self.stdout.write(self.style.SUCCESS("\n  ghadapi_drug: %d rows — PROTECTED, will not be touched\n" % cur.fetchone()[0]))

            if not confirm:
                self.stdout.write(self.style.WARNING("Re-run with --confirm to execute."))
                return

            self.stdout.write("\nDeleting...")
            try:
                with transaction.atomic():
                    cur.execute("SET CONSTRAINTS ALL DEFERRED;")

                    for table in TABLES_TO_CLEAR:
                        cur.execute('DELETE FROM "%s"' % table)
                        self.stdout.write(self.style.SUCCESS(
                            "  %s: deleted %d rows" % (table, cur.rowcount)
                        ))

                    cur.execute("SET CONSTRAINTS ALL IMMEDIATE;")

            except Exception as e:
                self.stdout.write(self.style.ERROR("\nERROR — transaction rolled back: %s" % e))
                raise

            cur.execute('SELECT COUNT(*) FROM "ghadapi_drug"')
            self.stdout.write(self.style.SUCCESS(
                "\nghadapi_drug still has %d rows — untouched ✓" % cur.fetchone()[0]
            ))

        self.stdout.write(self.style.SUCCESS("\nDone.\n"))