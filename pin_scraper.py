"""
Pinterest Pin Scraper
Extracts pin images via Playwright, streams batches as they're found.
"""

import re
import hashlib
import asyncio
import aiohttp
import aiofiles
from pathlib import Path
from typing import List, Dict

SCROLL_PAUSE = 0.8

# JS for extracting pin data from Pinterest DOM
_EXTRACT_JS = """
    (seedPinId) => {
        const results = [];
        let imgs = document.querySelectorAll('img[elementtiming*="related_pins"], img[elementtiming*="search"]');
        if (imgs.length === 0) {
            imgs = document.querySelectorAll('[data-test-id="pin"] [data-test-id="pinrep-image"]');
        }
        imgs.forEach(img => {
            let src = img.src || '';
            if (!src.includes('pinimg.com')) return;
            const alt = img.alt || '';
            if (alt === 'Selected board cover image') return;
            if (src.includes('/75x75') || src.includes('/30x30')) return;
            const srcset = img.getAttribute('srcset') || '';
            const origMatch = srcset.match(/(https:\\/\\/i\\.pinimg\\.com\\/originals\\/[^\\s]+)/);
            const match736 = srcset.match(/(https:\\/\\/i\\.pinimg\\.com\\/736x\\/[^\\s]+)/);
            if (origMatch) { src = origMatch[1]; }
            else if (match736) { src = match736[1]; }
            else { src = src.replace(/\\/[0-9]+x[^\\/]*\\//, '/736x/'); }
            const pin = img.closest('[data-test-id="pin"]');
            const link = pin ? pin.querySelector('a[href*="/pin/"]') : img.closest('a[href*="/pin/"]');
            let pinUrl = link ? link.href : null;
            if (pinUrl && pinUrl.includes('/repin/')) return;
            if (seedPinId && pinUrl && pinUrl.includes(seedPinId)) return;
            if (pinUrl && pinUrl.startsWith('/pin/')) { pinUrl = 'https://www.pinterest.com' + pinUrl; }
            if (!pinUrl || !pinUrl.includes('/pin/')) return;
            results.push({ url: src, alt: alt, pin_url: pinUrl });
        });
        return results;
    }
"""


async def stream_similar_pins(page, max_images=500, seed_url=""):
    """Async generator that yields new pin batches as they're found."""
    seen_urls = set()
    no_new_count = 0
    total = 0

    pin_match = re.search(r'/pin/(\d+)', seed_url)
    seed_pin_id = pin_match.group(1) if pin_match else ""

    try:
        await page.wait_for_selector(
            'img[elementtiming*="related_pins"], img[elementtiming*="search"]', timeout=5000,
        )
    except Exception:
        await page.wait_for_timeout(1000)

    while total < max_images:
        image_data = await page.evaluate(_EXTRACT_JS, seed_pin_id)

        batch = []
        for img in image_data:
            if img["url"] not in seen_urls:
                seen_urls.add(img["url"])
                batch.append(img)
                total += 1
                if total >= max_images:
                    break

        if batch:
            yield batch
            no_new_count = 0
        else:
            no_new_count += 1
            if no_new_count >= 4:
                break

        if total < max_images:
            await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            await asyncio.sleep(SCROLL_PAUSE)


def generate_filename(url: str) -> str:
    """Generate unique filename from URL"""
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    ext_match = re.search(r"\.(jpg|jpeg|png|gif|webp)", url.lower())
    ext = ext_match.group(0) if ext_match else ".jpg"
    return f"pin_{url_hash}{ext}"


async def download_image(
    session: aiohttp.ClientSession,
    url: str,
    filepath: Path,
    semaphore: asyncio.Semaphore,
) -> bool:
    """Download a single image"""
    async with semaphore:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.pinterest.com/",
            }
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    content = await response.read()
                    if len(content) < 5000:
                        return False
                    async with aiofiles.open(filepath, "wb") as f:
                        await f.write(content)
                    return True
        except Exception:
            pass
    return False
