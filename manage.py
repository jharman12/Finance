"""
manage.py  –  Developer seed / data management + remote device management CLI

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

    python manage.py list-devices
        Show all known paired remote devices with source_id, name, host,
        last_connected, and token_status (active / revoked / no-token).

    python manage.py unpair <source_id>
        Remove a paired device from the DB (soft-delete) and revoke its auth token.

    python manage.py rotate-token <source_id>
        Revoke the current auth token and issue a new one.
        The new token is printed — configure it on the remote device.

    python manage.py show-token <source_id>
        Report whether a valid non-revoked token exists for a device.
        The raw token hash is never printed.

Examples:
    # After setting up test data in the app, save it for the team:
    python manage.py export

    # On a fresh machine (or to reset to shared test data):
    python manage.py import --clear

    # Inspect the current database:
    python manage.py status

    # List all paired remote voice devices:
    python manage.py list-devices

    # Remove a device that is no longer in use:
    python manage.py unpair phone-living-room

    # Refresh the token for a device (e.g. after suspected compromise):
    python manage.py rotate-token phone-living-room
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the project root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).parent))

from finance_app.storage import FinanceRepository
from finance_app.services.voice.device_token_store import DeviceTokenStore, DeviceTokenRecord  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db_exists_check() -> bool:
    """Return True if the default DB file exists; print a warning if it does not."""
    from finance_app.config import DEFAULT_DB_PATH  # local import to keep patching simple in tests

    if not DEFAULT_DB_PATH.exists():
        print(
            f"[Warning] Database not found: {DEFAULT_DB_PATH}\n"
            "The Finance app has not been run on this machine yet. "
            "Launch the app first to initialise the database and pair remote devices."
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Device management commands
# ---------------------------------------------------------------------------


def cmd_list_devices(args: argparse.Namespace) -> None:  # noqa: ARG001
    """Print a table of all known paired remote devices."""
    db_present = _db_exists_check()
    repo = FinanceRepository()
    token_store = DeviceTokenStore()

    devices = repo._paired_device_repository.list_all()
    token_map = {r.source_id: r for r in token_store.list_tokens(active_only=False)}

    if not devices:
        if db_present:
            print("No paired remote devices found.")
        return

    col = [32, 22, 18, 22, 10]
    sep = "-" * sum(col)
    header = (
        f"{'SOURCE_ID':<{col[0]}}"
        f"{'NAME':<{col[1]}}"
        f"{'HOST':<{col[2]}}"
        f"{'LAST_CONNECTED':<{col[3]}}"
        f"{'TOKEN':<{col[4]}}"
    )
    print(header)
    print(sep)

    for device in devices:
        rec = token_map.get(device.source_id)
        if rec is None:
            token_status = "no-token"
        elif rec.is_active():
            token_status = "active"
        else:
            token_status = "revoked"

        last_conn = ""
        if device.last_connected_at:
            last_conn = str(device.last_connected_at)[:19]

        print(
            f"{device.source_id:<{col[0]}}"
            f"{device.device_name:<{col[1]}}"
            f"{device.host_ip:<{col[2]}}"
            f"{last_conn:<{col[3]}}"
            f"{token_status:<{col[4]}}"
        )


def cmd_unpair(args: argparse.Namespace) -> None:
    """Remove a paired device from the DB and revoke its auth token."""
    source_id: str = args.source_id

    if not _db_exists_check():
        sys.exit(1)

    repo = FinanceRepository()
    token_store = DeviceTokenStore()

    device = repo._paired_device_repository.get_by_source_id(source_id)
    if device is None:
        print(f"Error: device '{source_id}' not found in the database.")
        sys.exit(1)

    repo._paired_device_repository.delete(source_id)
    token_store.revoke_token(source_id)
    print(f"Unpaired device '{source_id}' ({device.device_name}). Token revoked.")


def cmd_rotate_token(args: argparse.Namespace) -> None:
    """Revoke the current token for a device and issue a fresh one."""
    source_id: str = args.source_id

    if not _db_exists_check():
        sys.exit(1)

    repo = FinanceRepository()
    token_store = DeviceTokenStore()

    device = repo._paired_device_repository.get_by_source_id(source_id)
    if device is None:
        print(f"Error: device '{source_id}' not found in the database.")
        sys.exit(1)

    token_store.revoke_token(source_id)
    new_token = token_store.issue_token(source_id, device.device_name)
    print(f"Token rotated for device '{source_id}' ({device.device_name}).")
    print(f"New token — configure this on the remote device:\n  {new_token}")


def cmd_show_token(args: argparse.Namespace) -> None:
    """Report whether a valid (non-revoked) token exists for a device — never prints the hash."""
    source_id: str = args.source_id

    _db_exists_check()
    token_store = DeviceTokenStore()

    all_records = {r.source_id: r for r in token_store.list_tokens(active_only=False)}
    record = all_records.get(source_id)

    if record is None:
        print(f"Token status for '{source_id}': ABSENT (no token record found)")
    elif record.is_active():
        paired = record.paired_at[:10] if record.paired_at else "unknown"
        print(f"Token status for '{source_id}': PRESENT (active, paired {paired})")
    else:
        revoked_at = record.revoked_at[:19] if record.revoked_at else "unknown"
        print(f"Token status for '{source_id}': ABSENT (token was revoked at {revoked_at})")


# ---------------------------------------------------------------------------
# Original seed / data commands
# ---------------------------------------------------------------------------


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

    # list-devices
    subparsers.add_parser(
        "list-devices",
        help="Show all known paired remote devices with token status",
    )

    # unpair
    unpair_parser = subparsers.add_parser(
        "unpair",
        help="Remove a paired device from the DB and revoke its auth token",
    )
    unpair_parser.add_argument("source_id", help="source_id of the device to unpair")

    # rotate-token
    rotate_parser = subparsers.add_parser(
        "rotate-token",
        help="Revoke the current token and issue a fresh one (prints new token)",
    )
    rotate_parser.add_argument("source_id", help="source_id of the target device")

    # show-token
    show_token_parser = subparsers.add_parser(
        "show-token",
        help="Report whether a valid non-revoked token exists for a device",
    )
    show_token_parser.add_argument("source_id", help="source_id of the target device")

    args = parser.parse_args()

    if args.command == "export":
        cmd_export(args)
    elif args.command == "import":
        cmd_import(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "list-devices":
        cmd_list_devices(args)
    elif args.command == "unpair":
        cmd_unpair(args)
    elif args.command == "rotate-token":
        cmd_rotate_token(args)
    elif args.command == "show-token":
        cmd_show_token(args)


if __name__ == "__main__":
    main()
