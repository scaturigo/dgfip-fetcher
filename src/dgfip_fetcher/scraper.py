import asyncio
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from .auth import CONFIG_DIR, write_private
from .utils import clean_title, document_year, document_filename, document_folder

logger = logging.getLogger(__name__)

BASE_URL = "https://cfspart.impots.gouv.fr"
HOME_URL = f"{BASE_URL}/espace-particulier/"
DOCUMENTS_URL = f"{BASE_URL}/enp/documents.do?n=0"
PDF_URL = BASE_URL + "/enp/Affichage_Document_PDF?idEnsua={id}"
# Unauthenticated requests are redirected to this host (login page)
LOGIN_HOST = "cfspart-idp.impots.gouv.fr"

# Fallback when no user agent was saved with the session
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"

# The logout control is a "Se déconnecter" button since 2026 (it used to be a "Déconnexion" link)
LOGGED_IN_SELECTOR = "button.fr-btn--logout, button:has-text('Se déconnecter'), a:has-text('Déconnexion')"
OTP_SELECTOR = "#otp_tmp, #code_SMS_tmp, #code_mail_tmp, input[name='code']"


class SessionExpired(Exception):
    """Raised when the portal redirects to the login page in the middle of a run."""


@dataclass
class Document:
    id: str
    title: str
    year: int | None


def user_agent_for(chrome_version):
    """User agent of a regular (non-headless) Chrome matching Playwright's Chromium version."""
    platform = {
        "darwin": "Macintosh; Intel Mac OS X 10_15_7",
        "win32": "Windows NT 10.0; Win64; x64",
    }.get(sys.platform, "X11; Linux x86_64")
    major = chrome_version.split(".")[0]
    return f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"


def is_login_page(resp):
    return resp.url.host == LOGIN_HOST


async def session_is_valid(client):
    """Checks whether the client's cookies give access to the personal space."""
    try:
        resp = await client.get(HOME_URL)
    except httpx.HTTPError:
        return False
    return resp.status_code == 200 and not is_login_page(resp)


async def dump_page(page, name):
    """Saves a screenshot and the HTML of the current page to help diagnose failures."""
    try:
        png = CONFIG_DIR / f"{name}.png"
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(png), full_page=True)
        os.chmod(png, 0o600)
        write_private(CONFIG_DIR / f"{name}.html", await page.content())
        logger.info(f"Page saved for debugging: {CONFIG_DIR / name}.png / .html (URL: {page.url})")
    except Exception as e:
        logger.error(f"Could not save page for debugging: {e}")


async def login_via_playwright(spi, pwd, headless=True):
    """Logs in with Playwright. Returns (cookies, user_agent), or None on failure."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            user_agent = user_agent_for(browser.version)
            context = await browser.new_context(user_agent=user_agent)
            page = await context.new_page()
            try:
                logger.info(f"Opening login page (mode: {'headless' if headless else 'visible'})...")
                await page.goto(HOME_URL)

                await page.fill("#spi_tmp", spi)
                await page.click("#btnAction")
                await page.fill("#pwd_tmp", pwd)
                await page.click("#btnAction")

                # Either we are logged in directly, or a 2FA code is requested
                await page.wait_for_selector(f"{LOGGED_IN_SELECTOR}, {OTP_SELECTOR}", timeout=30000)
                otp_input = page.locator(OTP_SELECTOR).filter(visible=True)
                if await otp_input.count():
                    logger.info("\n" + "!"*40)
                    logger.info("ACTION REQUIRED: a 2FA code has been sent to you (email or SMS).")
                    otp_code = input("Please enter the received code: ").strip()
                    logger.info("!"*40 + "\n")
                    # An empty answer lets the user type the code in the visible browser (--debug)
                    if otp_code:
                        await otp_input.first.fill(otp_code)
                        submit = page.locator("#btnAction").filter(visible=True)
                        if await submit.count():
                            await submit.first.click()
                        else:
                            await page.keyboard.press("Enter")

                await page.wait_for_selector(LOGGED_IN_SELECTOR, timeout=60000)
            except Exception as e:
                logger.error(f"Login failed: {e}")
                await dump_page(page, "login_failure")
                return None

            logger.info("Login successful!")
            cookies = httpx.Cookies()
            for c in await context.cookies():
                cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
            return cookies, user_agent
        finally:
            await browser.close()


def _is_document_element(tag):
    if tag.name == "a":
        return "Affichage_Document_PDF?idEnsua=" in (tag.get("href") or "")
    return tag.name == "form" and "Affichage_Document_PDF" in (tag.get("action") or "")


def parse_documents(html):
    """Extracts the documents listed in the documents page, in page order.

    Main documents (tax notices, invoices, returns) are links; the associated
    documents (annexes, acknowledgements) are forms.
    """
    soup = BeautifulSoup(html, "html.parser")
    docs = []
    for element in soup.find_all(_is_document_element):
        if element.name == "a":
            id_ensua = re.search(r"idEnsua=([^&]+)", element["href"]).group(1)
            title = clean_title(element.get("aria-label") or element.get_text(" "))
        else:
            id_input = element.find("input", {"name": "idEnsua"})
            btn = element.find("button") or element.find("input", {"type": "submit"})
            if not id_input or not id_input.get("value") or not btn:
                continue
            id_ensua = id_input["value"]
            title = clean_title(btn.get("title") or btn.get_text())
        # Documents are grouped in one collapsible section per year (<div id="2026">)
        section = element.find_parent(id=re.compile(r"^(?:19|20)\d{2}$"))
        year = int(section["id"]) if section else document_year(title)
        docs.append(Document(id_ensua, title, year))
    return docs


async def list_documents(client, years):
    """Lists the documents of the given years, without duplicates.

    The page lists all the years at once (its `n` parameter is ignored), and
    each document twice (desktop and mobile layouts).
    """
    resp = await client.get(DOCUMENTS_URL)
    if is_login_page(resp):
        raise SessionExpired()
    docs = {}
    for doc in parse_documents(resp.text):
        docs.setdefault(doc.id, doc)
    return [doc for doc in docs.values() if doc.year is None or doc.year in years]


async def get_with_retry(client, url, attempts=3, delay=2):
    """GET that retries when the server drops the connection (it happens on long runs)."""
    for attempt in range(1, attempts + 1):
        try:
            return await client.get(url)
        except httpx.TransportError:
            if attempt == attempts:
                raise
            await asyncio.sleep(delay)


async def download_documents(client, docs, output_dir, flat=False):
    """Downloads the documents not already present in output_dir. Returns the number downloaded.

    Documents are sorted in year folders with sub-folders by category, unless
    `flat` is set. A document is considered present wherever it is in
    output_dir, so files moved by hand are not downloaded again.
    """
    output_dir = Path(output_dir)
    existing = {p.name for p in output_dir.rglob("*.pdf")}
    downloaded = 0
    for i, doc in enumerate(docs, 1):
        name = document_filename(doc.title, doc.year, doc.id)
        folder = output_dir if flat else output_dir / document_folder(doc.title, doc.year)
        dest = folder / name

        if name in existing:
            logger.info(f"  [{i}/{len(docs)}] {name} (already downloaded)")
            continue

        logger.info(f"  [{i}/{len(docs)}] {dest.relative_to(output_dir)}...")
        try:
            resp = await get_with_retry(client, PDF_URL.format(id=doc.id))
        except httpx.HTTPError as e:
            logger.error(f"    [!] Download error: {e}")
            continue
        if is_login_page(resp):
            raise SessionExpired()
        if resp.status_code == 200 and resp.content.startswith(b"%PDF"):
            # Written under a temporary name so an interrupted download is not taken as complete
            folder.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".pdf.part")
            tmp.write_bytes(resp.content)
            tmp.replace(dest)
            downloaded += 1
            logger.info(f"    [OK] ({len(resp.content)//1024} KB)")
        else:
            logger.warning(f"    [!] Not a PDF (HTTP {resp.status_code}, {resp.headers.get('content-type')})")
    return downloaded
