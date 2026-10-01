# Sources

Inspection notes for every source in CLAUDE.md §4. An adapter may only be written for a source
whose status is **Cleared**. Everything here was observed on the live sites through the
project's own polite client (`mbd inspect`), identifying itself as
`CanadaHalalDirectoryBot/1.0`.

Last inspected: **2026-10-01**

## Summary

| source_id | Source | Status | Why |
|---|---|---|---|
| `hma_*` | Halal Monitoring Authority (HMA) Canada | **Cleared** | robots.txt allows the listing pages, no terms page forbids reuse, pages are server-rendered |
| `hicc_bc` | HIC Canada (BC Muslim Association) | **Cleared** | robots.txt allows `/certified/`, no terms page, one server-rendered page |
| `osm_overpass` | OpenStreetMap via Overpass API | **Decision needed** | main instance's robots.txt disallows `/api/`; the two mirrors tried did not respond |
| `jaffari_dir` | Jaffari Business Directory (ISIJ of Toronto) | **Permission required** | Terms forbid republishing or redistributing site material without written permission |
| `hmca` | Halal Montreal Certification Authority | **Not available** | no public client list; the site answers our bot with HTTP 403 |
| — | Ontario Muslim Chamber of Commerce | **Not available** | no public member directory |
| — | Commercial directory apps and review sites | **Do not scrape** | partnership / API request only |

Fixtures saved from the cleared sources are in `scraper/tests/fixtures/<name>/`. Pages that
contain personal data, or that come from a source whose terms forbid redistribution, are kept
only in the gitignored `data/raw/` archive and are not committed.

---

## `hma_*` — Halal Monitoring Authority (HMA) Canada

**Status: Cleared.** Type: certifier. Trust rank 1.

### Where the data lives

Everything is on **`https://hmacanada.org`**. The older hostnames in the spec,
`hma.hmacanada.org` and `new.hmacanada.org`, no longer complete a TLS handshake
(`TLSV1_ALERT_INTERNAL_ERROR`), so they cannot be fetched at all. Old URLs on those hosts must
still be canonicalized to `hmacanada.org` + path before being used as `source_record_key`.

| Section | Index page | Detail pages | Count seen |
|---|---|---|---|
| Certified stores | `/hma-certified-stores/` | `/hma-certified-stores/<slug>/` | 22 |
| Certified restaurants | `/hma-certified-restaurants/` | `/hma-certified-restaurants/<slug>/` | 77 linked (79 in sitemap) |
| Processed meat & deli | `/hma-processed-meat-deli-products/` | `/hma-processed-meat-deli-products/<slug>/` | 18 |
| Non-meat products | `/non-meat-products/` | `/non-meat-products/<slug>/` | 42 |
| Home-based businesses | `/home-businesses/` | `/home-businesses/<slug>/` | 2 |
| Suppliers | `/hma-certified-suppliers/` | none (one table on the page) | — |

`/certified-outlets/` is a hub page linking to the sections above.
`/hma-certified-suppliers-2/` exists in the sitemap but has no content; ignore it.
`https://hmacanada.org/page-sitemap.xml` lists every detail page and is a second way to
discover them.

### robots.txt and terms

- `https://hmacanada.org/robots.txt` disallows only `/wp-admin/`, WooCommerce upload folders
  and `add-to-cart` URLs. All listing and detail paths are allowed. No `Crawl-delay`.
- No Terms of Service, terms-of-use or privacy page was found in the footer or in the 243-URL
  page sitemap.

### Page structure

- WordPress + Elementor, fully server-rendered. No JavaScript rendering needed, so no
  Playwright.
- Index pages link to every detail page (stores and restaurants grouped by city, the others
  as flat lists). No pagination.
- Pages send an `ETag`, so conditional GET will work.
- Detail page (store / restaurant): a type label (`Certified store`, `Certified Restaurant`),
  business name, phone, address, website, "HMA Monitored & Certified Products", "Items NOT
  certified by HMA", an overview paragraph and feature tags. Store pages for chains also list
  "Other Locations".
- Detail page (processed meat, non-meat, home business): `Certified Company`, a category
  label, name, phone, address (sometimes only city and province), website, and a product
  table or list.
- **Certification expiry** appears on non-meat product pages as a labelled field, e.g.
  `Certification Expires` → `January 31, 2027`. It was not present on the store, restaurant
  or processed-meat pages inspected.
- Suppliers page: tables with the columns Company, Address, Contact, "Phone, Email, Web",
  Certified Products. The page says "Updated as of August 2026".

### Fields available

Name, category (from section), address, city, province, postal code (not always), phone,
website, certifier (HMA), certification expiry (non-meat pages), certified product scope.

### Personal data present, and how it is excluded

- The suppliers table has a **Contact** column with named individuals, and some cells mix a
  person's name and mobile number into the phone column. The Contact column is never read;
  phone cells are reduced to the business number.
- Several supplier and home-business emails are personal (webmail or a person's name as the
  local part). Only role addresses (info@, sales@, orders@, contact@) are kept; all others
  are dropped (Rule 5).
- **Home-based businesses**: any address on these pages is a home address. No address is
  stored for this section; city and province only.
- The suppliers page and the home-business detail page are therefore **not committed** as
  fixtures. Phase 4 needs a decision on scrubbed copies before those two parsers get tests.

### Rules for the adapter

- `halal_status = certified`, `certifier = HMA`.
- `muslim_owned = not_stated` always. HMA certifies large non-Muslim-owned companies too
  (grocery chains appear in the restaurant list). Certification never implies ownership.
- Product-level "Halal Check" pages and the product category pages (`/baked-goods/`,
  `/dairy-products/`, …) are about products, not businesses, and are out of scope.

### Fixtures

`scraper/tests/fixtures/hma/`: `certified-outlets.html`, `stores-index.html`,
`store-iqbal-foods-thorncliffe.html`, `restaurants-index.html`,
`restaurant-lahore-tikka-house.html`, `processed-meat-index.html`,
`processed-meat-sufra.html`, `non-meat-index.html`, `non-meat-italpasta.html`,
`home-businesses-index.html`.

---

## `hicc_bc` — HIC Canada (Halal Inspection & Certification, BC Muslim Association)

**Status: Cleared.** Type: certifier. Trust rank 1.

- **Official URL:** `https://hiccanada.ca/certified/` ("Certified Vendors"). HIC Canada
  describes itself as established by The BC Muslim Association. Third-party re-uploads are
  not used.
- **robots.txt:** disallows only `/wp-admin/`. `/certified/` is allowed. No `Crawl-delay`.
- **Terms:** no terms-of-use or privacy page is linked from the page or listed in the sitemap.
- **Structure:** WordPress + Elementor, server-rendered, a single page with no pagination.
  Vendors are grouped in five collapsible sections: Restaurant & Caterers, Retailer,
  Slaughterhouse, Manufacturers, Wholesaler. A vendor is normally one list item:
  `<li><strong>Name</strong> | phone | <a>website</a> | address</li>`.
  47 entries follow that exact pattern, but the page contains 64 postal codes, so some
  entries are marked up differently and the parser must handle both.
  Some entries carry a scope note, e.g. "*Only Cazba Commissary Kitchen is certified".
- **Fields available:** name, category (from section), phone, website, address with postal
  code. All postal codes start with `V` (British Columbia).
- **Not available:** certification expiry dates, a "last updated" date.
- **Personal data:** none in the vendor list. Staff contact details in the page footer are not
  part of the list and are not read.
- **No ETag / Last-Modified** headers, so change detection relies on `content_hash`.
- **Adapter rules:** `halal_status = certified`, `certifier = HIC Canada`,
  `muslim_owned = not_stated`. Scope notes must be kept in `extra`.

Fixture: `scraper/tests/fixtures/hicc_bc/certified.html`.

---

## `osm_overpass` — OpenStreetMap via Overpass API

**Status: Decision needed** before the adapter is built.

- **Licence:** ODbL 1.0. Attribution "© OpenStreetMap contributors (ODbL)" is required on the
  site, in the README and with the CSV.
- **Main instance** `https://overpass-api.de/api/interpreter`:
  - `https://overpass-api.de/robots.txt` contains `User-agent: *` / `Disallow: /api/`. The
    query endpoint is under `/api/`, so the project's client refuses to call it.
  - The published usage policy does allow programmatic use: under 10,000 queries and 1 GB per
    day, an identifying `User-Agent`, no parallel scripts, and a 30-second pause after HTTP
    429. This project would send one query per day.
  - The robots.txt rule and the usage policy point in different directions. Rule 4 says a
    robots.txt disallow means "do not build", so this is left to the operator to decide.
- **Mirrors** (same data, same licence):
  - `https://overpass.private.coffee/api/interpreter` — no robots.txt (404); policy: free for
    any project, no rate limit, notify them before large-scale use.
  - `https://overpass.kumi.systems/api/interpreter` — no robots.txt (404).
  - On 2026-10-01 both mirrors timed out on every request to `/api/` from this network,
    including the trivial `/api/status` endpoint, while their `/robots.txt` answered
    immediately. No response was obtained from either.
- **Other route:** OpenStreetMap asks bulk users to take data from planet extracts
  (for example a Canada extract) instead of live services. This avoids the robots.txt question
  entirely but means downloading a multi-gigabyte file and filtering it locally.
- **Fixture:** none. No Overpass response could be captured, and sample data is never invented.

Options for the operator:

1. Treat Overpass as a documented public API rather than a crawl target, and allow this one
   endpoint explicitly (one request per day, within the published usage policy).
2. Use a mirror with no robots.txt restriction, once one responds from the deployment network.
3. Use a Canada extract of OpenStreetMap and filter `diet:halal=yes|only` locally.

---

## `jaffari_dir` — Jaffari Business Directory (ISIJ of Toronto)

**Status: Permission required.** No adapter until ISIJ of Toronto gives written permission.

- **URL:** `https://jaffari.org/directory/` (the `?view=list` variant links the same
  listings). Detail pages: `https://jaffari.org/directory/<slug>/`.
- **robots.txt:** disallows only `/wp-admin/`. The directory paths are allowed.
- **Terms** (`https://jaffari.org/terms-and-conditions/`), copyright section: "You may print
  and download extracts from this Website for your own personal use. You may not modify,
  alter, republish, redistribute, resend, sell or broadcast any material on this Website to
  any other party without our prior written permission." Publishing these listings in a
  directory and CSV is republication, so permission is needed first.
- **Structure:** WordPress + Directorist plugin, server-rendered cards. The page reported 11
  listings but showed 6; the "page 2" link (`/directory/page/2/`) returned HTTP 404 on a plain
  request, so further pages are probably loaded by script.
- **Fields on a card / detail page:** name, category, address, phone, website, email,
  description.
- **Personal data:** descriptions name individual people; emails are hidden behind Cloudflare
  email protection and several would not be role addresses. Both would be excluded.
- **Self-identification caveat:** listings are submitted and paid for by the business, and the
  directory is described as supporting "businesses within our community". Non-members can also
  buy a listing, so a listing is not by itself a statement of Muslim ownership. If permission
  is granted, the operator must decide whether a listing here counts as `self_identified`.
- **Disclaimer on the page:** ISIJ "is not responsible for the content, accuracy, or
  representation of any … business listings".
- **Fixtures:** not committed, because the terms forbid redistribution.

Suggested next step: email ISIJ of Toronto asking for written permission to include the
directory's business listings (name, category, business address, phone, website) with a link
back to each listing.

---

## `hmca` — Halal Montreal Certification Authority

**Status: Not available.**

- **Official URL:** `https://halalmontreal.com/`.
- **robots.txt:** allows everything.
- **Access:** the home page and the page sitemap both returned **HTTP 403** to the project's
  identified bot User-Agent. The User-Agent is not disguised to get around this.
- **Public client list:** none. The site shows a strip of client logos under "Our Valued
  Clients" and links a "Suspended / Cancelled / Terminated customer list", but there is no
  page listing currently certified clients.

Suggested next step: ask HMCA whether they publish, or would share, a list of certified
clients.

---

## Ontario Muslim Chamber of Commerce (OMCC)

**Status: Not available.** No source id assigned.

- **URL:** `https://www.ontariomcc.ca/`. No robots.txt (404).
- The site has no public member directory. Its navigation is Home, Entrepreneurship, Careers,
  Events, Contact, and a link to a members portal sign-up. Business referrals are handled by
  email, not through a public list.

---

## Not to be scraped

Commercial Muslim directory apps and halal restaurant review sites (for example Muslim
Directory App and similar) are **not scraped**; their terms typically forbid it. They can only
be added through a partnership or an official API.

## Candidates found during inspection (not approved)

These are not in CLAUDE.md §4. Rule 7 requires the operator's approval before any work on them.

- Canadian Islamic Chamber of Commerce — `http://www.islamicchamber.ca/membership-directory/`
  appears to be a public membership directory. Not fetched or inspected.
