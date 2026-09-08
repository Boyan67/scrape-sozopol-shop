"""
Pulls the latest snapshot.json from the repo and opens a readable HTML report
of all currently tracked listings in your default browser.

Run manually:  python view_listings.py
"""
import json
import subprocess
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT_PATH = HERE / "snapshot.json"
REPORT_PATH = HERE / "report.html"

SOURCE_COLORS = {
    "imot.bg": "#1d4ed8",
    "alo.bg": "#b45309",
    "bazar.bg": "#15803d",
}


def render_row(key: str, l: dict) -> str:
    color = SOURCE_COLORS.get(l["source"], "#111827")
    return f"""
    <tr>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">
        <span style="background:{color};color:#fff;font-size:10px;font-weight:800;
                     padding:2px 7px;border-radius:5px;letter-spacing:.03em;">
          {l['source'].upper()}
        </span>
      </td>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;font-weight:700;">{l['price']}</td>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">{l['location']}</td>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;font-size:13px;color:#374151;">{l['info']}</td>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;">
        <a href="{l['url']}" target="_blank" style="color:#1d4ed8;font-weight:600;">Open &rarr;</a>
      </td>
    </tr>
    """


def main() -> None:
    try:
        subprocess.run(["git", "pull"], cwd=HERE, check=True)
    except Exception as e:
        print(f"git pull failed ({e}), showing local snapshot instead.")

    data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    items = sorted(data.items(), key=lambda kv: kv[1]["source"])

    rows = "".join(render_row(k, l) for k, l in items)

    html = f"""
    <html><head><meta charset="utf-8"><title>Sozopol Shop Listings</title></head>
    <body style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f3f4f6;padding:24px;">
      <div style="max-width:1400px;margin:0 auto;">
        <h2 style="margin:0 0 4px 0;">Sozopol Shop/Office Rentals</h2>
        <div style="color:#6b7280;font-size:13px;margin-bottom:16px;">{len(items)} listings currently tracked</div>
        <table style="width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1);">
          <tr style="background:#111827;color:#fff;text-align:left;">
            <th style="padding:10px 12px;">Source</th>
            <th style="padding:10px 12px;">Price</th>
            <th style="padding:10px 12px;">Location</th>
            <th style="padding:10px 12px;">Details</th>
            <th style="padding:10px 12px;">Link</th>
          </tr>
          {rows}
        </table>
      </div>
    </body></html>
    """

    REPORT_PATH.write_text(html, encoding="utf-8")
    webbrowser.open(REPORT_PATH.as_uri())
    print(f"Opened {REPORT_PATH} with {len(items)} listings.")


if __name__ == "__main__":
    main()
