#!/usr/bin/env python3
"""
One-off NAB PDF Statement Importer

Parses all NAB PDF statements from a directory and imports them
into the PostgreSQL database.

Usage:
    source venv/bin/activate

    # Export DB credentials:
    export DB_TYPE=postgres
    export DB_HOST=192.168.1.228
    export DB_PORT=5432
    export DB_NAME=family_finance
    export DB_USER=readwrite
    export DB_PASSWORD=your_password

    # Run the import:
    python scripts/import_nab_statements.py incoming/nab-statements/

    # Or dry-run (parse only, no DB write):
    python scripts/import_nab_statements.py incoming/nab-statements/ --dry-run
"""

import sys
import os
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.parsers.nab import NABParser
from src.database import get_repository


def main():
    parser = argparse.ArgumentParser(description="Import NAB PDF statements to database")
    parser.add_argument("directory", help="Directory containing NAB PDF statements")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't write to database")
    args = parser.parse_args()

    pdf_dir = Path(args.directory)
    if not pdf_dir.exists():
        print(f"Error: Directory not found: {pdf_dir}")
        sys.exit(1)

    files = sorted(pdf_dir.glob("*.pdf"))
    if not files:
        print(f"No PDF files found in {pdf_dir}")
        sys.exit(1)

    print(f"Found {len(files)} PDF files in {pdf_dir}")
    print()

    nab_parser = NABParser()
    all_transactions = []

    # Parse all files
    for f in files:
        txns = nab_parser.parse(f)
        all_transactions.extend(txns)

        credits = sum(t.amount for t in txns if t.amount > 0)
        debits = sum(t.amount for t in txns if t.amount < 0)
        print(f"  {f.name}: {len(txns):>4} txns | credits: ${credits:>10,.2f} | debits: ${debits:>10,.2f}")

    print(f"\nTotal parsed: {len(all_transactions)} transactions")

    if args.dry_run:
        print("\n[DRY RUN] No database writes performed.")
        return

    # Validate required env vars
    required_vars = ['DB_TYPE', 'DB_HOST', 'DB_USER', 'DB_PASSWORD']
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        print(f"\nError: Missing required environment variables: {', '.join(missing)}")
        print("\nSet them with:")
        print("  export DB_TYPE=postgres")
        print("  export DB_HOST=192.168.1.228")
        print("  export DB_PORT=5432")
        print("  export DB_NAME=family_finance")
        print("  export DB_USER=readwrite")
        print("  export DB_PASSWORD=your_password")
        sys.exit(1)

    # Import to database
    print(f"\nConnecting to {os.environ.get('DB_TYPE')}://{os.environ.get('DB_HOST')}:{os.environ.get('DB_PORT', '5432')}/{os.environ.get('DB_NAME', 'family_finance')}...")
    try:
        repo = get_repository()
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

    print("Importing transactions...")
    saved, skipped = repo.save_transactions(all_transactions)
    print(f"\nDone! {saved} saved, {skipped} skipped (duplicates)")


if __name__ == "__main__":
    main()
