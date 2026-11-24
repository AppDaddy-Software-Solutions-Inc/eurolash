#!/usr/bin/env python3
"""Refresh the baked-in Google reviews from the Places API.

The site is a static export, so the original WordPress plugin can no longer
fetch reviews. This script does that job at build time: it calls the Places
API once, rewrites the review slides and the rating/count header in every
page that carries the widget, and leaves the markup otherwise untouched.

Usage:
    set GOOGLE_PLACES_API_KEY=...          (PowerShell: $env:GOOGLE_PLACES_API_KEY="...")
    python tools/refresh-google-reviews.py

    --dry-run       show what would change, write nothing
    --from FILE     read a saved API response instead of calling Google
    --place-id ID   override the place id

Notes:
  * The Places API returns at most 5 reviews. That is a Google limit, not a
    limit of this script.
  * Review avatars are hot-linked to Google, matching what the existing
    header image already does.
"""

import argparse
import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

PLACE_ID = "ChIJ79wVfX-t0kwRcPXdBvkwojI"
ENDPOINT = "https://places.googleapis.com/v1/places/{place_id}"
FIELD_MASK = "id,rating,userRatingCount,reviews"

# Pages carrying the reviews widget, relative to the repo root.
PAGES = [
    "index.html",
    "about-us/index.html",
    "contact-us/index.html",
    "frequently-asked-questions/index.html",
    "kingston-lash-lift/index.html",
    "permanent-makeup-lash-services/index.html",
    "sara-rouhi/index.html",
]

GUEST = "assets/plugins/widget-google-reviews/assets/img/guest.png"
DIV = re.compile(r"<(/?)div[\s>]")


# --------------------------------------------------------------------------- fetch

def fetch(place_id, api_key):
    req = urllib.request.Request(
        ENDPOINT.format(place_id=place_id),
        headers={
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def normalise(payload):
    """Flatten the Places API response into what the markup needs."""
    out = []
    for r in payload.get("reviews", []):
        author = r.get("authorAttribution", {})
        published = r.get("publishTime", "")
        try:
            epoch = int(datetime.fromisoformat(
                published.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            epoch = 0
        out.append({
            "name": author.get("displayName", "A Google user"),
            "url": author.get("uri", ""),
            "photo": author.get("photoUri", ""),
            "rating": r.get("rating", 5),
            "when": r.get("relativePublishTimeDescription", ""),
            "epoch": epoch,
            "text": (r.get("originalText") or r.get("text") or {}).get("text", ""),
        })
    return {
        "rating": payload.get("rating"),
        "total": payload.get("userRatingCount"),
        "reviews": out,
    }


# --------------------------------------------------------------------------- markup

def slide_html(rv, prefix):
    """One review slide, matching the existing plugin markup exactly."""
    name = html.escape(rv["name"], quote=True)
    photo = html.escape(rv["photo"] or f"{prefix}{GUEST}", quote=True)
    guest = f"{prefix}{GUEST}"
    fallback = (f"onerror=\"if(this.src!='{guest}')this.src='{guest}';\"")
    img_attrs = (f'src="{photo}" loading="lazy" alt="{name} profile picture" '
                 f'width="50" height="50" {fallback} ')
    author = (f'<a href="{html.escape(rv["url"], quote=True)}" class="wp-google-name" '
              f'target="_blank" rel="nofollow noopener">{name}</a>'
              if rv["url"] else f'<span class="wp-google-name">{name}</span>')
    return (
        '<div class="rpi-slide grw-review">'
        '<div class="rpi-flx rpi-col12 grw-review-inner grw-backgnd">'
        '<div class="rpi-flx rpi-row12-center">'
        '<div class="grw-img-wrap">'
        f'<img loading="lazy" decoding="async" class="grw-img" {img_attrs}>'
        '</div>'
        '<div class="rpi-flx rpi-col6">'
        f'{author}'
        f'<div class="wp-google-time" data-time="{rv["epoch"]}" data-lang="en">'
        f'{html.escape(rv["when"])}</div>'
        '</div></div>'
        f'<span class="rpi-stars" style="--rating:{rv["rating"]}"></span>'
        '<div class="rpi-flx rpi-col4">'
        '<div class="wp-google-feedback grw-scroll" >'
        f'<span class="wp-google-text">{html.escape(rv["text"])}</span>'
        '</div></div>'
        '<svg height="16" width="16" role="none"><use href="#grw-google"/></svg>'
        '</div></div>'
    )


def match_div(s, start):
    depth, i = 0, start
    while True:
        m = DIV.search(s, i)
        if m is None:
            raise ValueError("unbalanced <div> while scanning slider")
        if m.group(1):
            depth -= 1
            if depth == 0:
                return s.index(">", m.start()) + 1
        else:
            depth += 1
        i = m.start() + 1


def rewrite(page, data):
    """Return (new_source, summary) for one page, or raise on unexpected markup."""
    with open(page, encoding="utf-8", newline="") as fh:
        s = fh.read()

    prefix = "../" * page.count("/")
    changes = []

    # --- the slides -------------------------------------------------------
    m = re.search(r'<div class="rpi-slides grw-reviews[^"]*"[^>]*>', s)
    if not m:
        raise ValueError(f"{page}: slider container not found")
    open_tag, body_start = m.group(0), m.end()
    body_end = match_div(s, m.start()) - len("</div>")

    slides = "".join(slide_html(r, prefix) for r in data["reviews"])
    n = len(data["reviews"])
    new_tag = re.sub(r'data-count="\d+"', f'data-count="{n}"', open_tag)
    new_tag = re.sub(r'data-offset="\d+"', f'data-offset="{n}"', new_tag)
    old_n = len(re.findall(r'<div class="rpi-slide grw-review', s[body_start:body_end]))
    changes.append(f"slides {old_n} -> {n}")
    s = s[:m.start()] + new_tag + slides + s[body_end:]

    # --- rating + total ---------------------------------------------------
    if data["rating"] is not None:
        s, k = re.subn(r'(<span class="rpi-stars" style="--rating:)[\d.]+(">)[\d.]+(</span>)',
                       rf'\g<1>{data["rating"]}\g<2>{data["rating"]}\g<3>', s, count=1)
        if k:
            changes.append(f'rating -> {data["rating"]}')
    if data["total"] is not None:
        s, k = re.subn(r'(<div class="wp-google-based">Based on )\d+( reviews</div>)',
                       rf'\g<1>{data["total"]}\g<2>', s, count=1)
        if k:
            changes.append(f'total -> {data["total"]}')

    return s, ", ".join(changes)


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from", dest="src", help="read a saved JSON response instead of calling Google")
    ap.add_argument("--place-id", default=os.environ.get("GOOGLE_PLACE_ID", PLACE_ID))
    args = ap.parse_args()

    if args.src:
        with open(args.src, encoding="utf-8") as fh:
            payload = json.load(fh)
    else:
        key = os.environ.get("GOOGLE_PLACES_API_KEY")
        if not key:
            sys.exit("GOOGLE_PLACES_API_KEY is not set. See the header of this file.")
        payload = fetch(args.place_id, key)

    data = normalise(payload)
    if not data["reviews"]:
        sys.exit("API returned no reviews - refusing to blank the widget.")

    print(f'{len(data["reviews"])} reviews | rating {data["rating"]} | {data["total"]} total\n')

    for page in PAGES:
        if not os.path.exists(page):
            print(f"  {page:46} SKIPPED (missing)")
            continue
        new, summary = rewrite(page, data)
        if args.dry_run:
            print(f"  {page:46} would update: {summary}")
        else:
            with open(page, "w", encoding="utf-8", newline="") as fh:
                fh.write(new)
            print(f"  {page:46} {summary}")

    if args.dry_run:
        print("\ndry run - nothing written")


if __name__ == "__main__":
    main()
