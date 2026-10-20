#!/usr/bin/env python3

import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from tabulate import tabulate


# ── Configuration ──────────────────────────────────────────────

CTFTIME_URL = "https://ctftime.org/event/list/?online=1&upcoming=true"

MMT = timezone(timedelta(hours=6, minutes=30))
WINDOW = timedelta(days=7)

REQUEST_TIMEOUT = 25
DETAIL_DELAY = 0.5

# Approximate conversion rate. Change this when needed.
USD_TO_MMK = 4500

DEBUG = True


# ── Logging and browser helpers ─────────────────────────────────

def log(message):
    if DEBUG:
        print(f"[DEBUG] {message}", flush=True)


def safe_get(driver, url):
    """Navigate without crashing if a page takes too long."""
    log(f"Opening {url}")

    try:
        driver.get(url)
    except TimeoutException:
        print("[WARN] Page load timed out; checking loaded content.")
        try:
            driver.execute_script("window.stop();")
        except WebDriverException:
            pass

    try:
        WebDriverWait(driver, 10).until(
            lambda d: d.find_element("tag name", "body")
        )
    except (TimeoutException, WebDriverException):
        log("Could not confirm that the page body loaded.")

    log(f"Current URL: {driver.current_url}")


# ── Date handling ───────────────────────────────────────────────


def parse_event_dates(date_text):
    """
    Parse CTFtime date ranges such as:
    23 Oct., 00:30 UTC — 25 Oct. 2026, 00:30 UTC
    23 Oct., 07:00 MMT — 25 Oct. 2026, 07:00 MMT
    """
    pattern = re.compile(
        r"(\d{1,2}\s+[A-Za-z]{3}\.?(?:\s+\d{4})?,\s*\d{1,2}:\d{2})"
        r"\s*(UTC|MMT)\s*[—–-]\s*"
        r"(\d{1,2}\s+[A-Za-z]{3}\.?(?:\s+\d{4})?,\s*\d{1,2}:\d{2})"
        r"\s*(UTC|MMT)",
        re.IGNORECASE,
    )

    match = pattern.search(date_text)
    if not match:
        log(f"Could not parse date range: {date_text!r}")
        return None, None

    start_text, start_zone, end_text, end_zone = match.groups()

    # Remove periods after abbreviated month names.
    start_text = re.sub(r"([A-Za-z]{3})\.", r"\1", start_text)
    end_text = re.sub(r"([A-Za-z]{3})\.", r"\1", end_text)

    now = datetime.now(MMT)

    # The end date usually includes the year.
    end_year_match = re.search(r"\b(20\d{2})\b", end_text)
    start_year_match = re.search(r"\b(20\d{2})\b", start_text)

    end_year = int(end_year_match.group(1)) if end_year_match else now.year
    start_year = int(start_year_match.group(1)) if start_year_match else end_year

    try:
        start = date_parser.parse(
            start_text,
            default=datetime(start_year, 1, 1),
        )
        end = date_parser.parse(
            end_text,
            default=datetime(end_year, 1, 1),
        )

        # Correct year-boundary events, such as Dec -> Jan.
        if not start_year_match and not end_year_match and start.month > end.month:
            end = end.replace(year=start.year + 1)
        elif not start_year_match and start > end:
            start = start.replace(year=start.year - 1)

        # CTFtime displays either UTC or Myanmar Time.
        start_tz = timezone.utc if start_zone.upper() == "UTC" else MMT
        end_tz = timezone.utc if end_zone.upper() == "UTC" else MMT

        start = start.replace(tzinfo=start_tz).astimezone(MMT)
        end = end.replace(tzinfo=end_tz).astimezone(MMT)

        return start, end

    except (ValueError, OverflowError) as exc:
        log(f"Date parsing error: {exc}")
        return None, None


def format_date(start, end):
    return (
        f"{start.strftime('%d %b %H:%M')} - "
        f"{end.strftime('%d %b %H:%M')} MMT"
    )


def format_duration(start, end):
    total_minutes = int((end - start).total_seconds() // 60)

    days, remainder = divmod(total_minutes, 1440)
    hours, minutes = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")

    return " ".join(parts) or "0m"


# ── Event list scraping ─────────────────────────────────────────

def get_online_events(driver):
    safe_get(driver, CTFTIME_URL)

    try:
        WebDriverWait(driver, 15).until(
            lambda d: d.find_elements("css selector", "table tbody tr")
        )
    except TimeoutException:
        print("[ERROR] CTFtime event table did not load.")
        log(f"Page title: {driver.title}")
        log(driver.page_source[:1000])
        return []

    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.select_one("table.table")

    if not table:
        log("Could not find table.table in the page HTML.")
        log(driver.page_source[:1000])
        return []

    events = []

    for row in table.select("tbody tr"):
        cells = row.find_all("td", recursive=False)

        # Skip the header and malformed rows.
        if len(cells) < 4:
            continue

        link = cells[0].find("a", href=True)
        if not link:
            continue

        name = link.get_text(" ", strip=True)
        event_url = urljoin(CTFTIME_URL, link["href"])

        date_text = cells[1].get_text(" ", strip=True)
        event_format = cells[2].get_text(" ", strip=True)
        location = cells[3].get_text(" ", strip=True)

        # Verify online status instead of blindly trusting the URL.
        if not re.search(r"\bon[\s-]*line\b|\bonline\b", location, re.I):
            continue

        start, end = parse_event_dates(date_text)
        if not start or not end:
            log(f"Skipping unparseable event: {name}")
            continue

        events.append({
            "name": name,
            "event_url": event_url,
            "start": start,
            "end": end,
            "format": event_format,
        })

    log(f"Found {len(events)} online events in the listing.")
    return events


# ── Official website and prize extraction ───────────────────────

SOCIAL_DOMAINS = {
    "discord.gg",
    "discord.com",
    "github.com",
    "gitlab.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "t.me",
    "telegram.me",
}


def is_external_url(url):
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False

    host = parsed.netloc.lower().split(":")[0]

    if host == "ctftime.org" or host.endswith(".ctftime.org"):
        return False

    return True


def find_official_url(soup):
    """Prefer links explicitly labelled as the official website."""
    anchors = soup.find_all("a", href=True)

    for anchor in anchors:
        label = " ".join([
            anchor.get_text(" ", strip=True),
            anchor.get("title", ""),
        ]).strip().lower()

        if re.search(r"\b(official )?(event )?website\b|\bhomepage\b", label):
            url = urljoin(CTFTIME_URL, anchor["href"])
            if is_external_url(url):
                return url

    # Fallback: choose an external link that is not obviously social media.
    for anchor in anchors:
        url = urljoin(CTFTIME_URL, anchor["href"])

        if not is_external_url(url):
            continue

        host = urlparse(url).netloc.lower().split(":")[0]

        if not any(
            host == domain or host.endswith("." + domain)
            for domain in SOCIAL_DOMAINS
        ):
            return url

    return "Not listed"


def find_prize_text(soup):
    """
    Search around prize-related labels.
    Returns 'Not listed' if no prize information can be identified.
    """
    for element in soup.find_all(string=re.compile(
        r"\b(prize|prizes|prize pool|rewards)\b",
        re.IGNORECASE,
    )):
        current = element.parent

        # Inspect the label's nearby HTML containers.
        for _ in range(4):
            if not current:
                break

            text = current.get_text(" ", strip=True)

            if text and len(text) <= 500:
                # Avoid returning a giant section of unrelated page text.
                if re.search(
                    r"(?:US\$|\$|USD|EUR|€|GBP|£|INR|₹|MMK|¥)"
                    r"\s*[\d,]+",
                    text,
                    re.IGNORECASE,
                ):
                    return text

            current = current.parent

    return "Not listed"


def convert_usd_prizes(prize_text):
    """Append an approximate MMK conversion for USD amounts."""
    if prize_text == "Not listed":
        return prize_text

    pattern = re.compile(
        r"(US\$|\$|USD\s*)(\d[\d,]*(?:\.\d{1,2})?)",
        re.IGNORECASE,
    )

    def replace_amount(match):
        amount = float(match.group(2).replace(",", ""))
        mmk = round(amount * USD_TO_MMK)
        return f"{match.group(1)}{match.group(2)} (≈ {mmk:,} MMK)"

    return pattern.sub(replace_amount, prize_text)


def scrape_event_details(driver, event):
    safe_get(driver, event["event_url"])

    soup = BeautifulSoup(driver.page_source, "html.parser")

    website = find_official_url(soup)
    prize = convert_usd_prizes(find_prize_text(soup))

    return website, prize


# ── Main ────────────────────────────────────────────────────────

def main():
    now = datetime.now(MMT)
    window_end = now + WINDOW

    print("\nCTFtime Online CTF Finder")
    print(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')} MMT")
    print(f"Window ends:  {window_end.strftime('%Y-%m-%d %H:%M:%S')} MMT")
    print("Fetching upcoming online events...\n")

    options = Options()
    options.add_argument("-headless")
    options.page_load_strategy = "eager"

    driver = None
    results = []

    try:
        log("Starting Firefox WebDriver...")
        driver = webdriver.Firefox(options=options)
        driver.set_page_load_timeout(REQUEST_TIMEOUT)
        log("Firefox started successfully.")

        events = get_online_events(driver)

        # Keep events starting between now and the end of the rolling window.
        matching_events = [
            event for event in events
            if now <= event["start"] <= window_end
        ]

        matching_events.sort(key=lambda event: event["start"])

        print(f"Events starting within 7 days: {len(matching_events)}\n")

        for index, event in enumerate(matching_events, start=1):
            print(
                f"[{index}/{len(matching_events)}] "
                f"Fetching details: {event['name']}",
                flush=True,
            )

            try:
                website, prize = scrape_event_details(driver, event)

                results.append([
                    event["name"],
                    format_date(event["start"], event["end"]),
                    format_duration(event["start"], event["end"]),
                    event["format"],
                    website,
                    prize,
                ])

            except (WebDriverException, ValueError, TypeError) as exc:
                print(f"[WARN] Failed to scrape {event['name']}: {exc}")
                results.append([
                    event["name"],
                    format_date(event["start"], event["end"]),
                    format_duration(event["start"], event["end"]),
                    event["format"],
                    "Fetch failed",
                    "Fetch failed",
                ])

            time.sleep(DETAIL_DELAY)

    except WebDriverException as exc:
        print(f"\n[ERROR] Firefox/WebDriver failed: {exc}", file=sys.stderr)
        print(
            "Check Firefox, geckodriver, network access, "
            "and whether CTFtime is reachable.",
            file=sys.stderr,
        )
        sys.exit(1)

    finally:
        if driver:
            driver.quit()
            log("Firefox closed.")

    if not results:
        print("No matching online CTFs found in the next 7 days.")
        return

    headers = [
        "Name",
        "Date (MMT)",
        "Duration",
        "Format",
        "Official Website",
        "Prize",
    ]

    print(tabulate(results, headers=headers, tablefmt="grid"))


if __name__ == "__main__":
    main()
