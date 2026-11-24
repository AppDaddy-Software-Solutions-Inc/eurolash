# Eurolash — static rebuild

A plain HTML/CSS/JS copy of eurolash.ca. No WordPress, no PHP, no database — every
file here is served as-is by any static web server.

## Layout

```
index.html                  home page
<page-slug>/index.html      one folder per page, so URLs stay /about-us/ etc.
blogs/index.html            blog listing page 1
blogs/2/index.html          blog listing page 2
category/<slug>/            category archives
author/<slug>/              author archives
404.html                    not-found page (wired up in web.config)
assets/                     was wp-content/ — theme + plugin CSS/JS, images, fonts, video
lib/                        was wp-includes/ — jQuery and a few core scripts
web.config                  IIS: default document, MIME types, 404 handler, compression
```

40 HTML pages, 448 assets, 27 MB.

`assets/plugins/elementor*/assets/js/*.bundle.min.js` are Elementor's webpack
chunks. Nothing in the HTML links to them — Elementor's runtime fetches them on
demand — so they were collected by reading the chunk map out of
`webpack.runtime.min.js`. They are what drive the background videos, toggles,
carousels and nav menu; do not prune them as "unreferenced".

## What was removed

Only WordPress plumbing that produced no visible output:

- REST API (`wp-json`), RSD/XML-RPC, shortlink and oEmbed discovery `<link>` tags
- RSS/comment feed links
- `<meta name="generator">`
- the emoji-detection script (`_wpemojiSettings`) and its CDN fallback
- the GoDaddy `wsimg.com` traffic-analytics script
- a broken `<link rel="preload" href="your-image-url">` left in the original theme

Everything that affects appearance or behaviour was kept: the Astra theme CSS,
all Elementor and Elementor Pro CSS/JS, Essential Addons, the lazy-loader, the
Google-reviews widget markup, all animations (entrance, motion-fx, sticky header,
hover transitions), the header background video, and every web font the pages
actually render.

## Performance pass

A later pass cut the site from 41 MB to 27 MB on disk and roughly a third off
what a visitor downloads, without changing how any page looks. Measured with
headless Chrome against a gzipping server, 31 pages, cold cache:

| | before | after |
|---|---|---|
| all 31 pages | 36.8 MB | 25.8 MB |
| pages without the header video | 20.2 MB | 12.6 MB (−37%) |
| a blog listing page (`/blogs/2/`) | 2629 KB | 480 KB (−82%) |
| an article page | 1586 KB | 648 KB (−59%) |

What was done, in order of what it saved:

- **PNG photographs re-encoded as WebP** (−12.6 MB). 34 of the uploads were
  photographs stored as PNG, several as dithered 256-colour palette images,
  which is why one was 4.2 MB. Dimensions are unchanged, so `srcset` width
  descriptors and `width`/`height` attributes stayed valid; every reference in
  the HTML and CSS was repointed. Transparent images (the logo) use lossless
  WebP and are bit-exact; photographs use the lowest quality that stays above
  38 dB PSNR against the original.
- **Dead stylesheets deleted** (−223 KB per page). The Gutenberg block library,
  the block-editor components CSS and the GoDaddy Launch CSS were linked on
  every page. The site is built entirely in Elementor: of their combined 774
  class names, none appear in any page's markup.
- **Audio track stripped from the header video** (−738 KB). It is a `muted`,
  `role="presentation"` background video, so the 128 kbps AAC track was never
  audible. The video stream was copied through untouched, not re-encoded — at
  389 kbps VP9 it is already efficient, and test re-encodes came out larger.
- **Non-Latin font subsets dropped** (−94 KB of CSS, −476 KB of fonts). The
  Google font CSS declared 162 `@font-face` blocks per family covering
  Cyrillic, Greek, Vietnamese, math and symbol ranges. The page text contains
  no characters in those ranges, so those blocks could never match; the Latin
  ones are untouched.
- **Honest `sizes` attributes** on 71 images. WordPress emits
  `sizes="(max-width: 1707px) 100vw, 1707px"` for an image actually painted
  505px wide, so browsers picked the largest candidate. Each image's real
  painted width was measured in a browser at 390/768/1024/1440/2560px and
  written back with 6% headroom, so the browser now picks the smallest
  candidate that is still sharp — including on 2x-DPR screens, which it
  accounts for itself.
- **Cache headers** (`web.config`). A typical page is 309 KB, of which only the
  ~22 KB of HTML is unique — the other ~287 KB of fonts, scripts and
  stylesheets is identical on every page. There was no expiry header at all, so
  each navigation revalidated all ~50 files. They are now cached for 30 days,
  which makes the second and later page views nearly free.
- **Unreferenced files deleted** (−0.5 MB): `assets/ext/` (a stale mirror of
  Google/Gravatar review avatars — the widget loads them from Google directly),
  the two leftover `wp-emoji` scripts, and three unused uploads.

Verified by screenshotting all 40 pages at 1440px and 390px against a copy of
the pre-optimisation site, with animations, carousels and video frozen so the
comparison is deterministic. 40 of 62 screenshots are pixel-identical; every
remaining difference was inspected and is one of: the Google reviews carousel
resting at a different scroll offset, the Google Maps iframe loading at a
different moment, the header video painting *sooner* than before, or WebP
re-encoding differing imperceptibly on photographic texture (peak difference
45/255 on isolated pixels of a skin close-up).

Deliberately **not** done:

- The header video is still 2.17 MB and is 61% of the home page — and 68% of it
  on a phone, where it is downloaded in full. Not playing it on small screens
  would be the single biggest remaining win, but that is a design decision, not
  a lossless optimisation, so it was left alone.
- The ~50 stylesheets were not concatenated. They are shared byte-for-byte
  across all 40 pages, so with the new cache headers keeping them separate is
  better for anyone visiting more than one page.
- The inline `<style>` blocks (95 KB, identical on every page) were not
  extracted to a shared file: they are interleaved with the `<link>` tags, so
  moving them would reorder the cascade.

## Known limitations

These needed a server-side WordPress to work and are now inert:

- **Contact form** (`/contact-us/`) — the markup is unchanged and renders identically,
  but submitting does nothing. Point the `<form>` at a form service (Formspree,
  Netlify Forms, an Azure Function, etc.) to make it live again.
- **Search boxes** in the off-canvas menu — same reason. Remove them, or wire them
  to a static search index or a Google site-search URL.
- **Blog "load more"** — the pagination links between `/blogs/` and `/blogs/2/`
  work; the infinite-scroll variant does not.

Two inline Elementor JS config values still name the old domain
(`admin-ajax.php` and the REST root). Nothing calls them; they were left in place
because editing Elementor's config object risks breaking its frontend scripts.

## Deploying

Copy the whole folder to the web root and serve it. On IIS the included
`web.config` sets `index.html` as the default document, registers MIME types
for `.webp`, `.woff2` and `.mp4`, and caches `assets/` and `lib/` for 30 days
while leaving HTML revalidated.

Because those filenames are not content-hashed, a cached asset is only replaced
when it expires. After swapping an image or stylesheet, either rename the file
or wait out the window.

`web.config` deliberately does not configure `<httpCompression>`: IIS locks
that section at machine level by default, and setting it in a site's web.config
produces a 500.19. Static compression is requested via `<urlCompression>`; if
CSS and JS arrive uncompressed, add `text/css` and `application/javascript` to
the server-level compression MIME types in `applicationHost.config`.

On a non-IIS host, reproduce three things: `index.html` as the directory index,
gzip or brotli for HTML/CSS/JS/SVG, and a long `Cache-Control: max-age` on
`/assets/` and `/lib/` only.

Canonical tags, Open Graph tags and the JSON-LD structured data still point at
`https://eurolash.ca/` — correct if this replaces that site, but they need
updating if it is served from a different domain.
