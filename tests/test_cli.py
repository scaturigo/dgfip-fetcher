import pytest
import httpx
import respx
from dgfip_fetcher.cli import main, main_async

@pytest.mark.asyncio
async def test_cli_reset(mocker, tmp_path):
    mocker.patch("dgfip_fetcher.auth.CONFIG_FILE", tmp_path / "config.json")
    mocker.patch("dgfip_fetcher.auth.AUTH_FILE", tmp_path / "auth.json")
    mocker.patch("dgfip_fetcher.auth.load_config", return_value={"spi": "123"})
    mocker.patch("keyring.delete_password")
    
    # Mock arguments
    mocker.patch("argparse.ArgumentParser.parse_args", return_value=mocker.Mock(reset=True))
    
    await main_async()
    assert not (tmp_path / "config.json").exists()

@pytest.mark.asyncio
async def test_cli_main_flow(mocker, tmp_path):
    mocker.patch("dgfip_fetcher.cli.get_credentials", return_value=("123", "pwd"))
    mocker.patch("dgfip_fetcher.cli.get_cookies_from_auth_file", return_value={"test": "val"})
    mocker.patch("argparse.ArgumentParser.parse_args", return_value=mocker.Mock(
        reset=False, years=1, output=str(tmp_path), debug=False
    ))
    mocker.patch("dgfip_fetcher.cli.process_year", return_value=mocker.AsyncMock())
    
    async with respx.mock() as respx_mock:
        respx_mock.get("https://cfspart.impots.gouv.fr/espace-particulier/").mock(
            return_value=httpx.Response(200, text="Déconnexion")
        )
        await main_async()

@pytest.mark.asyncio
async def test_cli_login_fails(mocker, tmp_path):
    mocker.patch("dgfip_fetcher.cli.get_credentials", return_value=("123", "pwd"))
    mocker.patch("dgfip_fetcher.cli.get_cookies_from_auth_file", return_value=None)
    mocker.patch("dgfip_fetcher.cli.login_via_playwright", return_value=None) # Fails login
    
    mocker.patch("argparse.ArgumentParser.parse_args", return_value=mocker.Mock(
        reset=False, years=0, output=str(tmp_path), debug=True
    ))
    
    async with respx.mock() as respx_mock:
        respx_mock.get("https://cfspart.impots.gouv.fr/espace-particulier/").mock(
            return_value=httpx.Response(200, text="Connexion")
        )
        await main_async()

def test_main_entrypoint(mocker):
    mocker.patch("asyncio.run")
    main()

def test_main_keyboard_interrupt(mocker):
    mocker.patch("asyncio.run", side_effect=KeyboardInterrupt())
    main()

def test_main_error_handling_chromium_missing(mocker):
    mocker.patch("asyncio.run", side_effect=Exception("playwright install chromium"))
    main()

def test_main_error_unexpected(mocker):
    mocker.patch("asyncio.run", side_effect=Exception("Boom"))
    main()
