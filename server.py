"""
Interactive Pinterest Scraper - Desktop App
Run: python server.py
"""

import json
import asyncio
import webbrowser
from pathlib import Path
from urllib.parse import unquote

import aiohttp
from aiohttp import web
from playwright.async_api import async_playwright

from pin_scraper import stream_similar_pins, generate_filename, download_image

# Global persistent browser
browser = None
playwright_instance = None

DOWNLOADS_DIR = Path(__file__).parent / "downloads"


async def index(request):
    return web.FileResponse(Path(__file__).parent / "static" / "index.html")


def resolve_pinterest_url(query):
    """Turn user input into a Pinterest URL. Accepts pin URLs, search URLs, or plain text queries."""
    query = query.strip()
    if "pinterest.com/" in query:
        return query, query  # already a URL
    # Plain text -> search URL
    from urllib.parse import quote
    url = f"https://www.pinterest.com/search/pins/?q={quote(query)}&rs=typed"
    return url, ""


async def scrape_stream(request):
    """SSE endpoint: streams pin batches as they're found."""
    raw_input = request.query.get("pin_url", "").strip()
    count = int(request.query.get("count", 20))

    if not raw_input:
        return web.json_response(
            {"error": "Please enter a pin URL or search query"}, status=400
        )

    nav_url, seed_url = resolve_pinterest_url(raw_input)

    resp = web.StreamResponse()
    resp.content_type = "text/event-stream"
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    await resp.prepare(request)

    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()

    try:
        await page.goto(nav_url, wait_until="domcontentloaded", timeout=30000)

        async for batch in stream_similar_pins(page, count, seed_url=seed_url):
            for img in batch:
                img["source_pin"] = raw_input
            data = json.dumps(batch)
            await resp.write(f"data: {data}\n\n".encode())

    except Exception as e:
        err = json.dumps({"error": str(e)})
        await resp.write(f"event: error\ndata: {err}\n\n".encode())

    await resp.write(b"event: done\ndata: {}\n\n")
    await context.close()
    return resp


async def proxy_image(request):
    """Proxy Pinterest CDN images to avoid hotlink issues"""
    url = unquote(request.query.get("url", ""))
    if not url or "pinimg.com" not in url:
        return web.Response(status=400, text="Invalid image URL")

    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.pinterest.com/",
            }
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status == 200:
                    body = await resp.read()
                    ct = resp.headers.get("Content-Type", "image/jpeg")
                    return web.Response(body=body, content_type=ct)
                return web.Response(status=resp.status)
    except Exception:
        return web.Response(status=502)


async def download_pins(request):
    """Download selected pins to a collection folder inside ./downloads/."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    name = body.get("collection", "").strip()
    pins = body.get("pins", [])

    if not name:
        return web.json_response({"error": "No collection name"}, status=400)
    if not pins:
        return web.json_response({"error": "No pins to download"}, status=400)

    folder_path = DOWNLOADS_DIR / name
    folder_path.mkdir(parents=True, exist_ok=True)

    cache_file = folder_path / "cache.json"
    existing_cache = []
    existing_urls = set()
    if cache_file.exists():
        with open(cache_file) as f:
            existing_cache = json.load(f)
            existing_urls = {item["url"] for item in existing_cache}

    # Add new pins to cache (even before download, so they're tracked)
    new_pins = [p for p in pins if p["url"] not in existing_urls]
    semaphore = asyncio.Semaphore(10)
    downloaded = []

    async with aiohttp.ClientSession() as session:
        tasks = []
        for pin in new_pins:
            filename = generate_filename(pin["url"])
            filepath = folder_path / filename
            pin_with_file = {**pin, "filename": filename}
            task = download_image(session, pin["url"], filepath, semaphore)
            tasks.append((pin_with_file, task))

        if tasks:
            results = await asyncio.gather(*[t[1] for t in tasks])
            for (pin_data, _), success in zip(tasks, results):
                if success:
                    downloaded.append(pin_data)

    all_cache = existing_cache + downloaded
    with open(cache_file, "w") as f:
        json.dump(all_cache, f, indent=2)

    return web.json_response({
        "downloaded": len(downloaded),
        "already_cached": len(pins) - len(new_pins),
        "total": len(all_cache),
    })


async def get_cache(request):
    """Return cached pins from a collection's cache.json."""
    name = request.query.get("collection", "").strip()
    if not name:
        return web.json_response([])

    cache_file = DOWNLOADS_DIR / name / "cache.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return web.json_response(json.load(f))
    return web.json_response([])


async def list_collections(request):
    """List existing collection folders inside ./downloads/."""
    if not DOWNLOADS_DIR.exists():
        return web.json_response([])
    collections = []
    for d in sorted(DOWNLOADS_DIR.iterdir()):
        if d.is_dir():
            cache_file = d / "cache.json"
            count = 0
            if cache_file.exists():
                with open(cache_file) as f:
                    count = len(json.load(f))
            collections.append({"name": d.name, "count": count})
    return web.json_response(collections)


async def on_startup(app):
    global browser, playwright_instance
    playwright_instance = await async_playwright().start()
    browser = await playwright_instance.chromium.launch(headless=True)
    print("Browser ready")


async def on_cleanup(app):
    global browser, playwright_instance
    if browser:
        await browser.close()
    if playwright_instance:
        await playwright_instance.stop()


app = web.Application()
app.router.add_get("/", index)
app.router.add_get("/api/scrape", scrape_stream)
app.router.add_get("/api/proxy", proxy_image)
app.router.add_post("/api/download", download_pins)
app.router.add_get("/api/cache", get_cache)
app.router.add_get("/api/collections", list_collections)
app.router.add_static("/static", Path(__file__).parent / "static")
app.on_startup.append(on_startup)
app.on_cleanup.append(on_cleanup)

async def on_startup_open_browser(app):
    webbrowser.open("http://localhost:8080")

app.on_startup.append(on_startup_open_browser)

if __name__ == "__main__":
    print("Starting Pinterest Scraper at http://localhost:8080")
    web.run_app(app, host="localhost", port=8080)
