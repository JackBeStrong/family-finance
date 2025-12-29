#!/usr/bin/env python3
"""
File Watcher Service

Monitors a folder for new bank statement CSV files, parses them,
and imports transactions to the SQLite database.

Usage:
    python -m src.watcher --watch-dir /path/to/incoming --data-dir /path/to/data
    
Environment Variables:
    WATCH_DIR: Directory to watch for new CSV files (default: ./incoming)
    DATA_DIR: Directory for database and processed files (default: ./data)
    POLL_INTERVAL: Seconds between folder scans (default: 30)
"""

import argparse
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers import ParserFactory
from src.database import get_repository

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


class FileWatcher:
    """
    Watches a directory for new CSV files and processes them.
    
    Workflow:
    1. Scan watch_dir for CSV files
    2. Parse each file using ParserFactory
    3. Import transactions to database
    4. Move processed file to processed_dir
    """
    
    def __init__(
        self,
        watch_dir: Path,
        data_dir: Path,
        poll_interval: int = 30,
    ):
        """
        Initialize the file watcher.
        
        Args:
            watch_dir: Directory to watch for new CSV files
            data_dir: Directory for database and processed files
            poll_interval: Seconds between folder scans
        """
        self.watch_dir = Path(watch_dir)
        self.data_dir = Path(data_dir)
        self.processed_dir = self.data_dir / "processed"
        self.failed_dir = self.data_dir / "failed"
        self.db_path = self.data_dir / "transactions.db"
        self.poll_interval = poll_interval
        
        # Create directories
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize repository
        self.repo = get_repository(db_path=str(self.db_path))
        
        logger.info(f"File watcher initialized")
        logger.info(f"  Watch directory: {self.watch_dir}")
        logger.info(f"  Data directory: {self.data_dir}")
        logger.info(f"  Database: {self.db_path}")
        logger.info(f"  Poll interval: {self.poll_interval}s")
    
    def scan_for_files(self) -> list[Path]:
        """Scan watch directory for CSV files."""
        csv_files = list(self.watch_dir.glob("*.csv"))
        # Also check subdirectories (one level deep)
        csv_files.extend(self.watch_dir.glob("*/*.csv"))
        return sorted(csv_files)
    
    def process_file(self, file_path: Path) -> bool:
        """
        Process a single CSV file.
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            True if processed successfully, False otherwise
        """
        logger.info(f"Processing: {file_path}")
        
        try:
            # Parse the file
            transactions = ParserFactory.parse_file(file_path)
            
            if not transactions:
                logger.warning(f"  No transactions parsed from {file_path}")
                return False
            
            logger.info(f"  Parsed {len(transactions)} transactions")
            
            # Save to database
            saved, skipped = self.repo.save_transactions(transactions)
            logger.info(f"  Saved: {saved}, Skipped (duplicates): {skipped}")
            
            # Move to processed directory
            self._move_to_processed(file_path)
            
            return True
            
        except ValueError as e:
            logger.error(f"  Parse error: {e}")
            self._move_to_failed(file_path, str(e))
            return False
        except Exception as e:
            logger.error(f"  Unexpected error: {e}")
            self._move_to_failed(file_path, str(e))
            return False
    
    def _move_to_processed(self, file_path: Path) -> None:
        """Move a processed file to the processed directory."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Preserve subdirectory structure if any
        if file_path.parent != self.watch_dir:
            subdir = file_path.parent.name
            dest_dir = self.processed_dir / subdir
            dest_dir.mkdir(exist_ok=True)
        else:
            dest_dir = self.processed_dir
        
        # Add timestamp to filename to avoid collisions
        dest_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
        dest_path = dest_dir / dest_name
        
        shutil.move(str(file_path), str(dest_path))
        logger.info(f"  Moved to: {dest_path}")
    
    def _move_to_failed(self, file_path: Path, error: str) -> None:
        """Move a failed file to the failed directory."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
        dest_path = self.failed_dir / dest_name
        
        shutil.move(str(file_path), str(dest_path))
        
        # Write error log
        error_log = self.failed_dir / f"{file_path.stem}_{timestamp}.error"
        error_log.write_text(f"Error processing {file_path.name}:\n{error}")
        
        logger.info(f"  Moved to failed: {dest_path}")
    
    def run_once(self) -> int:
        """
        Run a single scan and process cycle.
        
        Returns:
            Number of files processed
        """
        files = self.scan_for_files()
        
        if not files:
            return 0
        
        logger.info(f"Found {len(files)} CSV file(s)")
        
        processed = 0
        for file_path in files:
            if self.process_file(file_path):
                processed += 1
        
        return processed
    
    def run(self) -> None:
        """Run the watcher in continuous mode."""
        logger.info("Starting file watcher (Ctrl+C to stop)")
        
        try:
            while True:
                processed = self.run_once()
                
                if processed > 0:
                    total = self.repo.count_transactions()
                    logger.info(f"Total transactions in database: {total}")
                
                time.sleep(self.poll_interval)
                
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.repo.close()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Watch for bank statement CSV files and import to database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--watch-dir", "-w",
        type=Path,
        default=os.environ.get("WATCH_DIR", "./incoming"),
        help="Directory to watch for CSV files (default: ./incoming or $WATCH_DIR)"
    )
    
    parser.add_argument(
        "--data-dir", "-d",
        type=Path,
        default=os.environ.get("DATA_DIR", "./data"),
        help="Directory for database and processed files (default: ./data or $DATA_DIR)"
    )
    
    parser.add_argument(
        "--poll-interval", "-i",
        type=int,
        default=int(os.environ.get("POLL_INTERVAL", "30")),
        help="Seconds between folder scans (default: 30 or $POLL_INTERVAL)"
    )
    
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (don't watch continuously)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    watcher = FileWatcher(
        watch_dir=args.watch_dir,
        data_dir=args.data_dir,
        poll_interval=args.poll_interval,
    )
    
    if args.once:
        processed = watcher.run_once()
        total = watcher.repo.count_transactions()
        logger.info(f"Processed {processed} file(s). Total transactions: {total}")
        watcher.repo.close()
        return 0
    else:
        watcher.run()
        return 0


if __name__ == "__main__":
    sys.exit(main())
