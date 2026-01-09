"""
Westpac Scraper

Run with: python -m src.scrapers.westpac

Environment Variables:
    WESTPAC_CUSTOMER_ID: Westpac customer ID
    WESTPAC_PASSWORD: Westpac password
    HEADLESS: Set to "true" for headless mode (default: true)
    SLOW_MO: Milliseconds to slow down actions (default: 0 in headless, 500 in visible)
    SCREENSHOT_DIR: Directory for screenshots (default: data/scraper_state/screenshots)
    DOWNLOAD_DIR: Directory for downloaded files (default: incoming/westpac-homeloan-offset)
    LOCK_DIR: Directory for lock files (default: data/scraper_state)
    RANDOM_DELAY: Set to "true" to enable random delay before scraping (default: false)
    MAX_DELAY_HOURS: Maximum hours to delay when RANDOM_DELAY is enabled (default: 24)

What it does:
1. Opens browser (headless by default for automation)
2. Goes to Westpac login page
3. Fills in Customer ID and Password from environment
4. Clicks "Sign in"
5. Navigates to export page
6. Selects all accounts and exports last 7 days as CSV

Fail-Safe Mechanism:
- If any scrape attempt fails, a lock file is created
- Subsequent runs will refuse to execute while the lock file exists
- This prevents account lockouts from repeated failed login attempts
- To resume: manually delete the lock file after debugging
  Lock file location: data/scraper_state/westpac.lock
- Note: Lock file persists across container restarts but is cleared on LXC redeployment

Random Delay Feature:
- When RANDOM_DELAY=true, the scraper waits a random time before executing
- This spreads scraping throughout the day to avoid predictable patterns
- Cron triggers at a random time, then scraper adds additional randomization
"""

import argparse
import asyncio
import logging
import os
import random
import sys
from datetime import datetime
from pathlib import Path

# Load .env file if present
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Lock file configuration
LOCK_FILE_NAME = "westpac.lock"


def get_lock_file_path() -> Path:
    """Get the path to the lock file."""
    lock_dir = Path(os.getenv("LOCK_DIR", "data/scraper_state"))
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / LOCK_FILE_NAME


def is_locked() -> bool:
    """Check if the scraper is locked due to a previous failure."""
    return get_lock_file_path().exists()


def create_lock(reason: str) -> None:
    """Create a lock file with failure details."""
    lock_path = get_lock_file_path()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lock_content = f"""Westpac Scraper LOCKED
======================
Timestamp: {timestamp}
Reason: {reason}

This lock file was created because the scraper failed.
The scraper will NOT run again until this file is manually deleted.

To resume scraping after debugging:
  rm {lock_path}

Check screenshots in data/scraper_state/screenshots/ for debugging.
"""
    lock_path.write_text(lock_content)
    logger.warning(f"Lock file created: {lock_path}")


def clear_lock() -> None:
    """Remove the lock file (for manual use or after successful run)."""
    lock_path = get_lock_file_path()
    if lock_path.exists():
        lock_path.unlink()
        logger.info(f"Lock file removed: {lock_path}")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Westpac bank statement scraper")
    parser.add_argument(
        "--headless",
        action="store_true",
        default=os.getenv("HEADLESS", "true").lower() == "true",
        help="Run in headless mode (default: true)"
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Run with visible browser (overrides --headless)"
    )
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=int(os.getenv("SLOW_MO", "0")),
        help="Slow down actions by N milliseconds"
    )
    return parser.parse_args()


async def scrape_westpac(headless: bool = True, slow_mo: int = 0) -> bool:
    """
    Scrape Westpac and download transaction CSV.
    
    Args:
        headless: Run browser in headless mode
        slow_mo: Milliseconds to slow down actions
        
    Returns:
        True if successful, False otherwise
    """
    # Get credentials from environment
    customer_id = os.getenv("WESTPAC_CUSTOMER_ID")
    password = os.getenv("WESTPAC_PASSWORD")
    
    if not customer_id or not password:
        logger.error("Missing credentials: Set WESTPAC_CUSTOMER_ID and WESTPAC_PASSWORD")
        return False
    
    logger.info(f"Loaded credentials for customer ID: {customer_id[:3]}***")
    
    # Get directories from environment or use defaults
    screenshot_dir = Path(os.getenv("SCREENSHOT_DIR", "data/scraper_state/screenshots"))
    download_dir = Path(os.getenv("DOWNLOAD_DIR", "incoming/westpac-homeloan-offset"))
    
    # Create directories
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    download_dir.mkdir(parents=True, exist_ok=True)
    
    # Start Playwright
    async with async_playwright() as p:
        # Launch browser with consistent settings
        logger.info(f"Launching browser (headless={headless}, slow_mo={slow_mo}ms)...")
        browser = await p.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',  # Hide automation
            ]
        )
        
        try:
            # Create a new browser context with consistent settings
            # These settings match a typical Linux desktop Chrome browser
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                locale='en-AU',
                timezone_id='Australia/Sydney',
                # Disable webdriver detection
                extra_http_headers={
                    'Accept-Language': 'en-AU,en;q=0.9',
                }
            )
            
            # Create a new page from the context
            page = await context.new_page()
            
            # Step 1: Navigate to login page
            logger.info("Step 1: Navigating to Westpac login page...")
            await page.goto(
                "https://banking.westpac.com.au/wbc/banking/handler?"
                "TAM_OP=login&segment=personal&logout=false",
                timeout=60000
            )
            
            # Wait for page to load
            await page.wait_for_load_state("networkidle", timeout=30000)
            logger.info("Login page loaded")
            
            # Step 2: Find and fill Customer ID
            logger.info("Step 2: Filling Customer ID...")
            customer_id_field = page.locator("#fakeusername")
            await customer_id_field.fill(customer_id)
            logger.info("Customer ID entered")
            
            # Step 3: Find and fill Password
            logger.info("Step 3: Filling Password...")
            password_field = page.locator('input[type="password"]')
            await password_field.fill(password)
            logger.info("Password entered")
            
            # Step 4: Click Sign in button
            logger.info("Step 4: Clicking Sign in...")
            sign_in_button = page.get_by_role("button", name="Sign in")
            await sign_in_button.click()
            logger.info("Sign in clicked")
            
            # Wait for login to complete
            logger.info("Waiting for login to complete...")
            await page.wait_for_load_state("networkidle", timeout=60000)
            await asyncio.sleep(3)  # Extra wait for any redirects
            
            logger.info(f"Current URL after login: {page.url}")
            
            # Check for login errors
            if "error" in page.url.lower() or "login" in page.url.lower():
                await page.screenshot(path=str(screenshot_dir / "westpac_login_error.png"))
                logger.error("Login may have failed - still on login page")
                return False
            
            # Step 5: Navigate to export page
            logger.info("Step 5: Navigating to export page...")
            await page.goto(
                "https://banking.westpac.com.au/secure/banking/reportsandexports/exportparameters/2/",
                timeout=60000
            )
            await page.wait_for_load_state("networkidle", timeout=30000)
            logger.info("Export page loaded")
            
            # Take a screenshot
            await page.screenshot(path=str(screenshot_dir / "westpac_export_page.png"))
            logger.debug(f"Screenshot saved: {screenshot_dir / 'westpac_export_page.png'}")
            
            # Step 6: Click "Select multiple" link to open the popup
            logger.info("Step 6: Clicking 'Select multiple' link...")
            await page.locator("a.select-multiple").click()
            await asyncio.sleep(1)
            
            # Take screenshot to see popup
            await page.screenshot(path=str(screenshot_dir / "westpac_select_multiple_popup.png"))
            
            # Step 7: Click the "Select" checkbox (first checkbox - selects all)
            logger.info("Step 7: Clicking 'Select' checkbox to select all accounts...")
            await page.locator("#_selectall").click()
            await asyncio.sleep(0.5)
            logger.info("Select all checkbox clicked")
            
            # Take screenshot
            await page.screenshot(path=str(screenshot_dir / "westpac_all_selected.png"))
            
            # Step 8: Click "Continue" button
            logger.info("Step 8: Clicking 'Continue' button...")
            await page.locator("button.btn-submit.btn-primary").click()
            await asyncio.sleep(1)
            logger.info("Continue clicked")
            
            # Take screenshot to see result
            await page.screenshot(path=str(screenshot_dir / "westpac_accounts_selected.png"))
            
            # Step 9: Select date range - "Last 7 days"
            logger.info("Step 9: Selecting date range 'Last 7 days'...")
            
            # Click "a preset range" link to open the dropdown
            await page.locator("a.flyout-launcher.picker-text").click()
            await asyncio.sleep(0.5)
            
            # Click "Last 7 days" option
            await page.locator("a.link-icon.icon-arrow").filter(has_text="Last 7 days").click()
            await asyncio.sleep(0.5)
            logger.info("Date range selected: Last 7 days")
            
            # Take screenshot
            await page.screenshot(path=str(screenshot_dir / "westpac_date_selected.png"))
            
            # Step 10: Click Export and download CSV
            logger.info("Step 10: Clicking Export button and downloading CSV...")
            
            # Use expect_download to capture the file
            async with page.expect_download(timeout=30000) as download_info:
                await page.locator("button.export-link.btn-primary").click()
                logger.info("Clicked Export button, waiting for download...")
            
            download = await download_info.value
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"westpac_export_{timestamp}.csv"
            save_path = download_dir / filename
            
            # Save the file
            await download.save_as(str(save_path))
            logger.info(f"Downloaded: {save_path}")
            
            # Take final screenshot
            await page.screenshot(path=str(screenshot_dir / "westpac_export_complete.png"))
            
            logger.info(f"Export complete! File saved to: {save_path}")
            
            return True
            
        except PlaywrightTimeout as e:
            logger.error(f"Timeout error: {e}")
            try:
                await page.screenshot(path=str(screenshot_dir / "westpac_timeout_error.png"))
            except Exception:
                pass
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            try:
                await page.screenshot(path=str(screenshot_dir / "westpac_error.png"))
            except Exception:
                pass
            return False
            
        finally:
            # Close browser
            logger.info("Closing browser...")
            await browser.close()


async def main():
    """Main entry point."""
    args = parse_args()
    
    # Add random delay if RANDOM_DELAY environment variable is set
    random_delay_enabled = os.getenv("RANDOM_DELAY", "false").lower() == "true"
    if random_delay_enabled:
        # Random delay between 0 and MAX_DELAY_HOURS (default: 12 hours)
        # This adds unpredictability to scraping time
        max_delay_hours = int(os.getenv("MAX_DELAY_HOURS", "12"))
        max_delay_seconds = max_delay_hours * 3600
        delay_seconds = random.randint(0, max_delay_seconds)
        delay_hours = delay_seconds / 3600
        delay_minutes = (delay_seconds % 3600) / 60
        logger.info(f"Random delay enabled: waiting {int(delay_hours)}h {int(delay_minutes)}m ({delay_seconds}s) before running...")
        await asyncio.sleep(delay_seconds)
        logger.info("Random delay complete, starting scraper...")
    
    # Check for lock file FIRST - refuse to run if locked
    if is_locked():
        lock_path = get_lock_file_path()
        logger.error("=" * 60)
        logger.error("SCRAPER IS LOCKED - Previous run failed")
        logger.error("=" * 60)
        logger.error(f"Lock file exists: {lock_path}")
        logger.error("")
        logger.error("The scraper will NOT run to prevent account lockout.")
        logger.error("Please debug the issue manually, then remove the lock file:")
        logger.error(f"  rm {lock_path}")
        logger.error("")
        logger.error("Lock file contents:")
        logger.error("-" * 40)
        try:
            logger.error(lock_path.read_text())
        except Exception:
            pass
        logger.error("=" * 60)
        sys.exit(2)  # Exit code 2 = locked
    
    # --visible overrides --headless
    headless = not args.visible if args.visible else args.headless
    slow_mo = args.slow_mo if args.slow_mo else (500 if not headless else 0)
    
    success = await scrape_westpac(headless=headless, slow_mo=slow_mo)
    
    if success:
        logger.info("Scraper completed successfully")
        sys.exit(0)
    else:
        # Create lock file on failure to prevent subsequent runs
        create_lock("Scraper returned failure status. Check logs and screenshots for details.")
        logger.error("=" * 60)
        logger.error("SCRAPER FAILED - Lock file created")
        logger.error("=" * 60)
        logger.error("The scraper will NOT run again until manually unlocked.")
        logger.error(f"To resume after debugging: rm {get_lock_file_path()}")
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
