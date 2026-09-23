#!/usr/bin/env python3
"""
Zero-Cost Google Maps Scraper for Hermes Agents.
Headless extraction using Playwright + semantic attributes.
Zero paid APIs. Zero brittle CSS hash classes.
Handles both multi-result feeds and direct single-place matches.
"""

import argparse
import csv
import json
import logging
import os
import random
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

# Administrative and non-business category labels to reject
ADMIN_CATEGORIES = {
    "city",
    "town",
    "district",
    "administrative area",
    "metropolitan area",
    "country",
    "state",
    "province",
    "neighborhood",
    "sublocality",
    "municipality",
    "village",
    "county",
    "region",
}


@dataclass
class BusinessPlace:
    name: str = ""
    category: str = ""
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    address: str = ""
    phone: str = ""
    website: str = ""
    plus_code: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    maps_url: str = ""
    scraped_at: str = ""


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )


def handle_consent(page: Page):
    """Bypasses Google consent / privacy redirects on European/cloud IPs."""
    try:
        consent_selectors = [
            'button:has-text("Accept all")',
            'button:has-text("I agree")',
            'button:has-text("Agree")',
            'form[action*="consent"] button',
            'button[aria-label*="Accept"]'
        ]
        for sel in consent_selectors:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible():
                logging.info("Handling Google consent screen...")
                btn.click()
                page.wait_for_timeout(2500)
                break
    except Exception as e:
        logging.debug(f"Consent check non-blocking note: {e}")


def parse_coordinates_from_url(url: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Extracts coordinates from Google Maps URLs.
    Prioritizes actual business pin coordinates (!3d<lat>!4d<lng>) over
    viewport/camera coordinates (@<lat>,<lng>).
    """
    if not url:
        return None, None

    # 1. Exact place pin coordinates (!3d<lat>!4d<lng>)
    pin_match = re.search(r'!3d(-?\d+(?:\.\d+)?).*?!4d(-?\d+(?:\.\d+)?)', url)
    if pin_match:
        try:
            return float(pin_match.group(1)), float(pin_match.group(2))
        except ValueError:
            pass

    # 2. Viewport camera center fallback (@<lat>,<lng>)
    camera_match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if camera_match:
        try:
            return float(camera_match.group(1)), float(camera_match.group(2))
        except ValueError:
            pass

    return None, None


def is_valid_business(place: BusinessPlace) -> bool:
    """
    Validates whether an extracted place is an actual commercial business listing
    rather than an administrative locality, geographic boundary, or empty suggestion card.

    A valid business must have either:
    - A rating or review count, OR
    - A phone number, OR
    - A commercial category (excluding administrative labels like City, Town, District,
      Administrative area, Metropolitan area, Country, or completely empty fields across
      name/phone/rating/address).
    """
    if not place or not place.name or not place.name.strip():
        return False

    # Check for rating or reviews count
    if place.rating is not None or place.reviews_count is not None:
        return True

    # Check for valid phone number
    if place.phone and place.phone.strip():
        return True

    # Check commercial category
    cat = place.category.strip().lower() if place.category else ""
    if cat and cat not in ADMIN_CATEGORIES:
        has_substantive_info = bool(
            place.address.strip()
            or place.website.strip()
            or (place.phone and place.phone.strip())
            or place.rating is not None
            or place.reviews_count is not None
        )
        if has_substantive_info:
            return True

    return False


def build_search_url(query: str, country: Optional[str] = None) -> str:
    """Builds Google Maps search URL with optional country code (gl)."""
    encoded_query = urllib.parse.quote_plus(query.strip())
    url = f"https://www.google.com/maps/search/{encoded_query}?hl=en"
    if country and country.strip():
        url += f"&gl={urllib.parse.quote_plus(country.strip().lower())}"
    return url


def extract_place_details(page: Page, place_title_hint: str = "") -> BusinessPlace:
    """Extracts business data using semantic and stable DOM attributes."""
    place = BusinessPlace()
    place.scraped_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # 1. Maps URL and GPS coordinates (prefers pin coords !3d/!4d over viewport @)
    current_url = page.url
    place.maps_url = current_url
    place.latitude, place.longitude = parse_coordinates_from_url(current_url)

    # 2. Business Name from H1
    target_h1 = None
    try:
        h1s = page.locator('h1').all()
        for h in h1s:
            txt = h.inner_text().strip()
            if txt and txt.lower() != 'results':
                target_h1 = h
                place.name = txt
                break
    except Exception as e:
        logging.debug(f"H1 extraction fallback: {e}")

    if not place.name and place_title_hint:
        place.name = place_title_hint

    # 3. Category, Rating & Reviews
    if target_h1:
        try:
            header_container = target_h1.locator('xpath=../..')

            # Category
            cat_btn = header_container.locator('button[jsaction*="category"]').first
            if cat_btn.count() > 0:
                place.category = cat_btn.inner_text().strip()
            if not place.category:
                for b in header_container.locator('button').all():
                    btxt = b.inner_text().strip()
                    if btxt and re.match(r'^[A-Za-z\s&-]+$', btxt) and len(btxt.split()) <= 4:
                        place.category = btxt
                        break

            # Star Rating
            aria_star = header_container.locator('span[aria-label*="star"]').first
            if aria_star.count() > 0:
                star_text = aria_star.get_attribute('aria-label') or ''
                rm = re.search(r'([\d\.]+)\s*star', star_text, re.IGNORECASE)
                if rm:
                    place.rating = float(rm.group(1))
            if place.rating is None:
                for s in header_container.locator('span').all_inner_texts():
                    if re.match(r'^\d\.\d$', s.strip()):
                        place.rating = float(s.strip())
                        break

            # Reviews Count
            for s in header_container.locator('span').all_inner_texts():
                s = s.strip()
                if s.startswith('(') and s.endswith(')'):
                    cleaned = re.sub(r'[^\d]', '', s)
                    if cleaned:
                        place.reviews_count = int(cleaned)
                        break
        except Exception as e:
            logging.debug(f"Header meta extraction error: {e}")

    # 4. Address via stable data-item-id
    try:
        addr_el = page.locator('[data-item-id="address"]').first
        if addr_el.count() > 0:
            raw_addr = addr_el.inner_text().replace('\n', ' ').strip()
            place.address = re.sub(r'^[^\w\s]+', '', raw_addr).strip()
    except Exception as e:
        logging.debug(f"Address extraction error: {e}")

    # 5. Phone number via stable data-item-id prefix
    try:
        phone_el = page.locator('[data-item-id^="phone:"]').first
        if phone_el.count() > 0:
            raw_phone = phone_el.inner_text().replace('\n', ' ').strip()
            place.phone = re.sub(r'^[^\w\s+]+', '', raw_phone).strip()
    except Exception as e:
        logging.debug(f"Phone extraction error: {e}")

    # 6. Official Website via stable data-item-id
    try:
        web_el = page.locator('[data-item-id="authority"]').first
        if web_el.count() > 0:
            href = web_el.get_attribute('href')
            if href:
                place.website = href
            else:
                place.website = web_el.inner_text().replace('\n', ' ').strip()
    except Exception as e:
        logging.debug(f"Website extraction error: {e}")

    # 7. Plus Code / Oloc
    try:
        oloc_el = page.locator('[data-item-id="oloc"]').first
        if oloc_el.count() > 0:
            raw_oloc = oloc_el.inner_text().replace('\n', ' ').strip()
            place.plus_code = re.sub(r'^[^\w\s+]+', '', raw_oloc).strip()
    except Exception as e:
        logging.debug(f"Oloc extraction error: {e}")

    return place


def scrape_google_maps(
    query: str,
    total: int = 10,
    country: Optional[str] = None,
    headless: bool = True
) -> List[BusinessPlace]:
    setup_logging()
    results: List[BusinessPlace] = []

    search_url = build_search_url(query, country=country)
    country_info = f" | Country (gl): {country.strip().lower()}" if country and country.strip() else ""
    logging.info(f"Starting scrape: '{query}' | Target: {total} places{country_info} | Headless: {headless}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="en-US"
        )
        page = context.new_page()

        # Inject anti-automation evasion
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        try:
            page.goto(search_url, timeout=30000)
            page.wait_for_timeout(2500)
            handle_consent(page)

            # Wait for either feed or direct place page
            page.wait_for_timeout(2500)

            # Check if this query landed directly on a single place page
            place_links = page.locator('a[href*="/maps/place/"]').all()

            if len(place_links) == 0:
                # Might be a single direct match
                h1_candidate = None
                for h in page.locator('h1').all():
                    txt = h.inner_text().strip()
                    if txt and txt.lower() != 'results':
                        h1_candidate = txt
                        break

                if h1_candidate or '/maps/place/' in page.url or page.locator('[data-item-id="address"]').count() > 0:
                    logging.info(f"Single direct place match detected: '{h1_candidate}'")
                    # Give URL a second to update coordinates
                    page.wait_for_timeout(2000)
                    place_data = extract_place_details(page, place_title_hint=h1_candidate or "")
                    if is_valid_business(place_data):
                        results.append(place_data)
                        logging.info(f"  -> Extracted: {place_data.name} | Cat: {place_data.category} | Rating: {place_data.rating} ({place_data.reviews_count}) | Phone: {place_data.phone}")
                    else:
                        logging.info(f"  -> Skipped non-business card: {place_data.name} ({place_data.category})")
                    return results

            # Multi-result feed
            feed = page.locator('div[role="feed"]')
            logging.info("Scrolling feed to discover listings...")
            stuck_count = 0
            prev_links_count = 0
            discovery_target = max(total, int(total * 1.5))

            while True:
                place_links = page.locator('a[href*="/maps/place/"]').all()
                count = len(place_links)
                logging.info(f"Discovered {count} listing links (target: {total})")

                if count >= discovery_target:
                    break
                if count == prev_links_count:
                    stuck_count += 1
                    if stuck_count >= 4:
                        logging.info("Reached end of search results or no more listings loading.")
                        break
                else:
                    stuck_count = 0
                prev_links_count = count

                if feed.count() > 0:
                    feed.evaluate("el => el.scrollBy(0, 3000)")
                else:
                    page.mouse.wheel(0, 3000)
                time.sleep(1.2 + random.uniform(0.2, 0.6))

            total_available = len(page.locator('a[href*="/maps/place/"]').all())
            logging.info(f"Beginning deep extraction (available: {total_available}, target: {total})...")

            for i in range(total_available):
                if len(results) >= total:
                    break
                try:
                    current_link = page.locator('a[href*="/maps/place/"]').nth(i)
                    title_hint = current_link.get_attribute('aria-label') or f"Place #{i+1}"

                    logging.info(f"[{i+1}/{total_available}] Extracting: {title_hint}")
                    current_link.click()

                    page.wait_for_timeout(2000 + int(random.uniform(200, 600)))

                    place_data = extract_place_details(page, place_title_hint=title_hint)
                    if is_valid_business(place_data):
                        results.append(place_data)
                        logging.info(f"  -> Extracted: {place_data.name} | Cat: {place_data.category} | Rating: {place_data.rating} ({place_data.reviews_count}) | Phone: {place_data.phone}")
                    else:
                        logging.info(f"  -> Skipped non-business card: {place_data.name} ({place_data.category})")

                except Exception as ex:
                    logging.warning(f"Failed extracting listing #{i+1}: {ex}")
                    continue

        finally:
            browser.close()

    return results


def save_results(results: List[BusinessPlace], output_path: str, append: bool = False):
    if not results:
        logging.warning("No records to save.")
        return

    records = [asdict(r) for r in results]
    ext = os.path.splitext(output_path)[1].lower()

    if ext == ".json":
        existing = []
        if append and os.path.exists(output_path):
            try:
                with open(output_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []
        combined = existing + records
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(combined, f, indent=2, ensure_ascii=False)
        logging.info(f"Saved {len(combined)} records to JSON: {output_path}")
    else:
        fieldnames = list(records[0].keys())
        file_exists = os.path.isfile(output_path)
        mode = "a" if append else "w"
        with open(output_path, mode, newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not (append and file_exists):
                writer.writeheader()
            for r in records:
                writer.writerow(r)
        logging.info(f"Saved {len(records)} records to CSV: {output_path} (mode={mode})")


def main():
    parser = argparse.ArgumentParser(description="Zero-Cost Google Maps Scraper (Playwright Headless)")
    parser.add_argument("-s", "--search", type=str, required=True, help="Search query for Google Maps")
    parser.add_argument("-t", "--total", type=int, default=10, help="Number of places to extract (default: 10)")
    parser.add_argument("-c", "--country", type=str, default=None, help="Two-letter country code (e.g. us, uk, my) for &gl=<country> regional bias")
    parser.add_argument("-o", "--output", type=str, default="gmaps_results.csv", help="Output file path (.csv or .json)")
    parser.add_argument("--append", action="store_true", help="Append results to existing file")
    parser.add_argument("--headful", action="store_true", help="Run in visible browser window (default: headless)")

    args = parser.parse_args()
    places = scrape_google_maps(
        query=args.search,
        total=args.total,
        country=args.country,
        headless=not args.headful
    )
    save_results(places, args.output, append=args.append)


if __name__ == "__main__":
    main()
