# Pinterest Scraper

A local web-based tool for exploring and downloading Pinterest images. Built with Python, Playwright, and a lightweight aiohttp server.

> **Disclaimer:** This project is for **educational and research purposes only**. Scraping Pinterest may violate their [Terms of Service](https://policy.pinterest.com/en/terms-of-service). The authors are not responsible for how this tool is used. Do not use it to infringe on copyrights or redistribute content without permission. Use at your own risk.

![Screenshot](display-img.png)

https://github.com/DanielBartolic/pinterest-scraper/raw/main/demo.mp4

## Features

- **Search or explore** — Enter a search query (e.g. "pottery", "street fashion") or paste a direct Pinterest pin URL
- **Infinite scrolling** — Scrapes as many images as you want, streamed in real-time
- **Drill down** — Click any image to find similar pins, with full navigation history
- **Select & download** — Pick individual images or select all, then batch download to organized collections
- **Collections** — Downloaded images are saved to named folders with a cache manifest, so duplicates are skipped on re-download
- **No account required** — Uses headless Chromium via Playwright, no Pinterest login needed

## Requirements

- Python 3.8+
- Chromium browser (installed automatically by Playwright)

## Installation

```bash
# Clone the repo
git clone https://github.com/DanielBartolic/pinterest-scraper.git
cd pinterest-scraper

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (one-time setup)
playwright install chromium
```

## Usage

```bash
python server.py
```

This starts the server and opens your browser at `http://localhost:8080`.

### Searching

1. Type a **search query** (e.g. "ceramic vases") or paste a **Pinterest pin URL** into the search bar
2. Set the number of images to find (default: 20, no upper limit)
3. Click **Scrape** — images stream in as they're found

### Exploring

- **Click any image** to drill into that pin and discover similar images
- Use the **back arrow** to return to previous results
- Each drill-down creates a new scraping session for that pin

### Selecting images

There are two ways to enter select mode:

- **Click the Select button** in the toolbar — stays on until you click it again
- **Hold Shift** — temporarily enables selection while held, turns off when released

Once in select mode:
- Click images to **toggle selection** (selected = red border)
- Use **Select All** to select every visible image
- Use **Clear** to deselect everything

### Downloading

1. Type a **collection name** (e.g. "pottery") in the collection input, or pick an existing collection from the dropdown
2. Click **Download** — selected images are saved to `./downloads/<collection>/`
3. A `cache.json` manifest tracks what's been downloaded, so running again skips duplicates
4. Previously downloaded images show a **green border**

### File structure after download

```
downloads/
  pottery/
    pin_a1b2c3d4e5f6.jpg
    pin_f7e8d9c0b1a2.jpg
    cache.json
  street-fashion/
    pin_1a2b3c4d5e6f.jpg
    cache.json
```

## How it works

1. **server.py** starts an aiohttp web server and launches a persistent headless Chromium browser via Playwright
2. When you search or explore a pin, the server navigates Chromium to the Pinterest page and scrolls to load images
3. Pin data (image URLs, descriptions, pin links) is extracted from the DOM and streamed to the frontend via Server-Sent Events (SSE)
4. Images are proxied through the server to avoid hotlink restrictions from Pinterest's CDN
5. Downloads are fetched server-side with proper headers and saved to the local filesystem

## Tech stack

| Component | Technology |
|-----------|-----------|
| Backend | Python, aiohttp |
| Browser automation | Playwright (Chromium) |
| Frontend | Vanilla HTML/CSS/JS |
| Image downloads | aiohttp + aiofiles |

## License

[MIT](LICENSE) — see the [Disclaimer](#pinterest-scraper) above regarding usage.
