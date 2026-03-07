import pytest
import httpx
import respx
from dgfip_fetcher.scraper import process_year, login_via_playwright

@pytest.mark.asyncio
async def test_process_year_no_docs(tmp_path):
    year = 2023
    output_dir = str(tmp_path)
    async with respx.mock() as respx_mock:
        respx_mock.get(f"https://cfspart.impots.gouv.fr/enp/documents.do?n={year}").mock(
            return_value=httpx.Response(200, text="<html><body>No docs here</body></html>")
        )
        async with httpx.AsyncClient() as client:
            await process_year(client, year, output_dir)
    assert len(list(tmp_path.iterdir())) == 0

@pytest.mark.asyncio
async def test_process_year_with_docs(tmp_path):
    year = 2023
    output_dir = str(tmp_path)
    html_content = '<html><body><iframe src="/enp/documents.do?n=2023"></iframe></body></html>'
    iframe_content = """
    <html>
        <body>
            <form action="Affichage_Document_PDF">
                <input name="idEnsua" value="mock_id_123">
                <button title="« Visualiser PDF » Avis d'imposition 2023"></button>
            </form>
        </body>
    </html>
    """
    async with respx.mock() as respx_mock:
        respx_mock.get(f"https://cfspart.impots.gouv.fr/enp/documents.do?n={year}").mock(
            return_value=httpx.Response(200, text=html_content)
        )
        respx_mock.get("https://cfspart.impots.gouv.fr/enp/documents.do?n=2023").mock(
            return_value=httpx.Response(200, text=iframe_content)
        )
        respx_mock.get("https://cfspart.impots.gouv.fr/enp/Affichage_Document_PDF?idEnsua=mock_id_123").mock(
            return_value=httpx.Response(200, content=b"%PDF-1.4 content")
        )
        async with httpx.AsyncClient() as client:
            await process_year(client, year, output_dir)
    assert len(list(tmp_path.glob("*.pdf"))) == 1

@pytest.mark.asyncio
async def test_process_year_error(tmp_path):
    async with httpx.AsyncClient() as client:
        await process_year(client, None, str(tmp_path))

@pytest.mark.asyncio
async def test_login_via_playwright_otp(mocker):
    mock_p = mocker.patch("dgfip_fetcher.scraper.async_playwright")
    mock_browser = mocker.AsyncMock()
    mock_context = mocker.AsyncMock()
    mock_page = mocker.AsyncMock()
    
    mock_p.return_value.__aenter__.return_value.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    
    mock_page.wait_for_selector.return_value = mocker.AsyncMock()
    mock_otp_input = mocker.AsyncMock()
    mock_page.query_selector.side_effect = [mock_otp_input, None]
    mocker.patch("builtins.input", return_value="123456")
    mock_context.cookies.return_value = [{"name": "test", "value": "val"}]
    
    res = await login_via_playwright("spi", "pwd", headless=True)
    assert res == {"test": "val"}

@pytest.mark.asyncio
async def test_login_via_playwright_failure_total(mocker):
    mock_p = mocker.patch("dgfip_fetcher.scraper.async_playwright")
    mock_p.return_value.__aenter__.side_effect = Exception("Browser error")
    res = await login_via_playwright("spi", "pwd", headless=False)
    assert res is None

@pytest.mark.asyncio
async def test_login_via_playwright_retry_logic(mocker):
    # Mock async_playwright
    mock_p = mocker.patch("dgfip_fetcher.scraper.async_playwright")
    
    # Success mocks
    mock_browser = mocker.AsyncMock()
    mock_context = mocker.AsyncMock()
    mock_page = mocker.AsyncMock()
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.wait_for_selector.return_value = mocker.AsyncMock()
    mock_page.query_selector.return_value = None
    mock_context.cookies.return_value = [{"name": "retry", "value": "ok"}]

    # The trick: chromium.launch will fail the first time, succeed the second
    mock_p.return_value.__aenter__.return_value.chromium.launch.side_effect = [
        Exception("Headless fail"), 
        mock_browser
    ]
    
    # This should trigger the retry logic in the 'except' block
    res = await login_via_playwright("spi", "pwd", headless=True)
    
    assert res == {"retry": "ok"}
    # Verify it was called twice (once headless=True, once headless=False)
    assert mock_p.call_count == 2
