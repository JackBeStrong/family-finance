"""
Base scraper class with session persistence and Telegram integration.

This provides the foundation for bank-specific scrapers with:
- Browser session persistence (cookies/state) to minimize 2FA prompts
- Telegram bot integration for 2FA code input
- Screenshot capture for debugging
- Configurable timeouts and retry logic
"""

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Telegram bot for 2FA notifications and code input.
    
    Uses python-telegram-bot library to:
    1. Send notification when 2FA is needed
    2. Wait for user to reply with the code
    3. Return the code to the scraper
    """
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._pending_code: Optional[str] = None
        self._code_event: Optional[asyncio.Event] = None
    
    async def request_2fa_code(self, bank_name: str, timeout: int = 300) -> Optional[str]:
        """
        Send notification and wait for 2FA code.
        
        Args:
            bank_name: Name of the bank requesting 2FA
            timeout: Seconds to wait for code (default 5 minutes)
            
        Returns:
            The 2FA code entered by user, or None if timeout
        """
        try:
            from telegram import Bot
            from telegram.ext import Application, MessageHandler, filters
            
            bot = Bot(token=self.bot_token)
            
            # Send notification
            message = (
                f"🔐 **{bank_name} Scraper**\n\n"
                f"2FA code required.\n"
                f"Reply with the code within {timeout // 60} minutes."
            )
            await bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="Markdown"
            )
            logger.info(f"Sent 2FA request to Telegram for {bank_name}")
            
            # Set up listener for reply
            self._code_event = asyncio.Event()
            self._pending_code = None
            
            # Create application for receiving messages
            app = Application.builder().token(self.bot_token).build()
            
            async def handle_message(update, context):
                if str(update.effective_chat.id) == str(self.chat_id):
                    code = update.message.text.strip()
                    # Validate it looks like a code (digits only, 4-8 chars)
                    if code.isdigit() and 4 <= len(code) <= 8:
                        self._pending_code = code
                        self._code_event.set()
                        await update.message.reply_text(f"✅ Code received: {code}")
                    else:
                        await update.message.reply_text(
                            "❌ Invalid code format. Please send digits only (4-8 characters)."
                        )
            
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            
            # Start polling in background
            await app.initialize()
            await app.start()
            await app.updater.start_polling()
            
            try:
                # Wait for code with timeout
                await asyncio.wait_for(self._code_event.wait(), timeout=timeout)
                return self._pending_code
            except asyncio.TimeoutError:
                await bot.send_message(
                    chat_id=self.chat_id,
                    text=f"⏰ Timeout waiting for {bank_name} 2FA code."
                )
                logger.warning(f"Timeout waiting for 2FA code for {bank_name}")
                return None
            finally:
                await app.updater.stop()
                await app.stop()
                await app.shutdown()
                
        except ImportError:
            logger.error("python-telegram-bot not installed. Run: pip install python-telegram-bot")
            return None
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return None
    
    async def send_notification(self, message: str):
        """Send a simple notification message."""
        try:
            from telegram import Bot
            bot = Bot(token=self.bot_token)
            await bot.send_message(chat_id=self.chat_id, text=message)
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")


class BaseScraper(ABC):
    """
    Abstract base class for bank scrapers.
    
    Provides:
    - Browser session management with Playwright
    - Session persistence (cookies/localStorage)
    - Telegram integration for 2FA
    - Screenshot capture for debugging
    - Configurable download directory
    """
    
    def __init__(
        self,
        state_dir: str = "./data/scraper_state",
        download_dir: str = "./incoming",
        headless: bool = True,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
    ):
        """
        Initialize the scraper.
        
        Args:
            state_dir: Directory to store browser state (cookies, localStorage)
            download_dir: Directory where CSVs will be downloaded
            headless: Run browser in headless mode (set False for debugging)
            telegram_bot_token: Telegram bot token for 2FA notifications
            telegram_chat_id: Telegram chat ID to send notifications to
        """
        self.state_dir = Path(state_dir)
        self.download_dir = Path(download_dir)
        self.headless = headless
        
        # Create directories
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        # Telegram notifier
        self.telegram: Optional[TelegramNotifier] = None
        if telegram_bot_token and telegram_chat_id:
            self.telegram = TelegramNotifier(telegram_bot_token, telegram_chat_id)
        
        # Browser instances (set during run)
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        
        # Track downloaded files
        self._downloaded_files: list[Path] = []
    
    @property
    @abstractmethod
    def bank_name(self) -> str:
        """Return the bank name (e.g., 'westpac', 'cba')."""
        pass
    
    @property
    def state_file(self) -> Path:
        """Path to the browser state file for this bank."""
        return self.state_dir / f"{self.bank_name}_state.json"
    
    @property
    def screenshot_dir(self) -> Path:
        """Directory for debug screenshots."""
        return self.state_dir / "screenshots"
    
    async def _init_browser(self):
        """Initialize Playwright browser with persistent context."""
        self._playwright = await async_playwright().start()
        
        # Browser launch options
        browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ]
        
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=browser_args,
        )
        
        # Create context with state if exists
        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "accept_downloads": True,
        }
        
        # Load existing state if available
        if self.state_file.exists():
            logger.info(f"Loading existing browser state from {self.state_file}")
            context_options["storage_state"] = str(self.state_file)
        
        self._context = await self._browser.new_context(**context_options)
        
        # Set download path
        self._context.set_default_timeout(30000)  # 30 second default timeout
        
        self._page = await self._context.new_page()
        
        # Handle downloads
        self._page.on("download", self._handle_download)
    
    async def _handle_download(self, download):
        """Handle file downloads - save to download_dir."""
        # Get suggested filename
        suggested = download.suggested_filename
        
        # Create bank-specific subdirectory
        bank_download_dir = self.download_dir / f"{self.bank_name}-scraper"
        bank_download_dir.mkdir(parents=True, exist_ok=True)
        
        # Add timestamp to avoid overwrites
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{Path(suggested).stem}_{timestamp}{Path(suggested).suffix}"
        save_path = bank_download_dir / filename
        
        await download.save_as(str(save_path))
        logger.info(f"Downloaded: {save_path}")
        self._downloaded_files.append(save_path)
    
    async def _save_state(self):
        """Save browser state (cookies, localStorage) for session persistence."""
        if self._context:
            state = await self._context.storage_state()
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
            logger.info(f"Saved browser state to {self.state_file}")
    
    async def _take_screenshot(self, name: str) -> Optional[Path]:
        """Take a screenshot for debugging."""
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.screenshot_dir / f"{self.bank_name}_{name}_{timestamp}.png"
        if self._page:
            await self._page.screenshot(path=str(path))
            logger.debug(f"Screenshot saved: {path}")
            return path
        return None
    
    async def _close_browser(self):
        """Close browser and save state."""
        await self._save_state()
        
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    async def request_2fa_code(self, timeout: int = 300) -> Optional[str]:
        """
        Request 2FA code via Telegram.
        
        If Telegram is not configured, falls back to console input.
        """
        if self.telegram:
            return await self.telegram.request_2fa_code(self.bank_name, timeout)
        else:
            # Fallback to console input
            logger.info(f"2FA required for {self.bank_name}. Enter code in console.")
            print(f"\n🔐 {self.bank_name} requires 2FA code.")
            print(f"Enter the code (you have {timeout} seconds): ", end="", flush=True)
            
            # Use asyncio to handle timeout
            loop = asyncio.get_event_loop()
            try:
                code = await asyncio.wait_for(
                    loop.run_in_executor(None, input),
                    timeout=timeout
                )
                return code.strip()
            except asyncio.TimeoutError:
                print("\n⏰ Timeout waiting for code.")
                return None
    
    async def notify(self, message: str):
        """Send notification via Telegram (or log if not configured)."""
        if self.telegram:
            await self.telegram.send_notification(message)
        else:
            logger.info(f"Notification: {message}")
    
    async def is_logged_in(self) -> bool:
        """
        Check if already logged in (session still valid).
        
        Override in subclass to implement bank-specific check.
        Default implementation returns False.
        """
        return False
    
    @abstractmethod
    async def login(self) -> bool:
        """
        Perform login to the bank website.
        
        Should handle:
        - Navigating to login page
        - Entering credentials
        - Handling 2FA if required
        - Detecting successful login
        
        Returns:
            True if login successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def download_transactions(self, accounts: Optional[list] = None) -> list[Path]:
        """
        Download transaction CSVs for specified accounts.
        
        Args:
            accounts: List of account identifiers to download.
                     If None, download all available accounts.
        
        Returns:
            List of paths to downloaded CSV files
        """
        pass
    
    async def run(self, accounts: Optional[list] = None) -> list[Path]:
        """
        Main entry point - login and download transactions.
        
        Args:
            accounts: Optional list of account IDs to download
            
        Returns:
            List of paths to downloaded CSV files
        """
        self._downloaded_files = []
        
        try:
            await self._init_browser()
            
            # Check if already logged in
            if await self.is_logged_in():
                logger.info(f"Already logged in to {self.bank_name}")
            else:
                # Attempt login
                if await self.login():
                    logger.info(f"Successfully logged in to {self.bank_name}")
                    await self.notify(f"✅ Logged in to {self.bank_name}")
                else:
                    logger.error(f"Failed to login to {self.bank_name}")
                    await self.notify(f"❌ Failed to login to {self.bank_name}")
                    await self._take_screenshot("login_failed")
                    return []
            
            # Download transactions
            downloaded_files = await self.download_transactions(accounts)
            
            if downloaded_files:
                await self.notify(
                    f"✅ Downloaded {len(downloaded_files)} file(s) from {self.bank_name}"
                )
            else:
                await self.notify(f"⚠️ No files downloaded from {self.bank_name}")
                
        except Exception as e:
            logger.exception(f"Error during {self.bank_name} scrape: {e}")
            await self.notify(f"❌ Error scraping {self.bank_name}: {str(e)}")
            await self._take_screenshot("error")
            
        finally:
            await self._close_browser()
        
        return self._downloaded_files
