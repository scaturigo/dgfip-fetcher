import json
import logging
import getpass
import os
from pathlib import Path
from platformdirs import user_config_dir
import httpx
import keyring

logger = logging.getLogger(__name__)

APP_NAME = "dgfip-fetcher"
CONFIG_DIR = Path(user_config_dir(APP_NAME))
CONFIG_FILE = CONFIG_DIR / "config.json"
AUTH_FILE = CONFIG_DIR / "auth_state.json"

def write_private(path, text):
    """Writes a file readable only by the current user (it may contain session cookies)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    # The file may predate this function and have wider permissions
    os.chmod(path, 0o600)

def load_config():
    """Loads the French tax ID (SPI) from the JSON config file."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading config: {e}")
    return {}

def save_config(spi):
    """Saves the French tax ID (SPI) to the JSON config file."""
    write_private(CONFIG_FILE, json.dumps({"spi": spi}))

def get_credentials():
    """Retrieves credentials via keyring and JSON config."""
    config = load_config()
    spi = config.get("spi")

    if not spi:
        print("\n--- Initial Configuration ---")
        while True:
            spi = input("Please enter your French tax ID (13 digits - SPI): ").strip()
            if spi.isdigit() and len(spi) == 13:
                save_config(spi)
                logger.info(f"French tax ID (SPI) saved locally.")
                break
            else:
                logger.warning("Error: The French tax ID (SPI) must be exactly 13 digits long.")

    # Securely retrieve the password from the system keyring
    pwd = keyring.get_password(APP_NAME, spi)

    if not pwd:
        print(f"Password for {spi} not found in the system vault.")
        pwd = getpass.getpass("Please enter your French tax portal (impots.gouv.fr) password: ").strip()
        keyring.set_password(APP_NAME, spi, pwd)
        logger.info("Password securely saved in the system vault.")

    return spi, pwd

def load_session():
    """Loads the saved session. Returns (cookies, user_agent), or None.

    Cookies keep their domain so they are only sent to impots.gouv.fr.
    """
    if not AUTH_FILE.exists():
        return None
    try:
        with open(AUTH_FILE, "r") as f:
            data = json.load(f)
        cookies = httpx.Cookies()
        for c in data.get("cookies", []):
            cookies.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
        return cookies, data.get("user_agent")
    except Exception as e:
        logger.error(f"Error reading session: {e}")
        return None

def save_session(cookies, user_agent):
    """Saves the session cookies (they are renewed by the portal during a run)."""
    data = {
        "user_agent": user_agent,
        "cookies": [{"name": c.name, "value": c.value, "domain": c.domain, "path": c.path} for c in cookies.jar],
    }
    write_private(AUTH_FILE, json.dumps(data))
