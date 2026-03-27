"""
NAB (National Australia Bank) PDF Statement Parser

Handles NAB credit card PDF statement exports with the following format:
- PDF statements (not CSV - account is closed, only PDF downloads available)
- Transaction table columns: Date processed, Date of transaction, Card No, Details, Amount A$
- Date format: DD/MM/YY
- Amounts: Positive numbers for debits, CR suffix for credits (e.g., "186.49CR")
- Foreign transactions have a follow-up line: "FRGNAMT:22.00 USdollar"
- Account number extracted from page 1 header
- Statement period extracted from page 1 header

Requires: pdfplumber
"""

import re
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

from .base import (
    BaseParser,
    Transaction,
    RawTransaction,
    TransactionType,
    AccountType,
)


@dataclass
class NABConfig:
    """Configuration for NAB parser."""
    # Date format (DD/MM/YY)
    date_format: str = "%d/%m/%y"

    # Default account type (NAB statements are credit card)
    default_account_type: AccountType = AccountType.CREDIT_CARD


# Regex to match a transaction line from pdfplumber text extraction
# Format: DD/MM/YY DD/MM/YY V{card} {description} {amount}[CR]
# The description and amount are separated by whitespace, with amount right-aligned
TRANSACTION_LINE_RE = re.compile(
    r'^(\d{2}/\d{2}/\d{2})\s+'       # Date processed
    r'(\d{2}/\d{2}/\d{2})\s+'        # Date of transaction
    r'(V\d{4})\s+'                    # Card number (e.g., V7786)
    r'(.+?)\s+'                       # Details (non-greedy, then whitespace)
    r'([\d,]+\.\d{2})(CR)?$'         # Amount with optional CR suffix
)

# Regex for foreign amount continuation line
FOREIGN_AMOUNT_RE = re.compile(
    r'^FRGNAMT:([\d,]+\.\d{2})\s+(\w+)$'
)

# Regex for statement period on page 1
STATEMENT_PERIOD_RE = re.compile(
    r'StatementPeriod\s+(\d{2}\w{3}\d{2})-(\d{2}\w{3}\d{2})'
)

# Regex for account number on page 1
ACCOUNT_NUMBER_RE = re.compile(
    r'VisaAccountNumber\s+([\d\s]+)'
)

# Regex for interest/fee lines that appear as transactions
INTEREST_LINE_RE = re.compile(
    r'^(\d{2}/\d{2}/\d{2})\s+'
    r'(.+?)\s+'
    r'([\d,]+\.\d{2})(CR)?$'
)


class NABParser(BaseParser):
    """
    Parser for NAB credit card PDF statement exports.

    NAB PDF statements contain transaction tables across multiple pages.
    Each page with transactions has a "Transaction details" header followed
    by column headers and transaction rows.

    This parser uses pdfplumber to extract text from PDFs and then
    parses the transaction lines using regex patterns.
    """

    def __init__(self, config: Optional[NABConfig] = None):
        """
        Initialize the NAB parser.

        Args:
            config: Optional configuration override
        """
        self.config = config or NABConfig()

    @property
    def bank_name(self) -> str:
        return "nab"

    def can_parse(self, file_path: Path) -> bool:
        """
        Check if this file is a NAB PDF statement.

        Detection is based on:
        1. PDF file extension
        2. Directory name OR filename contains 'nab'
        3. OR PDF content contains NAB-specific markers
        """
        file_path = Path(file_path)

        if not file_path.suffix.lower() == '.pdf':
            return False

        # Check if directory name or filename indicates NAB
        dir_name = file_path.parent.name.lower()
        filename = file_path.stem.lower()

        nab_keywords = ['nab', 'national-australia']
        if any(kw in dir_name or kw in filename for kw in nab_keywords):
            return True

        # Fall back to content detection - check first page for NAB markers
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                if pdf.pages:
                    text = pdf.pages[0].extract_text() or ''
                    # Look for NAB-specific content
                    nab_markers = [
                        'NABCardServiceCentre',
                        'NAB Card Service Centre',
                        'nab.com.au',
                        'NABQantas',
                        'NAB Qantas',
                    ]
                    return any(marker in text for marker in nab_markers)
        except Exception:
            pass

        return False

    def parse(self, file_path: Path) -> List[Transaction]:
        """
        Parse NAB PDF statement and return normalized transactions.

        Args:
            file_path: Path to the NAB PDF statement file

        Returns:
            List of normalized Transaction objects
        """
        import pdfplumber

        file_path = Path(file_path)
        transactions = []

        with pdfplumber.open(file_path) as pdf:
            # Extract account info from page 1
            account_number, card_last4 = self._extract_account_info(pdf)

            # Parse transactions from all pages
            parsed_data = []
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text:
                    continue

                page_transactions = self._parse_page_transactions(
                    text, page_num + 1, file_path, account_number
                )
                parsed_data.extend(page_transactions)

        # Assign occurrence numbers for identical transactions
        parsed_data = self._assign_occurrence_numbers(parsed_data)

        # Create Transaction objects with proper IDs
        for data in parsed_data:
            trans_id = self._generate_transaction_id(
                data['date'], data['account_id'], data['amount'],
                data['description'], data['occurrence']
            )

            transaction = Transaction(
                id=trans_id,
                date=data['date'],
                amount=data['amount'],
                description=data['description'],
                account_id=data['account_id'],
                account_type=data['account_type'],
                bank_source=self.bank_name,
                source_file=str(file_path),
                balance=None,  # NAB statements don't show running balance per transaction
                original_category=None,
                transaction_type=data['transaction_type'],
                merchant_name=data['merchant_name'],
                location=data['location'],
                foreign_amount=data.get('foreign_amount'),
                foreign_currency=data.get('foreign_currency'),
                raw_transaction=data['raw_transaction'],
            )
            transactions.append(transaction)

        return transactions

    def _extract_account_info(self, pdf) -> Tuple[str, str]:
        """
        Extract account number and card last 4 digits from page 1.

        Returns:
            Tuple of (account_number, card_last4)
        """
        if not pdf.pages:
            return ('nab-unknown', '0000')

        text = pdf.pages[0].extract_text() or ''

        # Extract account number
        account_match = ACCOUNT_NUMBER_RE.search(text)
        if account_match:
            account_number = account_match.group(1).strip().replace(' ', '')
            # Use last 4 digits as short identifier
            card_last4 = account_number[-4:] if len(account_number) >= 4 else account_number
        else:
            # Try to extract from filename (e.g., 7786-20240605-statement.pdf)
            account_number = 'nab-unknown'
            card_last4 = '0000'

        return (account_number, card_last4)

    def _parse_page_transactions(self, text: str, page_num: int,
                                  file_path: Path,
                                  account_number: str) -> List[dict]:
        """
        Parse transaction lines from a single page's text.

        Args:
            text: Extracted text from the page
            page_num: Page number (1-based)
            file_path: Source file path
            account_number: Account number for this statement

        Returns:
            List of intermediate transaction data dicts
        """
        parsed = []
        lines = text.split('\n')

        # Find where transaction data starts (after "Transaction details" header)
        in_transactions = False
        skip_header_lines = 0

        for i, line in enumerate(lines):
            line = line.strip()

            # Detect start of transaction section
            if 'Transaction details' in line or 'Transaction  details' in line:
                in_transactions = True
                skip_header_lines = 2  # Skip "Date processed..." and "Date of transaction..." header lines
                continue

            # Skip column header lines
            if skip_header_lines > 0:
                if any(h in line for h in ['Date', 'processed', 'transaction', 'Card', 'Details', 'Amount']):
                    skip_header_lines -= 1
                    continue
                # If line doesn't match header pattern, might be a transaction already
                if not line or line.startswith('No'):
                    skip_header_lines -= 1
                    continue

            if not in_transactions:
                continue

            # Stop at page footer markers
            if any(marker in line for marker in [
                'Detachhere', 'Detach here',
                'Howtoidentify', 'How to identify',
                'Unauthorisedorunknown', 'Unauthorised or unknown',
                'Yourbalanceandinterest', 'Your balance and interest',
                'QantasFrequentFlyer', 'Qantas Frequent Flyer',
                'CREDITBALANCE', 'CREDIT BALANCE',
                'NABDOESNOTPAY', 'NAB DOES NOT PAY',
            ]):
                in_transactions = False
                continue

            # Skip empty lines and page markers
            if not line or line.startswith('Page') or line.startswith(')'):
                continue

            # Skip barcode/reference lines (single digits or short codes)
            if len(line) <= 10 and not line[0].isdigit():
                continue

            # Try to match a transaction line
            match = TRANSACTION_LINE_RE.match(line)
            if match:
                date_processed_str = match.group(1)
                date_transaction_str = match.group(2)
                card_no = match.group(3)
                details = match.group(4).strip()
                amount_str = match.group(5)
                is_credit = match.group(6) is not None  # CR suffix

                # Check if next line is a foreign amount
                foreign_amount = None
                foreign_currency = None
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    frgn_match = FOREIGN_AMOUNT_RE.match(next_line)
                    if frgn_match:
                        foreign_amount = Decimal(frgn_match.group(1).replace(',', ''))
                        foreign_currency = frgn_match.group(2)

                # Parse the transaction
                txn_data = self._build_transaction_data(
                    date_processed_str=date_processed_str,
                    date_transaction_str=date_transaction_str,
                    card_no=card_no,
                    details=details,
                    amount_str=amount_str,
                    is_credit=is_credit,
                    foreign_amount=foreign_amount,
                    foreign_currency=foreign_currency,
                    account_number=account_number,
                    file_path=file_path,
                    page_num=page_num,
                    line_num=i + 1,
                    raw_line=line,
                )
                if txn_data:
                    parsed.append(txn_data)

        return parsed

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """
        Replace non-ASCII characters from PDF extraction with safe equivalents.

        PDF text extraction can produce artifacts like ø, ñ, etc. that are
        actually separators or formatting characters in the original PDF.
        """
        import unicodedata
        # Normalize unicode, then replace any remaining non-ASCII with space
        normalized = unicodedata.normalize('NFKD', text)
        # Keep ASCII chars, replace others with space
        sanitized = ''.join(c if ord(c) < 128 else ' ' for c in normalized)
        # Collapse multiple spaces
        return ' '.join(sanitized.split())

    def _build_transaction_data(self, date_processed_str: str,
                                 date_transaction_str: str,
                                 card_no: str, details: str,
                                 amount_str: str, is_credit: bool,
                                 foreign_amount: Optional[Decimal],
                                 foreign_currency: Optional[str],
                                 account_number: str,
                                 file_path: Path, page_num: int,
                                 line_num: int, raw_line: str) -> Optional[dict]:
        """Build a transaction data dict from parsed fields."""
        try:
            # Sanitize details to remove PDF extraction artifacts (non-ASCII chars)
            details = self._sanitize_text(details)

            # Parse dates
            trans_date = self._parse_date(date_transaction_str, self.config.date_format)

            # Parse amount
            amount = Decimal(amount_str.replace(',', ''))
            if is_credit:
                # Credits are positive (money coming in / refunds / payments)
                trans_type = TransactionType.CREDIT
            else:
                # Debits are negative (money going out / purchases)
                amount = -amount
                trans_type = TransactionType.DEBIT

            # Check if it's a transfer/payment
            if self._is_transfer(details):
                trans_type = TransactionType.TRANSFER

            # Extract card last 4 from card_no (e.g., "V7786" -> "7786")
            card_last4 = card_no[1:] if card_no.startswith('V') else card_no

            # Use card last 4 as account ID
            account_id = card_last4

            # Extract merchant info
            merchant_name, location = self._parse_details(details)

            # Create raw transaction for audit trail
            raw_transaction = RawTransaction(
                source_file=str(file_path),
                source_bank=self.bank_name,
                row_number=line_num,
                raw_fields={
                    'date_processed': date_processed_str,
                    'date_transaction': date_transaction_str,
                    'card_no': card_no,
                    'details': details,
                    'amount': amount_str,
                    'is_credit': str(is_credit),
                    'page': str(page_num),
                    'raw_line': raw_line,
                },
            )

            if foreign_amount is not None:
                raw_transaction.raw_fields['foreign_amount'] = str(foreign_amount)
                raw_transaction.raw_fields['foreign_currency'] = foreign_currency or ''

            return {
                'date': trans_date,
                'amount': amount,
                'description': details,
                'account_id': account_id,
                'account_type': self.config.default_account_type,
                'transaction_type': trans_type,
                'merchant_name': merchant_name,
                'location': location,
                'foreign_amount': foreign_amount,
                'foreign_currency': foreign_currency,
                'raw_transaction': raw_transaction,
            }

        except Exception as e:
            print(f"Warning: Failed to parse NAB transaction line {line_num} on page {page_num}: {e}")
            print(f"  Line: {raw_line}")
            return None

    def _is_transfer(self, details: str) -> bool:
        """Check if transaction is an internal transfer or payment."""
        transfer_keywords = [
            'INTERNETPAYMENT',
            'INTERNET PAYMENT',
            'LinkedAccTrns',
            'Linked Acc Trns',
            'INTERNETBPAY',
            'INTERNET BPAY',
        ]
        details_upper = details.upper()
        return any(kw.upper() in details_upper for kw in transfer_keywords)

    def _parse_details(self, details: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract merchant name and location from details.

        NAB details are typically concatenated merchant name + location,
        e.g., "HUNGRYPANDAAUMELBOURNECBD" or "TRANSPORTFORNSWTAPSYDNEY"

        Since NAB doesn't use consistent separators, we try common patterns.
        """
        if not details:
            return None, None

        # Known patterns with location suffixes
        location_patterns = [
            # "MERCHANTNAMEcity" patterns - try to split at known city names
            (r'^(.+?)(SYDNEY|MELBOURNE|BRISBANE|PERTH|ADELAIDE|HOBART|DARWIN|CANBERRA'
             r'|WATERLOO|ZETLAND|RANDWICK|PAGEWOOD|EASTWOOD|KENSINGTON|MULGRAVE'
             r'|NORTHSYDNEY|SURRY\s*HILLS|SurryHills|HAYMARKET|DOCKLANDS'
             r'|MOOREPARK|NORTHRYDE|PRESTON|HAWTHORNEAST|BARANGAROO'
             r'|EASTGARDENS|STRATHFIELD|ALEXANDRIA)(.*)$', re.IGNORECASE),
        ]

        for pattern_str, flags in location_patterns:
            match = re.match(pattern_str, details, flags)
            if match:
                merchant = match.group(1).strip()
                location = match.group(2).strip()
                # Clean up merchant name
                if merchant:
                    return merchant, location
                return details, location

        # Internet payment patterns
        if 'INTERNETPAYMENT' in details or 'INTERNET PAYMENT' in details:
            return 'NAB Internet Payment', None

        if 'INTERNETBPAY' in details or 'INTERNET BPAY' in details:
            # Try to extract BPAY payee
            bpay_match = re.match(r'INTERNETBPAY\s*(.+)', details, re.IGNORECASE)
            if bpay_match:
                return f"BPAY {bpay_match.group(1).strip()}", None
            return 'BPAY Payment', None

        # NAB fee patterns
        if 'NABINTNLTRANFEE' in details or 'NAB INTNL TRAN FEE' in details:
            return 'NAB International Transaction Fee', None

        return details, None
