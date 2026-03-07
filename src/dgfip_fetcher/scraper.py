import asyncio
import logging
import re
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from .auth import AUTH_FILE, CONFIG_DIR
from .utils import generate_filename

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

async def login_via_playwright(spi, pwd, headless=True):
    """Handles login via Playwright."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()

            logger.info(f"Opening login page (mode: {'headless' if headless else 'visible'})...")
            await page.goto("https://cfspart.impots.gouv.fr/espace-particulier/")
            
            await page.wait_for_selector("#spi_tmp", timeout=10000)
            await page.fill("#spi_tmp", spi)
            await page.click("button[type='submit']")
            
            await page.wait_for_selector("#pwd_tmp", timeout=10000)
            await page.fill("#pwd_tmp", pwd)
            await page.click("button[type='submit']")
            
            try:
                success_selector = "a:has-text('Déconnexion')"
                otp_selector = "#code_SMS_tmp, #code_mail_tmp, input[name='code']"
                await asyncio.wait([
                    asyncio.create_task(page.wait_for_selector(success_selector, timeout=10000)),
                    asyncio.create_task(page.wait_for_selector(otp_selector, timeout=10000))
                ], return_when=asyncio.FIRST_COMPLETED)
            except: pass

            otp_input = await page.query_selector("#code_SMS_tmp, #code_mail_tmp, input[name='code']")
            if otp_input:
                logger.info("\n" + "!"*40)
                logger.info("ACTION REQUIRED: 2FA code detected.")
                otp_code = input("Please enter the received code: ").strip()
                logger.info("!"*40 + "\n")
                await otp_input.fill(otp_code)
                await page.keyboard.press("Enter")
            
            await page.wait_for_selector("a:has-text('Déconnexion')", timeout=30000)
            logger.info("Login successful!")
            
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(AUTH_FILE))
            cookies = {c["name"]: c["value"] for c in (await context.cookies())}
            await browser.close()
            return cookies
    except Exception as e:
        logger.error(f"Login failed: {e}")
        if headless:
            logger.info("Retrying in visible mode...")
            return await login_via_playwright(spi, pwd, headless=False)
        return None

async def process_year(client, year, output_dir):
    """Downloads documents for a given year."""
    logger.info(f"\n--- Year {year} ---")
    url = f"https://cfspart.impots.gouv.fr/enp/documents.do?n={year}"
    try:
        resp = await client.get(url)
        soup = BeautifulSoup(resp.text, "html.parser")
        frame_urls = [f.get("src") for f in soup.find_all("iframe") if f.get("src") and "documents.do" in f.get("src")]
        urls = [url] if not frame_urls else [f"https://cfspart.impots.gouv.fr{s}" if s.startswith("/") else s for s in frame_urls]
        
        for scan_url in urls:
            if scan_url != url:
                resp = await client.get(scan_url)
                soup = BeautifulSoup(resp.text, "html.parser")
            
            forms = soup.find_all("form", action=re.compile(r"Affichage_Document_PDF"))
            if not forms: continue
            
            logger.info(f"  {len(forms)} documents detected.")
            for i, form in enumerate(forms):
                try:
                    id_ensua = form.find("input", {"name": "idEnsua"}).get("value")
                    btn = form.find("button") or form.find("input", {"type": "submit"})
                    title = re.sub(r"« Visualiser PDF »\s*", "", btn.get("title") or btn.get_text()).strip()
                    dest = generate_filename(title, year, output_dir)
                    logger.info(f"  [{i+1}/{len(forms)}] {Path(dest).name}...")
                    
                    pdf_resp = await client.get(f"https://cfspart.impots.gouv.fr/enp/Affichage_Document_PDF?idEnsua={id_ensua}")
                    if pdf_resp.status_code == 200 and b"%PDF" in pdf_resp.content[:100]:
                        with open(dest, "wb") as f: f.write(pdf_resp.content)
                        logger.info(f"    [OK] ({len(pdf_resp.content)//1024} KB)")
                except Exception as e: logger.error(f"    [!] Document error: {e}")
    except Exception as e: logger.error(f"Year {year} error: {e}")
