# dgfip-fetcher

**dgfip-fetcher** is a CLI tool to automatically download all your tax documents (income tax notices, declarations, property taxes, etc.) from your personal space on [impots.gouv.fr](https://cfspart.impots.gouv.fr/espace-particulier/).

> **Note:** This tool is specifically designed for the French tax administration website.

## Key Features

*   **Time-saving**: No more manual clicking through each year.
*   **Clear Organization**: Files are automatically renamed (e.g., `2023_property_tax.pdf`).
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
*   `--debug`: Shows the browser during login (useful for 2FA or troubleshooting).
*   `--reset`: Clears saved credentials and session.

**Example:**
```bash
dgfip-fetcher --years 5 --output my_tax_archives
```

## How It Works

1.  **Authentication**: Uses Playwright to handle login and 2FA (SMS/Email) from the official French tax portal.
2.  **Secret Storage**: 
    *   Your **French tax ID (SPI)** is stored in a standard config folder.
    *   Your password is encrypted and stored in your OS keychain.
3.  **Retrieval**: Documents are detected and downloaded using efficient asynchronous requests.

## Development

To contribute:
1. Clone the repository.
2. Install dependencies: `uv sync`.
3. Run in dev mode: `uv run dgfip-fetcher`.

## Disclaimer

This project is an independent tool and is NOT affiliated with the Direction générale des Finances publiques (DGFiP) or impots.gouv.fr. Use it at your own risk.
