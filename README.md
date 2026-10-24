# dgfip-fetcher

**dgfip-fetcher** is a CLI tool to automatically download all your tax documents (income tax notices, declarations, property taxes, etc.) from your personal space on [impots.gouv.fr](https://cfspart.impots.gouv.fr/espace-particulier/).

> **Note:** This tool is specifically designed for the French tax administration website.

## Key Features

*   **Time-saving**: No more manual clicking through each year.
*   **Clear Organization**: One folder per year, with the income tax notices (*avis d'impôt*) at its root and the other documents in sub-folders (`Déclarations`, `Taxes locales`, `Factures`, `Autres`). Files are named after the year and the document title (e.g., `2022_avis_de_taxes_foncieres_2022_c4e1a9.pdf`). The short suffix is derived from the document identifier, so two documents with the same title (e.g. local invoices) never collide.
*   **Incremental**: Documents already present in the output folder are skipped, so you can run it every year in the same folder.
*   **Secure**: Your credentials are stored in your system's secure vault (Keyring).
*   **Simple**: One command to fetch everything.

## Installation

```bash
pip install dgfip-fetcher
```

After installation, you **must** download the browser used by Playwright:
```bash
python -m playwright install chromium
```

*(Note: If you use `uv`, run: `uv run playwright install chromium`)*

## Usage

Once installed, simply run:

```bash
dgfip-fetcher
```

### Options

*   `--years N`: Number of previous years to scan (default: 10).
*   `--output DIR`: Destination folder for PDFs.
*   `--flat`: Saves all files directly in the destination folder instead of year folders.
*   `--debug`: Shows the browser during login (useful for troubleshooting). When asked for the 2FA code, you can also type it in the browser and just press Enter in the terminal.
*   `--reset`: Clears saved credentials and session.

**Example:**
```bash
dgfip-fetcher --years 5 --output my_tax_archives
```

## How It Works

1.  **Authentication**: Uses Playwright to handle login and 2FA (SMS/Email) from the official French tax portal. The session is saved and reused, so the 2FA code is only asked when it has expired.
    If the login fails, a screenshot of the page is saved in the config folder (`login_failure.png`) to help troubleshooting.
2.  **Secret Storage**: 
    *   Your **French tax ID (SPI)** and the session cookies are stored in a standard config folder, readable only by your user.
    *   Your password is encrypted and stored in your OS keychain.
3.  **Retrieval**: All documents (tax notices, returns, acknowledgements, local invoices...) are listed from the "Documents" page and downloaded with plain HTTP requests.

## Development

To contribute:
1. Clone the repository.
2. Install dependencies: `uv sync`.
3. Run in dev mode: `uv run dgfip-fetcher`.

## Disclaimer

This project is an independent tool and is NOT affiliated with the Direction générale des Finances publiques (DGFiP) or impots.gouv.fr. Use it at your own risk.
