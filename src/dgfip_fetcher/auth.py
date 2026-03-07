import json
import logging
import getpass
from pathlib import Path
from platformdirs import user_config_dir
import keyring

logger = logging.getLogger(__name__)

APP_NAME = "dgfip-fetcher"
CONFIG_DIR = Path(user_config_dir(APP_NAME))
CONFIG_FILE = CONFIG_DIR / "config.json"
AUTH_FILE = CONFIG_DIR / "auth_state.json"

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
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump({"spi": spi}, f)

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

async def get_cookies_from_auth_file():
    if not AUTH_FILE.exists():
        return None
    try:
        with open(AUTH_FILE, "r") as f:
            auth_data = json.load(f)
        return {c["name"]: c["value"] for c in auth_data.get("cookies", [])}
    except Exception as e:
        logger.error(f"Error reading cookies: {e}")
        return None
