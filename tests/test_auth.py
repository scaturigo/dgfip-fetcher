import json
import stat
import httpx
import pytest
from dgfip_fetcher import auth

@pytest.fixture
def config_dir(tmp_path, mocker):
    mocker.patch("dgfip_fetcher.auth.CONFIG_DIR", tmp_path)
    mocker.patch("dgfip_fetcher.auth.CONFIG_FILE", tmp_path / "config.json")
    mocker.patch("dgfip_fetcher.auth.AUTH_FILE", tmp_path / "auth_state.json")
    return tmp_path

def test_load_config_error(config_dir):
    (config_dir / "config.json").write_text("{invalid json")
    assert auth.load_config() == {}

def test_load_save_config(config_dir):
    spi = "1234567890123"
    auth.save_config(spi)
    assert auth.load_config()["spi"] == spi

def test_write_private_restricts_permissions(tmp_path):
    path = tmp_path / "secret.json"
    path.write_text("old")
    path.chmod(0o644)
    auth.write_private(path, "new")
    assert path.read_text() == "new"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

def test_get_credentials_interactive(mocker, config_dir):
    # Simulate: first 12 digits (wrong), then 13 digits (correct)
    mocker.patch("builtins.input", side_effect=["123456789012", "9999999999999"])
    mocker.patch("getpass.getpass", return_value="mypassword")
    mocker.patch("keyring.get_password", return_value=None)
    set_password = mocker.patch("keyring.set_password")

    spi, pwd = auth.get_credentials()
    assert spi == "9999999999999"
    assert pwd == "mypassword"
    assert auth.load_config()["spi"] == "9999999999999"
    set_password.assert_called_once_with(auth.APP_NAME, spi, "mypassword")

def test_get_credentials_cached(mocker, config_dir):
    spi = "1234567890123"
    (config_dir / "config.json").write_text(json.dumps({"spi": spi}))
    mocker.patch("keyring.get_password", return_value="secret_password")
    assert auth.get_credentials() == (spi, "secret_password")

def test_save_load_session_keeps_domains(config_dir):
    cookies = httpx.Cookies()
    cookies.set("SESSION", "abc", domain=".impots.gouv.fr", path="/")
    auth.save_session(cookies, "UA/1.0")
    assert stat.S_IMODE((config_dir / "auth_state.json").stat().st_mode) == 0o600

    loaded, user_agent = auth.load_session()
    assert user_agent == "UA/1.0"
    assert loaded.get("SESSION", domain=".impots.gouv.fr") == "abc"

    # The cookie must not be sent to other sites
    for url, expected in [("https://cfspart.impots.gouv.fr/", "SESSION=abc"), ("https://example.com/", None)]:
        request = httpx.Request("GET", url)
        loaded.set_cookie_header(request)
        assert request.headers.get("cookie") == expected

def test_load_session_legacy_playwright_file(config_dir):
    # Files written by previous versions (Playwright storage_state) have no user agent
    data = {"cookies": [{"name": "test", "value": "val", "domain": "cfspart.impots.gouv.fr", "path": "/"}], "origins": []}
    (config_dir / "auth_state.json").write_text(json.dumps(data))
    cookies, user_agent = auth.load_session()
    assert cookies.get("test") == "val"
    assert user_agent is None

def test_load_session_missing(config_dir):
    assert auth.load_session() is None

def test_load_session_error(config_dir):
    (config_dir / "auth_state.json").write_text("bad")
    assert auth.load_session() is None
