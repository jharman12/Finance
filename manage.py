"""
manage.py  –  Developer seed / data management CLI

Usage:
    python manage.py export [--dir seeds]
        Export the current database to CSV files.
        Defaults to ./seeds/

    python manage.py import [--dir seeds] [--clear]
        Import CSV files into the database.
        Use --clear to wipe all existing data first (full reset).
        Defaults to ./seeds/

    python manage.py status
        Show row counts for all tables in the current database.

Examples:
    # After setting up test data in the app, save it for the team:
    python manage.py export

    # On a fresh machine (or to reset to shared test data):
    python manage.py import --clear

    # Inspect the current database:
    python manage.py status
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the project root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).parent))

from finance_app.storage import FinanceRepository


def cmd_export(args: argparse.Namespace) -> None:
    repo = FinanceRepository()
    output_dir = Path(args.dir)
    print(f"Exporting to: {output_dir.resolve()}")
    counts = repo.export_to_csv(output_dir)
    for table, count in counts.items():
        print(f"  {table}: {count} rows")
    print("Done. Commit the CSV files in seeds/ to share with your team.")


def cmd_import(args: argparse.Namespace) -> None:
    repo = FinanceRepository()
    input_dir = Path(args.dir)

    if not input_dir.exists():
        print(f"Error: directory '{input_dir}' not found.")
        sys.exit(1)

    if args.clear:
        confirm = input("This will DELETE all existing data and reload from CSVs. Continue? [y/N] ")
        if confirm.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return

    print(f"Importing from: {input_dir.resolve()}" + (" (clearing first)" if args.clear else ""))
    counts = repo.import_from_csv(input_dir, clear_first=args.clear)
    if not counts:
        print("No CSV files found. Nothing imported.")
    else:
        for table, count in counts.items():
            print(f"  {table}: {count} rows imported")
        print("Done.")


def cmd_status(args: argparse.Namespace) -> None:  # noqa: ARG001
    repo = FinanceRepository()
    print(f"Database: {repo.database_path}")
    with repo._connection() as conn:
        for table in ("categories", "transactions", "recurring_items", "budgets", "settings"):
            try:
                row = conn.execute(f"SELECT COUNT(*) as n FROM {table}").fetchone()  # noqa: S608
                print(f"  {table}: {row['n']} rows")
            except Exception:
                print(f"  {table}: (not found)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finance app data management tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # export
    export_parser = subparsers.add_parser("export", help="Export database to CSV files")
    export_parser.add_argument("--dir", default="seeds", help="Output directory (default: seeds)")

    # import
    import_parser = subparsers.add_parser("import", help="Import CSV files into the database")
    import_parser.add_argument("--dir", default="seeds", help="Input directory (default: seeds)")
    import_parser.add_argument("--clear", action="store_true", help="Wipe all data before importing")

    # status
    subparsers.add_parser("status", help="Show row counts for all tables")

    args = parser.parse_args()

    if args.command == "export":
        cmd_export(args)
    elif args.command == "import":
        cmd_import(args)
    elif args.command == "status":
        cmd_status(args)


if __name__ == "__main__":
    main()
