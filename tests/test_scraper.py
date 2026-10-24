import httpx
import pytest
import respx
from dgfip_fetcher import scraper
from dgfip_fetcher.utils import document_filename
from dgfip_fetcher.scraper import (
    Document, SessionExpired, parse_documents, list_documents, download_documents,
    session_is_valid, login_via_playwright, user_agent_for, DOCUMENTS_URL, PDF_URL, HOME_URL,
)

def doc_link(id_ensua, title):
    # Main documents (notices, invoices): links, listed twice (desktop and mobile layouts)
    link = f"""
    <h3><a aria-label="{title} (nouvelle fenêtre)" href="Affichage_Document_PDF?idEnsua={id_ensua}" target="_blank">{title}</a></h3>"""
    return link * 2

def doc_form(id_ensua, title):
    # Associated documents (annexes, acknowledgements): forms, also listed twice
    form = f"""
    <form action="Affichage_Document_PDF" method="GET" target="_blank">
        <input type="hidden" name="idEnsua" value="{id_ensua}">
        <button type="submit" title="Visualiser {title}&nbsp;&nbsp; (nouvelle fenêtre)">Visualiser</button>
    </form>"""
    return form * 2

def year_section(year, *docs):
    return f'<div class="fr-collapse" id="{year}"><div class="fr-grid-row">{"".join(docs)}</div></div>'

DOCS_HTML = "<html><body>" + "".join([
    year_section(2026,
        doc_link("ID1", "Avis d'impôt 2026 sur les revenus et prélèvements sociaux 2025"),
        doc_link("ID2", "Facture locale COMMUNE-EXEMPLE"),
        doc_form("ID3", "Accusé de réception de télédéclaration des revenus 2025"),
        doc_form("ID4", "Accusé de réception de télédéclaration des revenus 2025"),
    ),
    year_section(2019, doc_link("ID5", "Avis de taxe foncière 2019")),
    # Outside any year section: the year comes from the title, if any
    doc_link("ID6", "Avis de situation déclarative 2025"),
    doc_link("ID7", "Lettre de relance"),
]) + "</body></html>"

def redirect_to_login():
    return httpx.Response(302, headers={"Location": "https://cfspart-idp.impots.gouv.fr/oauth2/authorize"})

def test_parse_documents():
    docs = parse_documents(DOCS_HTML)
    assert len(docs) == 14
    assert docs[0] == Document("ID1", "Avis d'impôt 2026 sur les revenus et prélèvements sociaux 2025", 2026)
    assert docs[2] == Document("ID2", "Facture locale COMMUNE-EXEMPLE", 2026)
    assert docs[4] == Document("ID3", "Accusé de réception de télédéclaration des revenus 2025", 2026)
    assert [d.year for d in docs[-4::2]] == [2025, None]

@pytest.mark.asyncio
async def test_list_documents_deduplicates_and_filters_years():
    async with respx.mock() as respx_mock:
        respx_mock.get(DOCUMENTS_URL).mock(return_value=httpx.Response(200, text=DOCS_HTML))
        async with httpx.AsyncClient() as client:
            docs = await list_documents(client, range(2026, 2023, -1))
    # ID5 (2019) is out of range; ID7 has no known year so it is kept
    assert [d.id for d in docs] == ["ID1", "ID2", "ID3", "ID4", "ID6", "ID7"]

@pytest.mark.asyncio
async def test_list_documents_session_expired():
    async with respx.mock() as respx_mock:
        respx_mock.get(DOCUMENTS_URL).mock(return_value=redirect_to_login())
        respx_mock.get(url__startswith="https://cfspart-idp.impots.gouv.fr/").mock(return_value=httpx.Response(200))
        async with httpx.AsyncClient(follow_redirects=True) as client:
            with pytest.raises(SessionExpired):
                await list_documents(client, [2025])

@pytest.mark.asyncio
async def test_download_documents(tmp_path):
    docs = [
        Document("ID2", "Accusé de réception des revenus 2025", 2025),
        Document("ID3", "Accusé de réception des revenus 2025", 2025),
        Document("BAD", "Avis de taxe foncière 2025", 2025),
    ]
    async with respx.mock() as respx_mock:
        respx_mock.get(PDF_URL.format(id="ID2")).mock(return_value=httpx.Response(200, content=b"%PDF-1.6 two"))
        respx_mock.get(PDF_URL.format(id="ID3")).mock(return_value=httpx.Response(200, content=b"%PDF-1.6 three"))
        respx_mock.get(PDF_URL.format(id="BAD")).mock(return_value=httpx.Response(200, text="<html>error</html>"))
        async with httpx.AsyncClient() as client:
            assert await download_documents(client, docs, tmp_path) == 2
            # Second run, with the documents listed in another order: nothing new, no duplicate
            assert await download_documents(client, docs[::-1], tmp_path) == 0

    two, three = (document_filename(d.title, d.year, d.id) for d in docs[:2])
    folder = tmp_path / "2025" / "Déclarations"
    assert sorted(p.name for p in folder.iterdir()) == sorted([two, three])
    assert (folder / three).read_bytes() == b"%PDF-1.6 three"

@pytest.mark.asyncio
async def test_download_documents_layout(tmp_path):
    docs = [
        Document("A", "Avis d'impôt 2026 sur les revenus et prélèvements sociaux 2025", 2026),
        Document("F", "Facture locale COMMUNE-EXEMPLE", 2026),
        Document("L", "Lettre de relance", None),
    ]
    async with respx.mock() as respx_mock:
        respx_mock.get(url__startswith=PDF_URL.format(id="")).mock(return_value=httpx.Response(200, content=b"%PDF"))
        async with httpx.AsyncClient() as client:
            await download_documents(client, docs, tmp_path / "tree")
            await download_documents(client, docs, tmp_path / "flat", flat=True)

    tree = sorted(str(p.relative_to(tmp_path / "tree")) for p in (tmp_path / "tree").rglob("*.pdf"))
    assert tree == sorted([
        f"2026/{document_filename(docs[0].title, 2026, 'A')}",
        f"2026/Factures/{document_filename(docs[1].title, 2026, 'F')}",
        f"Sans année/Factures/{document_filename(docs[2].title, None, 'L')}",
    ])
    assert len([p for p in (tmp_path / "flat").iterdir() if p.is_file()]) == 3

@pytest.mark.asyncio
async def test_download_documents_finds_files_moved_by_hand(tmp_path):
    doc = Document("A", "Avis d'impôt 2026", 2026)
    moved = tmp_path / "rangement perso" / document_filename(doc.title, doc.year, doc.id)
    moved.parent.mkdir()
    moved.write_bytes(b"%PDF")
    async with respx.mock():
        async with httpx.AsyncClient() as client:
            assert await download_documents(client, [doc], tmp_path) == 0

@pytest.mark.asyncio
async def test_download_documents_retries_dropped_connections(tmp_path, mocker):
    mocker.patch("dgfip_fetcher.scraper.asyncio.sleep")
    async with respx.mock() as respx_mock:
        respx_mock.get(PDF_URL.format(id="ID1")).mock(side_effect=[
            httpx.RemoteProtocolError("Server disconnected"), httpx.Response(200, content=b"%PDF-1.6"),
        ])
        respx_mock.get(PDF_URL.format(id="ID2")).mock(side_effect=httpx.RemoteProtocolError("Server disconnected"))
        async with httpx.AsyncClient() as client:
            docs = [Document("ID1", "Avis", 2025), Document("ID2", "Facture", 2025)]
            # ID2 keeps failing: it is skipped, the run goes on
            assert await download_documents(client, docs, tmp_path) == 1

@pytest.mark.asyncio
async def test_download_documents_session_expired(tmp_path):
    async with respx.mock() as respx_mock:
        respx_mock.get(PDF_URL.format(id="ID1")).mock(return_value=redirect_to_login())
        respx_mock.get(url__startswith="https://cfspart-idp.impots.gouv.fr/").mock(return_value=httpx.Response(200))
        async with httpx.AsyncClient(follow_redirects=True) as client:
            with pytest.raises(SessionExpired):
                await download_documents(client, [Document("ID1", "Avis", 2025)], tmp_path)

@pytest.mark.asyncio
async def test_session_is_valid():
    async with respx.mock() as respx_mock:
        route = respx_mock.get(HOME_URL)
        respx_mock.get(url__startswith="https://cfspart-idp.impots.gouv.fr/").mock(return_value=httpx.Response(200))
        async with httpx.AsyncClient(follow_redirects=True) as client:
            route.mock(return_value=httpx.Response(200, text="Se déconnecter"))
            assert await session_is_valid(client)
            route.mock(return_value=redirect_to_login())
            assert not await session_is_valid(client)
            route.mock(side_effect=httpx.ConnectError("offline"))
            assert not await session_is_valid(client)

def test_user_agent_for(mocker):
    mocker.patch("dgfip_fetcher.scraper.sys.platform", "darwin")
    ua = user_agent_for("145.0.7632.6")
    assert "Chrome/145.0.0.0" in ua and "Macintosh" in ua and "Headless" not in ua

@pytest.fixture
def playwright_mocks(mocker):
    mock_p = mocker.patch("dgfip_fetcher.scraper.async_playwright")
    browser = mocker.AsyncMock()
    browser.version = "145.0.7632.6"
    context = mocker.AsyncMock()
    page = mocker.AsyncMock()
    mock_p.return_value.__aenter__.return_value.chromium.launch.return_value = browser
    browser.new_context.return_value = context
    context.new_page.return_value = page
    context.cookies.return_value = [{"name": "SESSION", "value": "val", "domain": ".impots.gouv.fr", "path": "/"}]

    # page.locator(...).filter(visible=True) -> locator whose count() tells if the element is visible
    locators = {}
    def locator(selector):
        loc = mocker.MagicMock()
        visible = locators.setdefault(selector, mocker.MagicMock())
        visible.count = mocker.AsyncMock(return_value=0)
        visible.first.fill = mocker.AsyncMock()
        visible.first.click = mocker.AsyncMock()
        loc.filter.return_value = visible
        return loc
    page.locator = mocker.MagicMock(side_effect=locator)
    mocker.patch("dgfip_fetcher.scraper.dump_page")
    return browser, page, locators

@pytest.mark.asyncio
async def test_login_without_otp(playwright_mocks, mocker):
    browser, page, _ = playwright_mocks
    input_mock = mocker.patch("builtins.input")
    cookies, user_agent = await login_via_playwright("spi", "pwd")
    assert cookies.get("SESSION") == "val"
    assert "Chrome/145" in user_agent
    input_mock.assert_not_called()
    page.fill.assert_any_call("#pwd_tmp", "pwd")
    browser.close.assert_awaited()

@pytest.mark.asyncio
async def test_login_with_otp(playwright_mocks, mocker):
    _, page, locators = playwright_mocks
    original = page.locator.side_effect
    def locator(selector):
        loc = original(selector)
        if selector in (scraper.OTP_SELECTOR, "#btnAction"):
            loc.filter.return_value.count.return_value = 1
        return loc
    page.locator.side_effect = locator
    mocker.patch("builtins.input", return_value="123456")

    assert await login_via_playwright("spi", "pwd") is not None
    locators[scraper.OTP_SELECTOR].first.fill.assert_awaited_with("123456")
    locators["#btnAction"].first.click.assert_awaited()

@pytest.mark.asyncio
async def test_login_failure_saves_page_and_does_not_retry(playwright_mocks, mocker):
    browser, page, _ = playwright_mocks
    page.wait_for_selector.side_effect = Exception("Timeout")
    assert await login_via_playwright("spi", "pwd") is None
    scraper.dump_page.assert_awaited_once()
    browser.close.assert_awaited()
    assert scraper.async_playwright.call_count == 1
