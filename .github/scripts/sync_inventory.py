#!/usr/bin/env python3
"""Build the LOT ONE ordering catalog from live pricing and warehouse sheets.

The published Website sheet is authoritative for both pricing tiers. R1, R2,
and R3 are authoritative for stock and for which stocked products exist. The
result is embedded into index.html and saved as products.json as a resilient
fallback for browsers that cannot reach Google Sheets directly. Products that
have warehouse stock but no approved price remain visible with pricing pending.
"""
import csv
import json
import re
import sys
import traceback
import urllib.request
from datetime import date, datetime, timezone

PRICING_SHEET_CSV = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRybvOuVrE5eg9eP2KTRqSJ9VAhHFyKM66g83dqvGH7Cub0mpHamUeDpt_ggJq0c7nKcSXn-dJ8n73c"
    "/pub?gid=580555334&single=true&output=csv"
)

WAREHOUSE_SHEETS = {
    "R1": {
        "url": "https://docs.google.com/spreadsheets/d/15kPdQ7bzSdVL5v4iYMGmuP_Ayme-BtFSrf20R_JsjAU/gviz/tq?gid=1000001&tqx=out:csv",
        "stock_column": 1,
    },
    "R2": {
        "url": "https://docs.google.com/spreadsheets/d/1vqh37r9NcGaZaNcbr0_vAntWI3_mOjWuYybfDw8apHs/gviz/tq?gid=733898262&tqx=out:csv",
        "stock_column": 4,
    },
    "R3": {
        "url": "https://docs.google.com/spreadsheets/d/1dmxeL0WGAXvj_dkzOrjF9C7iyRrt4hcvVQ5pkt-WMrI/gviz/tq?gid=733898262&tqx=out:csv",
        "stock_column": 4,
    },
}


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_number(value, default=0):
    cleaned = str(value or "").replace("$", "").replace(",", "").strip()
    if not cleaned:
        return default
    try:
        number = float(cleaned)
    except ValueError:
        return default
    return int(number) if number == int(number) else number


def parse_price(value):
    return parse_number(value, 0)


def canonical_website_name(value):
    """Translate scientific/warehouse names to the site's established labels."""
    name = re.sub(r"\s+", " ", str(value or "").strip())
    patterns = (
        (r"^Retatrutide\s*(\d+(?:\.\d+)?)\s*(?:mg)?$", lambda m: f"R-{m.group(1)}"),
        (r"^R-?(\d+(?:\.\d+)?)$", lambda m: f"R-{m.group(1)}"),
        (r"^Tirzepatide\s*(\d+(?:\.\d+)?)\s*(?:mg)?$", lambda m: f"T-{m.group(1)}"),
        (r"^T-?(\d+(?:\.\d+)?)$", lambda m: f"T-{m.group(1)}"),
        (r"^(?:Tesamorelin|Tesa)\s*(\d+(?:\.\d+)?)\s*(?:mg)?$", lambda m: f"Tesa{m.group(1)}"),
        (r"^(?:Testosterone Cypionate|TestC)\s*(\d+(?:\.\d+)?)\s*(?:mg)?$", lambda m: f"TestC{m.group(1)}"),
        (r"^(?:Testosterone Enanthate|TestE)\s*(\d+(?:\.\d+)?)\s*(?:mg)?$", lambda m: f"TestE{m.group(1)}"),
        (r"^(?:Bacteriostatic Water|Vendor Bac)\s*(\d+(?:\.\d+)?)\s*mL$", lambda m: f"Vendor Bac {m.group(1)}mL"),
        (r"^(?:hCG|HCG|G)\s*(\d+(?:\.\d+)?)\s*K$", lambda m: f"G{m.group(1)}K"),
        (r"^(?:GHK-Cu|GHKCU)\s*(\d+(?:\.\d+)?)\s*(?:mg)?$", lambda m: f"GHKCU{m.group(1)}"),
        (r"^(?:MOTS-C|Mots)\s*(\d+(?:\.\d+)?)\s*(?:mg)?$", lambda m: f"Mots{m.group(1)}"),
        (r"^(?:Melanotan II|MT-?2)\s*(\d+(?:\.\d+)?)\s*(?:mg)?$", lambda m: f"MT-2 {m.group(1)}"),
        (r"^(?:Thymosin Alpha-1|TA-?1)\s*(\d+(?:\.\d+)?)\s*(?:mg)?$", lambda m: f"TA-1 {m.group(1)}"),
        (r"^(?:Epithalon|Epitalon)\s*(\d+(?:\.\d+)?)\s*(?:mg)?$", lambda m: f"Epitalon {m.group(1)}"),
        (r"^(?:TB-?500|BT)\s*(\d+(?:\.\d+)?)\s*(?:mg)?$", lambda m: f"BT{m.group(1)}"),
        (r"^(?:Bacteriostatic Water|Vendor Bac)\s*30\s*mL(?:\s*\(Hospira\))?$", lambda m: "Vendor Bac 30mL"),
        (r"^KLOW\s*(\d+(?:\.\d+)?)\s*(?:mg)?$", lambda m: f"Klow {m.group(1)}"),
    )
    for pattern, replacement in patterns:
        match = re.match(pattern, name, re.I)
        if match:
            return replacement(match)
    if re.match(r"^CJC \(no DAC\)/IPA\b", name, re.I):
        return name
    name = re.sub(r"\s+(mg|IU)$", "", name, flags=re.I)
    return re.sub(r"^Wolverine Peptide\b", "Wolverine", name, flags=re.I)


def product_key(value):
    return re.sub(r"[^a-z0-9]+", "", canonical_website_name(value).lower())


def js_escape(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fetch_csv(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 LOT-ONE-inventory-sync/2.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8-sig")


def read_warehouse(name, config):
    rows = list(csv.reader(fetch_csv(config["url"]).splitlines()))
    stock = {}
    names = {}
    for row in rows[1:]:
        if not row:
            continue
        product_name = (row[0] or "").strip()
        if not product_name or re.match(r"^total\b", product_name, re.I):
            continue
        quantity = parse_number(row[config["stock_column"]] if len(row) > config["stock_column"] else 0)
        canonical_name = canonical_website_name(product_name)
        key = product_key(canonical_name)
        stock[key] = stock.get(key, 0) + max(0, int(quantity))
        names.setdefault(key, canonical_name)
    print(f"{name}: {len(stock)} warehouse products")
    return stock, names


def build_products():
    pricing_rows = list(csv.DictReader(fetch_csv(PRICING_SHEET_CSV).splitlines()))
    warehouse_data = {name: read_warehouse(name, config) for name, config in WAREHOUSE_SHEETS.items()}
    warehouse_stock = {name: data[0] for name, data in warehouse_data.items()}
    warehouse_names = {name: data[1] for name, data in warehouse_data.items()}
    pricing = {}
    for row in pricing_rows:
        raw_name = (row.get("Item Name") or "").strip()
        if not raw_name:
            continue
        name = canonical_website_name(raw_name)
        pricing[product_key(name)] = {
            "name": name,
            "price": parse_price(row.get("Retail Price")),
            "homiePrice": parse_price(row.get("Homie Price")),
            "fallbackStock": max(0, int(parse_number(row.get("Stock"), 0))),
        }

    all_keys = set(pricing)
    for stock in warehouse_stock.values():
        all_keys.update(stock)
    products = []
    for key in sorted(all_keys):
        priced = pricing.get(key, {})
        name = priced.get("name")
        if not name:
            for warehouse in WAREHOUSE_SHEETS:
                name = warehouse_names[warehouse].get(key)
                if name:
                    break
        if not name:
            continue
        locations = {warehouse: int(warehouse_stock[warehouse].get(key, 0)) for warehouse in WAREHOUSE_SHEETS}
        found_in_any_warehouse = any(key in warehouse_stock[warehouse] for warehouse in WAREHOUSE_SHEETS)
        if not found_in_any_warehouse and priced:
            locations["R1"] = priced["fallbackStock"]
        products.append({
            "id": slugify(name),
            "name": name,
            "price": priced.get("price", 0),
            "homiePrice": priced.get("homiePrice", 0),
            "stock": sum(locations.values()),
            "warehouses": locations,
        })
    if not products:
        raise RuntimeError("No priced products were parsed; refusing to replace the catalog")
    return products


def products_js(products):
    lines = ["var products = ["]
    for index, product in enumerate(products):
        comma = "," if index < len(products) - 1 else ""
        warehouses = json.dumps(product["warehouses"], separators=(",", ":"))
        lines.append(
            f'        {{ id: "{product["id"]}", name: "{js_escape(product["name"])}", '
            f'price: {product["price"]}, homiePrice: {product["homiePrice"]}, '
            f'stock: {product["stock"]}, warehouses: {warehouses} }}{comma}'
        )
    lines.append("      ];")
    return "\n".join(lines)


def replace_products_block(html, replacement):
    start_match = re.search(r"var products = \[", html)
    if not start_match:
        raise RuntimeError("products array not found")
    array_start = html.find("[", start_match.start())
    depth = 0
    for index in range(array_start, len(html)):
        if html[index] == "[":
            depth += 1
        elif html[index] == "]":
            depth -= 1
            if depth == 0:
                end = index + 1
                if html[end : end + 1] == ";":
                    end += 1
                return html[: start_match.start()] + replacement + html[end:]
    raise RuntimeError("could not find end of products array")


def main():
    print("Fetching pricing and R1/R2/R3 inventory sheets...")
    try:
        products = build_products()
    except Exception as error:
        print(f"Live catalog fetch failed: {error}", file=sys.stderr)
        traceback.print_exc()
        return 1
    with open("index.html", encoding="utf-8") as source:
        html = source.read()
    html = replace_products_block(html, products_js(products))
    today = date.today().strftime("%B %d, %Y").replace(" 0", " ")
    html = re.sub(r"Inventory updated [A-Za-z]+ \d{1,2}, \d{4}", f"Inventory updated {today}", html)
    with open("index.html", "w", encoding="utf-8") as output:
        output.write(html)
    payload = {"updatedAt": datetime.now(timezone.utc).isoformat(), "products": products}
    with open("products.json", "w", encoding="utf-8") as output:
        json.dump(payload, output, indent=2)
        output.write("\n")
    priced_count = sum(1 for item in products if item["price"] > 0)
    print(f"SYNC OK: {len(products)} products ({priced_count} priced), {sum(item['stock'] for item in products)} units")
    return 0


if __name__ == "__main__":
    sys.exit(main())
