"""
Daily watcher for new shop-rental listings in Sozopol, across multiple sites.
Scrapes each configured source, compares against the last saved snapshot,
and emails (via Resend) a combined daily digest.

Run manually:  python watch_sozopol.py
Scheduled via GitHub Actions (see .github/workflows/watch.yml).
"""
import json
import os
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
SNAPSHOT_PATH = HERE / "snapshot.json"
LOG_PATH = HERE / "run.log"

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
FROM_EMAIL = "onboarding@resend.dev"
TO_EMAIL = "boyanyonkov01@gmail.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def log(msg: str) -> None:
    print(msg)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def fetch_imotbg() -> dict:
    url = "https://www.imot.bg/obiavi/naemi/oblast-burgas/gr-sozopol/magazin?type_home=14~"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "windows-1251"
    soup = BeautifulSoup(resp.text, "html.parser")

    listings = {}
    for item in soup.select("div.item"):
        item_id = item.get("id", "")
        if not item_id.startswith("ida"):
            continue
        raw_id = item_id[len("ida"):]
        key = f"imotbg:{raw_id}"

        title_a = item.select_one("a.title")
        listing_url = (
            "https:" + title_a["href"]
            if title_a and title_a["href"].startswith("//")
            else (title_a["href"] if title_a else "")
        )
        location_tag = title_a.select_one("location") if title_a else None
        location = location_tag.get_text(strip=True) if location_tag else ""

        price_tag = item.select_one("div.price div")
        price = price_tag.get_text(strip=True) if price_tag else ""

        info_tag = item.select_one("div.info")
        info = info_tag.get_text(strip=True) if info_tag else ""

        listings[key] = {
            "source": "imot.bg",
            "url": listing_url,
            "location": location,
            "price": price,
            "info": info,
        }
    return listings


def fetch_alobg() -> dict:
    url = "https://www.alo.bg/obiavi/imoti-naemi/magazini-ofisi/?region_id=2&location_ids=490"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    listings = {}
    for item in soup.select("div.listvip-item"):
        item_id = item.get("id", "")
        if not item_id.startswith("adrows_"):
            continue
        raw_id = item_id[len("adrows_"):]
        key = f"alobg:{raw_id}"

        title_a = item.select_one(".listvip-item-title")
        title = title_a.get_text(strip=True) if title_a else ""
        link_a = item.select_one("a[href^='/']")
        listing_url = (
            "https://www.alo.bg" + link_a["href"] if link_a else ""
        )

        address_tag = item.select_one(".listvip-item-address")
        location = address_tag.get_text(strip=True) if address_tag else ""

        price_tag = item.select_one(".price_nowrap")
        price = price_tag.get_text(strip=True) if price_tag else ""

        content_tag = item.select_one(".listvip-item-content")
        info = ""
        if content_tag:
            desc = content_tag.select_one(".listvip-desc")
            params = [
                s.get_text(strip=True)
                for s in content_tag.select(".ads-params-multi")
                if "Месечен наем" not in s.get("title", "")
            ]
            info = ", ".join(params)
            if desc:
                info = (info + " — " + desc.get_text(strip=True)) if info else desc.get_text(strip=True)

        listings[key] = {
            "source": "alo.bg",
            "url": listing_url,
            "location": location or title,
            "price": price,
            "info": info,
        }
    return listings


def fetch_bazarbg() -> dict:
    # NOTE: bazar.bg auto-appends a "Обяви за 'Бизнес имоти' от Бургас" section of
    # unrelated Burgas-wide listings below the real Sozopol results. Scoping to the
    # unique #dataContainer id excludes that section entirely.
    url = "https://bazar.bg/obiavi/naemi-biznes-imoti/sozopol"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    listings = {}
    container = soup.select_one("#dataContainer")
    if not container:
        return listings

    for item in container.select(".listItemContainer"):
        link_a = item.select_one("a.listItemLink")
        if not link_a:
            continue
        raw_id = link_a.get("data-id", "")
        if not raw_id:
            continue
        key = f"bazarbg:{raw_id}"

        listing_url = link_a.get("href", "")

        location_tag = item.select_one(".location")
        location = location_tag.get_text(strip=True) if location_tag else ""

        price_tag = item.select_one(".price")
        price = price_tag.get_text(strip=True) if price_tag else ""

        title_tag = item.select_one("span.title")
        info = title_tag.get_text(strip=True) if title_tag else ""

        listings[key] = {
            "source": "bazar.bg",
            "url": listing_url,
            "location": location,
            "price": price,
            "info": info,
        }
    return listings


SOURCES = [fetch_imotbg, fetch_alobg, fetch_bazarbg]


def fetch_all_listings() -> dict:
    combined = {}
    for fetch_fn in SOURCES:
        try:
            combined.update(fetch_fn())
        except Exception as e:
            log(f"Source {fetch_fn.__name__} FAILED: {e}")
    return combined


def load_snapshot() -> dict:
    if not SNAPSHOT_PATH.exists():
        return {}
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        return {}
    return json.loads(content)


def save_snapshot(data: dict) -> None:
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def render_card(l: dict, badge: str = "") -> str:
    badge_html = (
        f"<span style='background:#15803d;color:#fff;font-size:11px;font-weight:800;"
        f"padding:2px 8px;border-radius:999px;margin-left:8px;vertical-align:middle;'>{badge}</span>"
        if badge else ""
    )
    source_html = (
        f"<span style='background:#111827;color:#fff;font-size:10px;font-weight:800;"
        f"padding:2px 7px;border-radius:5px;margin-left:8px;vertical-align:middle;"
        f"letter-spacing:.03em;'>{l['source'].upper()}</span>"
    )
    return f"""
    <tr>
      <td style="padding:0 0 14px 0;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border:2px solid #9ca3af;border-radius:10px;overflow:hidden;">
          <tr>
            <td style="padding:16px 18px;">
              <div style="font-size:16px;font-weight:800;color:#000000;">
                {l['price']}{badge_html}{source_html}
              </div>
              <div style="font-size:13px;font-weight:600;color:#1f2937;margin-top:4px;">
                {l['location']}
              </div>
              <div style="font-size:13px;color:#111827;margin-top:10px;line-height:1.5;">
                {l['info']}
              </div>
              <div style="margin-top:12px;">
                <a href="{l['url']}"
                   style="display:inline-block;background:#1d4ed8;color:#ffffff;
                          text-decoration:none;font-size:13px;font-weight:700;
                          padding:8px 14px;border-radius:6px;border:1px solid #1e3a8a;">
                  View listing &rarr;
                </a>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
    """


def build_email_html(new_listings: list, total_count: int) -> str:
    if new_listings:
        headline = f"{len(new_listings)} new listing{'s' if len(new_listings) != 1 else ''} found"
        headline_color = "#15803d"
        cards = "".join(render_card(l, badge="NEW") for l in new_listings)
    else:
        headline = "No new listings today"
        headline_color = "#111827"
        cards = """
        <tr><td style="padding:24px 18px;background:#ffffff;border:2px solid #9ca3af;
                        border-radius:10px;text-align:center;color:#1f2937;font-size:13px;font-weight:600;">
              Nothing new since yesterday. Everything's quiet.
            </td></tr>
        """

    today = __import__("datetime").date.today().strftime("%A, %d %B %Y")

    return f"""
    <div style="background:#e5e7eb;padding:24px 0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td align="center">
            <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:560px;max-width:92%;">
              <tr>
                <td style="padding:4px 4px 18px 4px;">
                  <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#374151;font-weight:700;">
                    Sozopol Shop Watch
                  </div>
                  <div style="font-size:22px;font-weight:800;color:{headline_color};margin-top:4px;">
                    {headline}
                  </div>
                  <div style="font-size:12px;color:#374151;font-weight:600;margin-top:2px;">
                    {today} &middot; {total_count} total listing{'s' if total_count != 1 else ''} tracked
                  </div>
                </td>
              </tr>
              {cards}
              <tr>
                <td style="padding:16px 4px 0 4px;text-align:center;font-size:11px;color:#4b5563;font-weight:600;">
                  Watching imot.bg, alo.bg and bazar.bg for shop rentals in Sozopol &middot; runs daily
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </div>
    """


def send_email(new_listings: list, total_count: int) -> bool:
    html = build_email_html(new_listings, total_count)
    if new_listings:
        subject = f"🟢 {len(new_listings)} new shop listing(s) in Sozopol"
    else:
        subject = "⚪ Sozopol shop watch: no new listings today"

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": FROM_EMAIL,
            "to": TO_EMAIL,
            "subject": subject,
            "html": html,
        },
        timeout=30,
    )
    if resp.status_code >= 300:
        log(f"Email send FAILED: {resp.status_code} {resp.text}")
        return False
    log(f"Email sent OK: {resp.status_code}")
    return True


def main() -> int:
    log(f"\n=== Run at {__import__('datetime').datetime.now().isoformat()} ===")
    current = fetch_all_listings()

    if not current:
        log("FETCH FAILED: no listings from any source.")
        return 1

    log(f"Found {len(current)} current listings across {len(SOURCES)} source(s).")

    previous = load_snapshot()

    if not previous:
        save_snapshot(current)
        log("First run: baseline snapshot saved.")
        send_email([], len(current))
        return 0

    new_ids = [i for i in current if i not in previous]
    new_listings = [current[i] for i in new_ids]

    if new_listings:
        log(f"New listings: {len(new_listings)} -> {new_ids}")
    else:
        log("No new listings.")

    send_email(new_listings, len(current))

    if current != previous:
        save_snapshot(current)
        log("Snapshot updated.")
    else:
        log("Snapshot unchanged.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
