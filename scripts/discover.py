#!/usr/bin/env python3
"""
DECOUVERTE DES LANDING PAGES.

L'inventaire ne fournit que des domaines. Les slugs varient par marche
(/lp/vendez-votre-voiture, /odkup/..., /tasacion/...). Ce script trouve les URLs
de LP de chaque site, sans supposer de convention de nommage.

Trois sources, dans l'ordre :
  1. sitemap.xml (declare dans robots.txt, ou aux emplacements usuels)
  2. liens internes de la page d'accueil (footer, plan de site, sous-nav)
  3. rien -> le site est marque 'a_inspecter_manuellement'

Ecrit inventory/pages.csv (entree de scripts/extract.py) et met a jour
inventory/sites.csv (colonne pages_decouvertes).

Usage :
    python3 scripts/discover.py                      # tout l'inventaire
    python3 scripts/discover.py --country FR         # un pays
    python3 scripts/discover.py --limit 5            # echantillon de test
    python3 scripts/discover.py --delay 1.5          # politesse entre requetes
"""
import argparse, csv, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("pip install requests beautifulsoup4")

ROOT = Path(__file__).resolve().parent.parent
INV = ROOT / "inventory"
UA = "Mozilla/5.0 (compatible; RetomaV2Discover/1.0)"
TIMEOUT = 20

# Segments qui signalent une landing page editoriale, toutes langues du parc.
LP_HINTS = re.compile(
    r"/(lp|landing)/"
    r"|vendez|vendre|reprise|estimation|cote|rachat"          # fr
    r"|verkopen|overname|inruil|waarde"                        # nl
    r"|verkauf|ankauf|bewertung|wert|schaetzung"               # de
    r"|vender|tasacion|valoracion|compra"                      # es
    r"|vendere|valutazione|usato|permuta"                       # it
    r"|sprzedaj|odkup|wycena|wartosc"                           # pl
    r"|sell|trade-in|tradein|valuation",                        # en
    re.I,
)
# Pages fonctionnelles : jamais des LP editoriales.
EXCLUDE = re.compile(
    r"\.(pdf|jpg|jpeg|png|webp|svg|xml|zip)$"
    r"|/(cookies?|privacy|confidentialit|politica|datenschutz|mentions|legal|cgu|cgv)"
    r"|accessibilit|sitemap|#|mailto:|tel:",
    re.I,
)


def get(url, session):
    try:
        r = session.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT,
                        allow_redirects=True)
        return r if r.status_code == 200 else None
    except requests.RequestException:
        return None


def from_sitemap(base, session, seen):
    """Suit robots.txt puis les emplacements usuels, y compris les index de sitemaps."""
    candidates = []
    r = get(urljoin(base, "/robots.txt"), session)
    if r:
        candidates += re.findall(r"(?im)^\s*sitemap:\s*(\S+)", r.text)
    candidates += [urljoin(base, p) for p in
                   ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml")]

    urls, queue, guard = [], list(dict.fromkeys(candidates)), 0
    while queue and guard < 12:
        guard += 1
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        r = get(sm, session)
        if not r:
            continue
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", r.text, re.I | re.S)
        for loc in locs:
            if loc.endswith(".xml"):
                queue.append(loc)          # index de sitemaps
            else:
                urls.append(loc.strip())
    return urls


def from_homepage(base, session):
    r = get(base, session)
    if not r:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    host = urlparse(base).netloc
    out = []
    for a in soup.find_all("a", href=True):
        u = urljoin(base, a["href"])
        if urlparse(u).netloc == host:
            out.append(u.split("#")[0].rstrip("/"))
    return out


def keep(urls, base):
    host = urlparse(base).netloc
    out = []
    for u in urls:
        if urlparse(u).netloc != host:
            continue
        if EXCLUDE.search(u) or not LP_HINTS.search(u):
            continue
        u = u.split("?")[0].rstrip("/")
        if u.rstrip("/") == base.rstrip("/"):
            continue                       # la home n'est pas une LP
        out.append(u)
    return sorted(dict.fromkeys(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country")
    ap.add_argument("--brand")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--delay", type=float, default=1.0)
    a = ap.parse_args()

    sites = list(csv.DictReader((INV / "sites.csv").open(encoding="utf-8")))
    todo = [s for s in sites
            if (not a.country or s["country"] == a.country)
            and (not a.brand or s["brand_slug"] == a.brand)]
    if a.limit:
        todo = todo[:a.limit]

    print(f"Decouverte sur {len(todo)} site(s)\n")
    session = requests.Session()
    pages, stats = [], {"sitemap": 0, "accueil": 0, "vide": 0, "injoignable": 0}

    for i, s in enumerate(todo, 1):
        base, seen = s["url"], set()
        found = keep(from_sitemap(base, session, seen), base)
        source = "sitemap"
        if not found:
            found = keep(from_homepage(base, session), base)
            source = "accueil"
        if not found:
            source = "vide" if get(base, session) else "injoignable"
            s["statut"] = "a_inspecter_manuellement"
        stats[source] += 1
        s["pages_decouvertes"] = len(found)

        print(f"  [{i:>2}/{len(todo)}] {s['site_key']:<28} {len(found):>2} page(s)  ({source})")
        for u in found:
            pages.append({
                "site_key": s["site_key"], "country": s["country"], "lang": s["lang"],
                "brand": s["brand_slug"], "template": s["template"],
                "url": u, "slug": urlparse(u).path, "source": source,
            })
        time.sleep(a.delay)

    INV.mkdir(exist_ok=True)
    with (INV / "pages.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["site_key", "country", "lang", "brand",
                                          "template", "url", "slug", "source"])
        w.writeheader()
        w.writerows(pages)
    with (INV / "sites.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(sites[0].keys()))
        w.writeheader()
        w.writerows(sites)

    print(f"\n{len(pages)} page(s) sur {len(todo)} site(s)")
    print("  " + " | ".join(f"{k} {v}" for k, v in stats.items()))
    if stats["vide"] or stats["injoignable"]:
        print("\n  Les sites sans resultat sont marques 'a_inspecter_manuellement'"
              " dans inventory/sites.csv.")
    print("\n-> inventory/pages.csv (entree de scripts/extract.py)")


if __name__ == "__main__":
    main()
