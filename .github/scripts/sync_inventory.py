#!/usr/bin/env python3
"""Sync LOT ONE inventory from the published Google Sheet into index.html.

Reads the public Website tab CSV, rebuilds the `var products = [...]` block
in index.html, refreshes the inventory date label, and writes products.json.
Exits non-zero (without touching anything) if the sheet can't be read or the
products block can't be found.
"""
import csv
import json
import re
import sys
import traceback
import urllib.request
from datetime import date

SHEET_CSV = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRybvOuVrE5eg9eP2KTRqSJ9VAhHFyKM66g83dqvGH7Cub0mpHamUeDpt_ggJq0c7nKcSXn-dJ8n73c"
    "/pub?gid=580555334&single=true&output=csv"
)


def slugify(name):
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def parse_price(v):
    v = (v or "").replace("$", "").replace(",", "").strip() or "0"
    f = float(v)
    return int(f) if f == int(f) else f


def js_escape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def fetch_csv():
    """Fetch the sheet CSV, following redirects, with a browser UA."""
    req = urllib.request.Request(
        SHEET_CSV,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8-sig")


def main():
    print("Step 1: fetching sheet CSV...")
    try:
        text = fetch_csv()
    except Exception as e:
        print(f"Sheet fetch failed: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1
    print(f"Step 1 done: {len(text)} chars fetched")
    print(f"Preview: {text[:80]!r}")

    rows = list(csv.DictReader(text.splitlines()))
    print(f"Step 2: parsed {len(rows)} CSV rows")
    products = []
    for row in rows:
        name = (row.get("Item Name") or "").strip()
        if not name:
            continue
        try:
            stock = int(float((row.get("Stock") or "0").strip() or 0))
        except ValueError:
            stock = 0
        products.append(
            {
                "id": slugify(name),
                "name": name,
                "price": parse_price(row.get("Retail Price")),
                "homiePrice": parse_price(row.get("Homie Price")),
                "stock": stock,
            }
        )

    if not products:
        print("No products parsed, aborting", file=sys.stderr)
        print(f"CSV header was: {text.splitlines()[0] if text else '(empty)'}", file=sys.stderr)
        return 1
    print(f"Step 2 done: {len(products)} products")

    lines = ["var products = ["]
    for i, p in enumerate(products):
        comma = "," if i < len(products) - 1 else ""
        lines.append(
            f'        {{ id: "{p["id"]}", name: "{js_escape(p["name"])}", '
            f'price: {p["price"]}, homiePrice: {p["homiePrice"]}, stock: {p["stock"]} }}{comma}'
        )
    lines.append("      ];")
    new_block = "\n".join(lines)

    print("Step 3: patching index.html...")
    try:
        with open("index.html", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        print("index.html not found", file=sys.stderr)
        return 1
    print(f"Step 3: index.html is {len(html)} chars")

    m = re.search(r"var products = \[", html)
    if not m:
        print("products array not found, aborting", file=sys.stderr)
        return 1
    i = html.find("[", m.start())
    depth = 0
    end = None
    for j in range(i, len(html)):
        if html[j] == "[":
            depth += 1
        elif html[j] == "]":
            depth -= 1
            if depth == 0:
                k = j + 1
                if html[k : k + 1] == ";":
                    k += 1
                end = k
                break
    if end is None:
        print("could not find end of products array", file=sys.stderr)
        return 1

    old_block = html[m.start() : end]
    if old_block != new_block:
        html = html[: m.start()] + new_block + html[end:]
        today = date.today().strftime("%B %-d, %Y")
        html, n = re.subn(
            r"Inventory updated [A-Za-z]+ \d{1,2}, \d{4}",
            f"Inventory updated {today}",
            html,
        )
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Step 3 done: updated {len(products)} products (date: {n} replacement(s))")
    else:
        print("Step 3 done: no product changes")

    with open("products.json", "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2)
    print("Step 4 done: wrote products.json")
    print("SYNC OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
