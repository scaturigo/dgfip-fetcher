import json
import pytest
from pathlib import Path
from dgfip_fetcher import auth

def test_load_config_error(mocker, tmp_path):
    mocker.patch("dgfip_fetcher.auth.CONFIG_FILE", tmp_path / "corrupt.json")
    with open(tmp_path / "corrupt.json", "w") as f:
        f.write("{invalid json")
    assert auth.load_config() == {}

def test_load_save_config(tmp_path, mocker):
    mocker.patch("dgfip_fetcher.auth.CONFIG_DIR", tmp_path)
    mocker.patch("dgfip_fetcher.auth.CONFIG_FILE", tmp_path / "config.json")
    
    spi = "1234567890123"
    auth.save_config(spi)
    loaded = auth.load_config()
    assert loaded["spi"] == spi

def test_get_credentials_interactive(mocker, tmp_path):
    mocker.patch("dgfip_fetcher.auth.CONFIG_FILE", tmp_path / "config.json")
    mocker.patch("dgfip_fetcher.auth.CONFIG_DIR", tmp_path)
    
    # Simulate: first 12 digits (wrong), then 13 digits (correct)
    mocker.patch("builtins.input", side_effect=["123456789012", "9999999999999"])
    mocker.patch("getpass.getpass", return_value="mypassword")
    mocker.patch("keyring.get_password", return_value=None)
    mocker.patch("keyring.set_password")

    spi, pwd = auth.get_credentials()
    assert spi == "9999999999999"
    assert pwd == "mypassword"
    assert auth.load_config()["spi"] == "9999999999999"

def test_get_credentials_cached(mocker, tmp_path):
    mocker.patch("dgfip_fetcher.auth.CONFIG_FILE", tmp_path / "config.json")
    mocker.patch("dgfip_fetcher.auth.CONFIG_DIR", tmp_path)
    
    spi = "1234567890123"
    password = "secret_password"
    with open(tmp_path / "config.json", "w") as f:
        json.dump({"spi": spi}, f)
        
    mocker.patch("keyring.get_password", return_value=password)
    res_spi, res_pwd = auth.get_credentials()
    assert res_spi == spi
    assert res_pwd == password

@pytest.mark.asyncio
async def test_get_cookies_from_auth_file_ok(tmp_path, mocker):
    auth_file = tmp_path / "auth.json"
    mocker.patch("dgfip_fetcher.auth.AUTH_FILE", auth_file)
    data = {"cookies": [{"name": "test", "value": "val"}]}
    with open(auth_file, "w") as f:
        json.dump(data, f)
    
    cookies = await auth.get_cookies_from_auth_file()
    assert cookies == {"test": "val"}

@pytest.mark.asyncio
async def test_get_cookies_from_auth_file_missing(tmp_path, mocker):
    mocker.patch("dgfip_fetcher.auth.AUTH_FILE", tmp_path / "none.json")
    assert await auth.get_cookies_from_auth_file() is None

@pytest.mark.asyncio
async def test_get_cookies_from_auth_file_error(tmp_path, mocker):
    auth_file = tmp_path / "error.json"
    mocker.patch("dgfip_fetcher.auth.AUTH_FILE", auth_file)
    with open(auth_file, "w") as f:
        f.write("bad")
    assert await auth.get_cookies_from_auth_file() is None
