# AGENTS.md — LOT ONE ordering site

Instructions for AI coding assistants (Claude, ChatGPT/Codex, Cursor, GitHub Copilot, Gemini, Windsurf, etc.) and human contributors editing this project.

## What this is

A single-page order form for **LOT ONE** (live at https://lot-one.org, hosted on Netlify). Customers browse single vials, pick quantities, enter contact/delivery/payment details, upload a payment screenshot, and submit. The order is emailed to the owner.

## Project layout

```
index.html          The entire site: HTML, CSS (<style> in <head>) and JS (<script> at the end of <body>)
favicon.ico         Multi-size browser/bookmark icon
icons/              PNG icons (32px favicon, 180px apple-touch, 192/512px for the manifest)
site.webmanifest    Web app manifest (name, icons, theme colors)
AGENTS.md           This file
```

There is **no build step, no framework, no package.json**. Netlify publishes the repository root as static files. Do not add a bundler, framework or dependencies unless the owner explicitly asks for it.

## How the page works (in `index.html`)

- **Products** — the `products` array near the top of the `<script>` is the fallback catalog (`id`, `name`, `price`, `homiePrice`, `stock`, `warehouses`). On load, the page fetches the published pricing sheet plus the R1, R2, and R3 inventory sheets, keeps the website's established short product names, and replaces the fallback if all four reads succeed. The pricing sheet controls the orderable catalog and price tiers; warehouse sheets control stock. `.github/scripts/sync_inventory.py` refreshes the embedded fallback and `products.json` on schedule.
- **Coupon** — entering the discount code (see the coupon handler around `couponCode.value`) switches prices from `price` to `homiePrice`. The selected tier is sent in the hidden `pricing_tier` field.
- **Order submission** — the `<form id="orderForm">` posts (multipart, with the payment proof image) to FormSubmit (`action="https://formsubmit.co/..."`). JS fills the hidden fields `order_number`, `order_items` and `order_total` before submit, then shows the `#confirmation` panel.
- **Delivery** — "Shipping" shows the `#addressPanel` and makes the address fields required; "Local Pickup" hides it.
- **Payment** — Zelle, Cash App and Venmo radio options, each with the handle in its `value`.

Keep existing element `id`s and form field `name`s unless you update every reference — the JS and the order emails depend on them.

## Design system

Neon "electric blue on near-black" style matching the L1 logo. Use the CSS custom properties defined at the top of the `<style>` block (`:root`) rather than hard-coding colors:

- Colors: `--bg`, `--surface`, `--ink`, `--muted`, `--line`, `--line-bright`, `--accent`, `--accent-strong`, `--accent-electric`, `--accent-soft`, `--danger`, `--warning`, `--success`
- Effects: `--glow`, `--glow-soft`, `--shadow`
- Fonts: `--display` ("Exo 2", bold italic for headings) and DM Sans for body text, loaded from Google Fonts

Rules to preserve:

- Every animation must be disabled under `@media (prefers-reduced-motion: reduce)`.
- The `[hidden] { display: none !important; }` rule must stay so hidden panels stay hidden.
- Layout must work on mobile (the majority of visitors) as well as desktop.
- Keep the page lightweight — compress and resize any new images instead of embedding large base64 data.

## Editing guidelines

- Make small, focused edits to `index.html`; don't rewrite the whole file.
- Match the existing code style: vanilla ES5-style JavaScript (`var`, `function`), no external JS libraries.
- Escape any user- or sheet-provided text before inserting it as HTML (use the existing `escapeHtml()`).
- Don't change the payment handles, the FormSubmit email address, the Google Sheet URLs or the coupon code unless the owner asks.
- Never commit secrets, API keys or passwords.

## Testing

Open `index.html` in a browser, or run `netlify dev` from the repo root to preview. Check: products load, search and stock filters work, the coupon switches prices, the delivery choice toggles the address section, and the form validates required fields.

## Deploying

Pushing to the `main` branch deploys to production on Netlify automatically.
