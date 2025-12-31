"""
Westpac Scraper

Run with: python -m src.scrapers.westpac

What it does:
1. Opens a VISIBLE browser (so you can watch)
2. Goes to Westpac login page
3. Fills in Customer ID and Password from .env
4. Clicks "Sign in"
5. Navigates to export page
6. Waits so you can see what happens
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

# Load .env file
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright


async def main():
    # Get credentials from .env
    customer_id = os.getenv("WESTPAC_CUSTOMER_ID")
    password = os.getenv("WESTPAC_PASSWORD")
    
    if not customer_id or not password:
        print("❌ Error: Set WESTPAC_CUSTOMER_ID and WESTPAC_PASSWORD in .env")
        return
    
    print(f"✅ Loaded credentials for customer ID: {customer_id[:3]}***")
    
    # Start Playwright
    async with async_playwright() as p:
        # Launch browser - VISIBLE (headless=False) so you can watch
        print("\n🌐 Launching browser...")
        browser = await p.chromium.launch(
            headless=False,  # Show the browser window
            slow_mo=500,     # Slow down actions by 500ms so you can see them
        )
        
        # Create a new page
        page = await browser.new_page()
        
        # Step 1: Navigate to login page
        print("📍 Step 1: Navigating to Westpac login page...")
        await page.goto(
            "https://banking.westpac.com.au/wbc/banking/handler?"
            "TAM_OP=login&segment=personal&logout=false"
        )
        
        # Wait for page to load
        await page.wait_for_load_state("networkidle")
        print("✅ Login page loaded")
        
        # Step 2: Find and fill Customer ID
        print("\n📍 Step 2: Filling Customer ID...")
        customer_id_field = page.locator("#fakeusername")
        await customer_id_field.fill(customer_id)
        print("✅ Customer ID entered")
        
        # Step 3: Find and fill Password
        print("\n📍 Step 3: Filling Password...")
        password_field = page.locator('input[type="password"]')
        await password_field.fill(password)
        print("✅ Password entered")
        
        # Step 4: Click Sign in button
        print("\n📍 Step 4: Clicking Sign in...")
        sign_in_button = page.get_by_role("button", name="Sign in")
        await sign_in_button.click()
        print("✅ Sign in clicked!")
        
        # Wait for login to complete
        print("\n⏳ Waiting for login to complete...")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)  # Extra wait for any redirects
        
        print(f"📍 Current URL after login: {page.url}")
        
        # Step 5: Navigate to export page
        print("\n📍 Step 5: Navigating to export page...")
        await page.goto(
            "https://banking.westpac.com.au/secure/banking/reportsandexports/exportparameters/2/"
        )
        await page.wait_for_load_state("networkidle")
        print("✅ Export page loaded")
        
        # Take a screenshot
        screenshot_path = Path("data/scraper_state/screenshots")
        screenshot_path.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path / "westpac_export_page.png"))
        print(f"📸 Screenshot saved to: {screenshot_path / 'westpac_export_page.png'}")
        
        # Step 6: Click "Select multiple" link to open the popup
        print("\n📍 Step 6: Clicking 'Select multiple' link...")
        await page.locator("a.select-multiple").click()
        await asyncio.sleep(1)
        
        # Take screenshot to see popup
        await page.screenshot(path=str(screenshot_path / "westpac_select_multiple_popup.png"))
        print("📸 Screenshot: westpac_select_multiple_popup.png")
        
        # Step 7: Click the "Select" checkbox (first checkbox - selects all)
        print("\n📍 Step 7: Clicking 'Select' checkbox to select all accounts...")
        # From DevTools: <input type="checkbox" id="_selectall" name="selectall" class="table-row-multi-select">
        await page.locator("#_selectall").click()
        await asyncio.sleep(0.5)
        print("✅ Select all checkbox clicked")
        
        # Take screenshot
        await page.screenshot(path=str(screenshot_path / "westpac_all_selected.png"))
        print("📸 Screenshot: westpac_all_selected.png")
        
        # Step 8: Click "Continue" button
        print("\n📍 Step 8: Clicking 'Continue' button...")
        await page.locator("button.btn-submit.btn-primary").click()
        await asyncio.sleep(1)
        print("✅ Continue clicked")
        
        # Take screenshot to see result
        await page.screenshot(path=str(screenshot_path / "westpac_accounts_selected.png"))
        print(f"📸 Screenshot: westpac_accounts_selected.png")
        
        # Step 9: Select date range - "Last 7 days"
        print("\n📍 Step 9: Selecting date range 'Last 7 days'...")
        
        # Click "a preset range" link to open the dropdown
        print("🖱️  Clicking 'a preset range' link...")
        await page.locator("a.flyout-launcher.picker-text").click()
        await asyncio.sleep(0.5)
        
        # Click "Last 7 days" option
        print("🖱️  Clicking 'Last 7 days'...")
        await page.locator("a.link-icon.icon-arrow").filter(has_text="Last 7 days").click()
        await asyncio.sleep(0.5)
        print("✅ Date range selected: Last 7 days")
        
        # Take screenshot
        await page.screenshot(path=str(screenshot_path / "westpac_date_selected.png"))
        print("📸 Screenshot: westpac_date_selected.png")
        
        # Step 10: Click Export and download CSV
        print("\n📍 Step 10: Clicking Export button and downloading CSV...")
        
        # Set up download handler BEFORE clicking
        download_dir = Path("incoming/westpac-homeloan-offset")
        download_dir.mkdir(parents=True, exist_ok=True)
        
        # Use expect_download to capture the file
        async with page.expect_download() as download_info:
            await page.locator("button.export-link.btn-primary").click()
            print("🖱️  Clicked Export button, waiting for download...")
        
        download = await download_info.value
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"westpac_export_{timestamp}.csv"
        save_path = download_dir / filename
        
        # Save the file
        await download.save_as(str(save_path))
        print(f"✅ Downloaded: {save_path}")
        
        # Take final screenshot
        await page.screenshot(path=str(screenshot_path / "westpac_export_complete.png"))
        print("📸 Screenshot: westpac_export_complete.png")
        
        print("\n🎉 Export complete!")
        print(f"   File saved to: {save_path}")
        
        await asyncio.sleep(5)
        
        # Print final URL
        print(f"\n📍 Final URL: {page.url}")
        
        # Close browser
        print("\n🔒 Closing browser...")
        await browser.close()
        
    print("\n✅ Done! Check the screenshot to see the export page.")


if __name__ == "__main__":
    asyncio.run(main())
