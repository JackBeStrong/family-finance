"""
Westpac Scraper - Step 1: Login Only

This is a minimal script to test the login flow.
Run with: python -m src.scrapers.westpac_step1

What it does:
1. Opens a VISIBLE browser (so you can watch)
2. Goes to Westpac login page
3. Fills in Customer ID and Password from .env
4. Clicks "Sign in"
5. Waits 30 seconds so you can see what happens next
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
        print("📍 Navigating to Westpac login page...")
        await page.goto(
            "https://banking.westpac.com.au/wbc/banking/handler?"
            "TAM_OP=login&segment=personal&logout=false"
        )
        
        # Wait for page to load
        await page.wait_for_load_state("networkidle")
        print("✅ Login page loaded")
        
        # Step 2: Find and fill Customer ID
        # The actual input field has id="fakeusername" (found from error message)
        print("\n🔍 Looking for Customer ID field...")
        
        # Use the specific ID we discovered
        customer_id_field = page.locator("#fakeusername")
        
        # Fill it in
        print(f"✏️  Filling Customer ID...")
        await customer_id_field.fill(customer_id)
        print("✅ Customer ID entered")
        
        # Step 3: Find and fill Password
        print("\n🔍 Looking for Password field...")
        # Password field is likely similar - let's use type="password"
        password_field = page.locator('input[type="password"]')
        
        print("✏️  Filling Password...")
        await password_field.fill(password)
        print("✅ Password entered")
        
        # Step 4: Click Sign in button
        print("\n🔍 Looking for Sign in button...")
        sign_in_button = page.get_by_role("button", name="Sign in")
        
        print("🖱️  Clicking Sign in...")
        await sign_in_button.click()
        print("✅ Sign in clicked!")
        
        # Step 5: Wait and observe
        print("\n⏳ Waiting 30 seconds so you can see what happens...")
        print("   (Watch the browser window)")
        print("   - If 2FA appears, note what it looks like")
        print("   - If login succeeds, note the URL")
        print("   - If error appears, note the message")
        
        await asyncio.sleep(30)
        
        # Print final URL
        print(f"\n📍 Final URL: {page.url}")
        
        # Take a screenshot for reference
        screenshot_path = Path("data/scraper_state/screenshots")
        screenshot_path.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path / "westpac_after_login.png"))
        print(f"📸 Screenshot saved to: {screenshot_path / 'westpac_after_login.png'}")
        
        # Close browser
        print("\n🔒 Closing browser...")
        await browser.close()
        
    print("\n✅ Done! Check the screenshot to see the result.")


if __name__ == "__main__":
    asyncio.run(main())
