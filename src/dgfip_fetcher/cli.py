import asyncio
import logging
import argparse
import sys
import httpx
import argcomplete
from pathlib import Path
from datetime import datetime
from .auth import get_credentials, load_session, save_session
from .scraper import (
    login_via_playwright, session_is_valid, list_documents, download_documents,
    SessionExpired, USER_AGENT,
)

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def reset():
    """Deletes the saved credentials, session and debug files."""
    import keyring
    from .auth import CONFIG_DIR, CONFIG_FILE, AUTH_FILE, APP_NAME, load_config
    spi = load_config().get("spi")
    if spi:
        try:
            keyring.delete_password(APP_NAME, spi)
        except keyring.errors.PasswordDeleteError:
            pass
    for path in [CONFIG_FILE, AUTH_FILE, CONFIG_DIR / "login_failure.png", CONFIG_DIR / "login_failure.html"]:
        path.unlink(missing_ok=True)
    logger.info("Credentials and session cleared. Please run the script again.")

async def main_async():
    """Runs the CLI. Returns the process exit code."""
    parser = argparse.ArgumentParser(description="dgfip-fetcher: Automated download of tax documents from impots.gouv.fr")
    parser.add_argument("--years", type=int, default=10, help="Number of previous years to scan (default: 10)")
    parser.add_argument("--output", "-o", default=".", help="Destination folder (default: current directory)")
    parser.add_argument("--flat", action="store_true", help="Save all files directly in the destination folder (default: one folder per year, sub-folders by category)")
    parser.add_argument("--debug", action="store_true", help="Enable visible browser mode (useful for debugging)")
    parser.add_argument("--reset", action="store_true", help="Reset saved credentials and session")

    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    if args.reset:
        reset()
        return 0

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    spi, pwd = get_credentials()
    cookies, user_agent = load_session() or (None, None)
    user_agent = user_agent or USER_AGENT

    async with httpx.AsyncClient(cookies=cookies, headers={"User-Agent": user_agent}, follow_redirects=True, timeout=30.0) as client:
        if await session_is_valid(client):
            logger.info("Active session restored.")
        else:
            logger.info("Session not found or expired. Logging in...")
            result = await login_via_playwright(spi, pwd, headless=not args.debug)
            if not result:
                logger.error("Failed to login. Check your credentials, or retry with --debug to see the browser.")
                return 1
            client.cookies, user_agent = result
            client.headers["User-Agent"] = user_agent
            save_session(client.cookies, user_agent)

        current_year = datetime.now().year
        years = range(current_year, current_year - args.years - 1, -1)
        try:
            docs = await list_documents(client, years)
            logger.info(f"\n{len(docs)} documents found from {years[-1]} to {years[0]}.")
            downloaded = await download_documents(client, docs, output_dir, flat=args.flat)
        except SessionExpired:
            logger.error("The session expired during the run. Please run the command again.")
            return 1
        finally:
            save_session(client.cookies, user_agent)

    logger.info(f"\nDone! {downloaded} new document(s) in: '{output_dir}'.")
    return 0

def main():
    """Synchronous entry point for the script."""
    try:
        sys.exit(asyncio.run(main_async()))
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user.")
        sys.exit(130)
    except Exception as e:
        if "Executable doesn't exist" in str(e) or "playwright install" in str(e).lower():
            logger.error("\n[Error] Chromium browser not found.")
            logger.info("Please install it by running: python -m playwright install chromium")
        else:
            logger.error(f"An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
