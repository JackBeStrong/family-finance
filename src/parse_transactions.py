#!/usr/bin/env python3
"""
Transaction Parser CLI

Command-line tool for parsing bank transaction CSV files and outputting
normalized transaction data, with optional database storage.

Usage:
    python -m src.parse_transactions <input_path> [options]
    
Examples:
    # Parse a single file and save to files
    python -m src.parse_transactions bank-transactions-raw-csv/westpac-credit-card/Data_export_011125-301125.csv
    
    # Parse all files in a directory
    python -m src.parse_transactions bank-transactions-raw-csv/ --recursive
    
    # Parse and save to database
    python -m src.parse_transactions bank-transactions-raw-csv/ -r --save-to-db
    
    # Save to database only (no file output)
    python -m src.parse_transactions bank-transactions-raw-csv/ -r --save-to-db --no-file-output
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers import ParserFactory, Transaction
from src.parsers.base import save_transactions_json, save_transactions_csv


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Parse bank transaction CSV files into normalized format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s bank-transactions-raw-csv/westpac-credit-card/Data_export.csv
  %(prog)s bank-transactions-raw-csv/ --recursive
  %(prog)s bank-transactions-raw-csv/ -r --save-to-db
  %(prog)s bank-transactions-raw-csv/ -r --save-to-db --no-file-output
        """
    )
    
    parser.add_argument(
        "input_path",
        type=Path,
        help="Input CSV file or directory"
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=Path("output/normalized"),
        help="Output directory (default: output/normalized)"
    )
    
    parser.add_argument(
        "--output-format", "-f",
        choices=["json", "csv", "both"],
        default="both",
        help="Output format (default: both)"
    )
    
    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Recursively process directories"
    )
    
    parser.add_argument(
        "--parser", "-p",
        type=str,
        default=None,
        help="Force specific parser (e.g., 'westpac', 'anz')"
    )
    
    parser.add_argument(
        "--list-parsers",
        action="store_true",
        help="List available parsers and exit"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    # Database options
    parser.add_argument(
        "--save-to-db",
        action="store_true",
        help="Save parsed transactions to SQLite database"
    )
    
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/transactions.db",
        help="Path to SQLite database (default: data/transactions.db)"
    )
    
    parser.add_argument(
        "--no-file-output",
        action="store_true",
        help="Skip file output (use with --save-to-db)"
    )
    
    return parser.parse_args()


def process_file(file_path: Path, parser_name: str = None, 
                 verbose: bool = False) -> list[Transaction]:
    """Process a single CSV file."""
    if verbose:
        print(f"Processing: {file_path}")
    
    try:
        transactions = ParserFactory.parse_file(file_path, parser_name)
        if verbose:
            print(f"  Parsed {len(transactions)} transactions")
        return transactions
    except ValueError as e:
        print(f"  Warning: {e}")
        return []
    except Exception as e:
        print(f"  Error: {e}")
        return []


def save_output(transactions: list[Transaction], output_dir: Path, 
                base_name: str, output_format: str):
    """Save transactions to output files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if output_format in ("json", "both"):
        json_path = output_dir / f"{base_name}.json"
        save_transactions_json(transactions, json_path)
        print(f"  Saved: {json_path}")
    
    if output_format in ("csv", "both"):
        csv_path = output_dir / f"{base_name}.csv"
        save_transactions_csv(transactions, csv_path)
        print(f"  Saved: {csv_path}")


def main():
    """Main entry point."""
    args = parse_args()
    
    # List parsers and exit
    if args.list_parsers:
        print("Available parsers:")
        for name in ParserFactory.list_parsers():
            parser = ParserFactory.get_parser(name)
            print(f"  - {name}: {parser.__class__.__doc__.split(chr(10))[0].strip()}")
        return 0
    
    input_path = args.input_path
    
    if not input_path.exists():
        print(f"Error: Input path does not exist: {input_path}")
        return 1
    
    # Determine if we should output to files
    output_to_files = not args.no_file_output
    
    all_transactions = []
    
    if input_path.is_file():
        # Process single file
        transactions = process_file(input_path, args.parser, args.verbose)
        if transactions:
            all_transactions.extend(transactions)
            if output_to_files:
                base_name = input_path.stem + "_normalized"
                save_output(transactions, args.output_dir, base_name, args.output_format)
    
    elif input_path.is_dir():
        # Process directory
        if args.recursive:
            files = list(input_path.rglob("*.csv"))
        else:
            files = list(input_path.glob("*.csv"))
        
        print(f"Found {len(files)} CSV files")
        
        for file_path in files:
            transactions = process_file(file_path, args.parser, args.verbose)
            if transactions:
                all_transactions.extend(transactions)
                
                if output_to_files:
                    # Create output path preserving directory structure
                    relative_path = file_path.relative_to(input_path)
                    output_subdir = args.output_dir / relative_path.parent
                    base_name = file_path.stem + "_normalized"
                    save_output(transactions, output_subdir, base_name, args.output_format)
        
        # Also save combined output
        if all_transactions and output_to_files:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            combined_name = f"all_transactions_{timestamp}"
            save_output(all_transactions, args.output_dir, combined_name, args.output_format)
    
    # Save to database if requested
    if args.save_to_db and all_transactions:
        from src.database import get_repository
        
        print(f"\nSaving to database: {args.db_path}")
        repo = get_repository(db_path=args.db_path)
        saved, skipped = repo.save_transactions(all_transactions)
        print(f"  Saved: {saved} transactions")
        print(f"  Skipped (duplicates): {skipped} transactions")
        print(f"  Total in database: {repo.count_transactions()}")
    
    # Summary
    print(f"\nTotal transactions parsed: {len(all_transactions)}")
    
    # Group by bank
    by_bank = {}
    for t in all_transactions:
        by_bank.setdefault(t.bank_source, []).append(t)
    
    for bank, txns in sorted(by_bank.items()):
        print(f"  {bank}: {len(txns)} transactions")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
