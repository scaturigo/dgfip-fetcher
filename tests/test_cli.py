import httpx
import pytest
from dgfip_fetcher import cli
from dgfip_fetcher.cli import main, main_async
from dgfip_fetcher.scraper import Document, SessionExpired

def args(mocker, **overrides):
    values = dict(reset=False, years=1, output=".", debug=False, flat=False)
    values.update(overrides)
    return mocker.patch("argparse.ArgumentParser.parse_args", return_value=mocker.Mock(**values))

@pytest.fixture
def flow(mocker):
    """Mocks everything around the HTTP/browser layer."""
    mocker.patch("dgfip_fetcher.cli.get_credentials", return_value=("123", "pwd"))
    mocker.patch("dgfip_fetcher.cli.load_session", return_value=None)
    mocker.patch("dgfip_fetcher.cli.save_session")
    mocker.patch("dgfip_fetcher.cli.session_is_valid", return_value=True)
    mocker.patch("dgfip_fetcher.cli.login_via_playwright", return_value=(httpx.Cookies({"S": "v"}), "UA/2"))
    mocker.patch("dgfip_fetcher.cli.list_documents", return_value=[Document("ID1", "Avis", 2025)])
    mocker.patch("dgfip_fetcher.cli.download_documents", return_value=1)
    return cli

@pytest.mark.asyncio
async def test_cli_reset(mocker, tmp_path):
    for name in ["config.json", "auth_state.json", "login_failure.png"]:
        (tmp_path / name).write_text("x")
    mocker.patch("dgfip_fetcher.auth.CONFIG_DIR", tmp_path)
    mocker.patch("dgfip_fetcher.auth.CONFIG_FILE", tmp_path / "config.json")
    mocker.patch("dgfip_fetcher.auth.AUTH_FILE", tmp_path / "auth_state.json")
    mocker.patch("dgfip_fetcher.auth.load_config", return_value={"spi": "123"})
    delete_password = mocker.patch("keyring.delete_password")
    args(mocker, reset=True)

    assert await main_async() == 0
    delete_password.assert_called_once()
    assert list(tmp_path.iterdir()) == []

@pytest.mark.asyncio
async def test_cli_session_restored(flow, mocker, tmp_path):
    args(mocker, output=str(tmp_path / "out"))
    assert await main_async() == 0
    flow.login_via_playwright.assert_not_called()
    assert (tmp_path / "out").is_dir()
    assert len(flow.list_documents.call_args.args[1]) == 2  # current year + 1 previous year
    assert flow.download_documents.call_args.kwargs == {"flat": False}
    flow.save_session.assert_called_once()

@pytest.mark.asyncio
async def test_cli_login_then_download(flow, mocker, tmp_path):
    flow.session_is_valid.return_value = False
    args(mocker, output=str(tmp_path))
    assert await main_async() == 0
    flow.login_via_playwright.assert_awaited_once_with("123", "pwd", headless=True)
    # Saved right after login, then again at the end of the run
    assert flow.save_session.call_count == 2
    assert flow.save_session.call_args.args[1] == "UA/2"

@pytest.mark.asyncio
async def test_cli_login_fails(flow, mocker, tmp_path):
    flow.session_is_valid.return_value = False
    flow.login_via_playwright.return_value = None
    args(mocker, output=str(tmp_path), debug=True)
    assert await main_async() == 1
    flow.login_via_playwright.assert_awaited_once_with("123", "pwd", headless=False)
    flow.list_documents.assert_not_called()

@pytest.mark.asyncio
async def test_cli_session_expired_during_run(flow, mocker, tmp_path):
    flow.download_documents.side_effect = SessionExpired()
    args(mocker, output=str(tmp_path))
    assert await main_async() == 1
    flow.save_session.assert_called_once()

@pytest.mark.parametrize("error, code", [
    (None, 0),
    (KeyboardInterrupt(), 130),
    (Exception("Executable doesn't exist, run playwright install chromium"), 1),
    (Exception("Boom"), 1),
])
def test_main_exit_codes(mocker, error, code):
    mocker.patch("dgfip_fetcher.cli.main_async", new=mocker.Mock())
    mocker.patch("asyncio.run", return_value=0, side_effect=error)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == code
