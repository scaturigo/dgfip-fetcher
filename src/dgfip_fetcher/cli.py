import asyncio
import logging
import argparse
import httpx
import argcomplete
from pathlib import Path
from datetime import datetime
from .auth import get_credentials, get_cookies_from_auth_file
from .scraper import login_via_playwright, process_year, USER_AGENT

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def main_async():
    parser = argparse.ArgumentParser(description="dgfip-fetcher: Automated download of tax documents from impots.gouv.fr")
    parser.add_argument("--years", type=int, default=10, help="Number of previous years to scan (default: 10)")
    parser.add_argument("--output", "-o", default=".", help="Destination folder (default: current directory)")
    parser.add_argument("--debug", action="store_true", help="Enable visible browser mode (useful for debugging)")
    parser.add_argument("--reset", action="store_true", help="Reset saved credentials and session")
    
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    if args.reset:
        from .auth import CONFIG_FILE, AUTH_FILE, APP_NAME, load_config
        import keyring
        config = load_config()
        spi = config.get("spi")
        if spi:
            try:
                keyring.delete_password(APP_NAME, spi)
            except: pass
        if CONFIG_FILE.exists(): CONFIG_FILE.unlink()
        if AUTH_FILE.exists(): AUTH_FILE.unlink()
        logger.info("Credentials and session cleared. Please run the script again.")
        return

    if args.output != ".":
        Path(args.output).mkdir(parents=True, exist_ok=True)

    spi, pwd = get_credentials()
    cookies = await get_cookies_from_auth_file()
    
    headers = {"User-Agent": USER_AGENT}
    
    async with httpx.AsyncClient(cookies=cookies, headers=headers, follow_redirects=True, timeout=30.0) as client:
        try:
            resp = await client.get("https://cfspart.impots.gouv.fr/espace-particulier/")
            session_valid = "Déconnexion" in resp.text
        except: session_valid = False
            
        if not session_valid:
            logger.info("Session not found or expired. Logging in...")
            new_cookies = await login_via_playwright(spi, pwd, headless=not args.debug)
            if not new_cookies: 
                logger.error("Failed to login. Please check your credentials.")
                return
            client.cookies.update(new_cookies)
        else:
            logger.info("Active session restored.")

        current_year = datetime.now().year
        for year in range(current_year, current_year - args.years - 1, -1):
            await process_year(client, year, args.output)

    logger.info(f"\nDone! Your documents are in: '{args.output}'.")

def main():
    """Synchronous entry point for the script."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user.")
    except Exception as e:
        if "Executable doesn't exist" in str(e) or "playwright install" in str(e).lower():
            logger.error("\n[Error] Chromium browser not found.")
            logger.info("Please install it by running: python -m playwright install chromium")
        else:
            logger.error(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
