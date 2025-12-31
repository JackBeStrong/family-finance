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
        
        # Step 6: Click the account dropdown and select "All"
        print("\n📍 Step 6: Selecting all accounts...")
        
        # From DevTools inspection: the input has id="Accounts_1"
        # Click on it to open the dropdown
        print("🖱️  Clicking account dropdown (id=Accounts_1)...")
        await page.locator("#Accounts_1").click()
        await asyncio.sleep(1)
        
        # Take screenshot to see dropdown state
        await page.screenshot(path=str(screenshot_path / "westpac_dropdown_open.png"))
        print("📸 Screenshot: westpac_dropdown_open.png")
        
        # Now click "All" option - it's an <a class="select-all">
        print("🖱️  Clicking 'All' option (a.select-all)...")
        await page.locator("a.select-all").click()
        print("✅ All accounts selected")
        
        await asyncio.sleep(2)
        
        # Take another screenshot to see the result
        await page.screenshot(path=str(screenshot_path / "westpac_accounts_selected.png"))
        print(f"📸 Screenshot saved to: {screenshot_path / 'westpac_accounts_selected.png'}")
        
        # Step 7: Wait and observe what's next
        print("\n⏳ Waiting 30 seconds so you can see what's next...")
        print("   Look for:")
        print("   - Export/Download button")
        print("   - Format selector (CSV)")
        
        await asyncio.sleep(30)
        
        # Print final URL
        print(f"\n📍 Final URL: {page.url}")
        
        # Close browser
        print("\n🔒 Closing browser...")
        await browser.close()
        
    print("\n✅ Done! Check the screenshot to see the export page.")


if __name__ == "__main__":
    asyncio.run(main())
