#!/usr/bin/env python3
"""
EXTRACTEUR V1 -> contenu structure V2.

Produit un BROUILLON de content/<site>/<page>.json a partir d'une page V1 en ligne,
plus un rapport listant tout ce que la machine n'a pas pu decider seule.

Le brouillon n'est jamais publiable tel quel : les champs marques TODO_* attendent
un arbitrage humain. C'est voulu — mieux vaut un trou visible qu'un texte invente.

Usage :
    python3 scripts/extract.py --url https://www.reprise.citroen.fr/lp/vendez-votre-voiture \
                               --brand citroen --market FR
    python3 scripts/extract.py --file fixtures/page.html --brand citroen --market FR \
                               --url https://www.reprise.citroen.fr/lp/vendez-votre-voiture
    python3 scripts/extract.py --batch sites.csv        # colonnes : url,brand,market

Dependances : requests, beautifulsoup4
"""
import argparse, json, re, sys, csv, unicodedata
from pathlib import Path
from urllib.parse import urlparse, urljoin

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("pip install beautifulsoup4")

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (compatible; RetomaV2Extractor/1.0)"

TODO = "TODO_ARBITRAGE"
SOCIAL_PATTERNS = {
    "facebook": "facebook.com", "x": "twitter.com", "instagram": "instagram.com",
    "youtube": "youtube.com", "linkedin": "linkedin.com",
}
# Un plan de site n'est jamais repris en V2 (decision du 2026-08-03).
# On le detecte uniquement pour l'inventaire, jamais pour l'injecter.
SITEMAP_HINTS = ("plan du site", "plano do site", "mapa do site")


# ─────────────────────────── utilitaires ───────────────────────────
def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def clean(s):
    """Normalise les espaces et repare les concatenations cassees du V1."""
    if not s:
        return ""
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    # minuscule collee a une majuscule = fin de liste soudee au paragraphe suivant
    s = re.sub(r"([a-zàâçéèêëîïôûùüÿñæœ])([A-ZÀÂÇÉÈÊËÎÏÔÛÙÜŸÑÆŒ])", r"\1 \2", s)
    return s.strip(" -–—")


def txt(node):
    return clean(node.get_text(" ", strip=True)) if node else ""


# ─────────────────────────── extraction ───────────────────────────
def extract(html, url, brand, market, notes):
    soup = BeautifulSoup(html, "html.parser")
    dom = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    lang = (soup.html.get("lang") if soup.html else None) or market.lower()

    def meta(name=None, prop=None):
        sel = {"name": name} if name else {"property": prop}
        tag = soup.find("meta", attrs=sel)
        return clean(tag.get("content", "")) if tag else ""

    # --- meta ---
    title = clean(soup.title.string if soup.title else "")
    desc = meta(name="description")
    canon = soup.find("link", rel="canonical")
    canon = canon.get("href") if canon else url
    if not title:
        notes.append("title absent en V1")
    if not desc:
        notes.append("meta description absente en V1")

    # --- h1 ---
    h1s = soup.find_all("h1")
    if len(h1s) != 1:
        notes.append(f"{len(h1s)} <h1> en V1 (il en faut 1) — a arbitrer")
    h1 = txt(h1s[0]) if h1s else TODO

    # --- fil d'Ariane : on deduplique, V1 repete parfois 'Accueil' ---
    crumbs, seen = [], set()
    bc = soup.find(class_=re.compile(r"breadcrumb", re.I))
    if bc:
        for a in bc.find_all(["a", "span"]):
            label = txt(a)
            if not label or label in seen or label == "/":
                continue
            seen.add(label)
            href = urljoin(dom, a.get("href")) if a.name == "a" and a.get("href") else None
            crumbs.append({"label": label, "href": href})
    if crumbs:
        crumbs[-1]["href"] = None  # la page courante n'est jamais un lien
    else:
        notes.append("fil d'Ariane introuvable")

    # --- images de contenu (hors logos/icones) ---
    medias = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src or src.startswith("data:"):
            continue
        src = urljoin(dom, src)
        if re.search(r"logo|icon|sprite|pixel", src, re.I):
            continue
        alt = clean(img.get("alt", ""))
        if not alt:
            notes.append(f"image sans alt en V1 : {src[:80]}")
        medias.append({"url": src, "alt": alt or TODO})

    # --- blocs de contenu : chaque h2 ouvre une section ---
    # On travaille sur une copie amputee des zones structurelles : sans ca, les
    # titres de pied de page remontent comme blocs de contenu.
    corpus = BeautifulSoup(html, "html.parser")
    for zone in corpus.find_all(["footer", "header", "nav"]):
        zone.decompose()
    for zone in corpus.find_all(class_=re.compile(r"footer|header|breadcrumb|menu", re.I)):
        zone.decompose()

    blocks = []
    for i, h2 in enumerate(corpus.find_all(["h2", "h3"])):
        heading = txt(h2)
        if not heading or any(k in heading.lower() for k in SITEMAP_HINTS):
            continue
        paragraphs, bullets = [], []
        for sib in h2.find_next_siblings():
            if sib.name in ("h1", "h2"):
                break
            if sib.name == "p":
                t = txt(sib)
                if t:
                    paragraphs.append(t)
            elif sib.name in ("ul", "ol"):
                bullets += [txt(li) for li in sib.find_all("li") if txt(li)]
        if not paragraphs and not bullets:
            continue
        is_faq = bool(re.search(r"question|faq|perguntas", heading, re.I))
        is_steps = any(re.match(r"^(étape|etape|passo|step)\s*\d", p, re.I) for p in paragraphs)
        blocks.append({
            "type": "faq" if is_faq else ("etapes" if is_steps else "two_col"),
            "id": slugify(heading)[:40] or f"bloc-{i}",
            "h2": heading,
            "paragraphs": [{"text": p} for p in paragraphs],
            "bullets": bullets,
            "image": medias[min(i, len(medias) - 1)]["url"] if medias else TODO,
            "image_alt": medias[min(i, len(medias) - 1)]["alt"] if medias else TODO,
            "tag": TODO,
            "image_side": "left" if i % 2 else "right",
        })
    if not blocks:
        notes.append("aucun bloc de contenu detecte — structure V1 inhabituelle")

    # --- pied de page ---
    columns, social, sitemap_links = [], [], 0
    foot = soup.find("footer") or soup.find(class_=re.compile(r"footer", re.I))
    if foot:
        for a in foot.find_all("a", href=True):
            for net, pat in SOCIAL_PATTERNS.items():
                if pat in a["href"]:
                    social.append({"network": net, "href": a["href"]})
                    break
        for h in foot.find_all(["h2", "h3", "h4", "strong"]) + foot.find_all(
                class_=re.compile(r"col-title|footer-title", re.I)):
            label = txt(h)
            # un vrai titre de colonne est court et ne contient pas de lien
            if not label or len(label) > 32 or h.find("a"):
                continue
            if any(k in label.lower() for k in SITEMAP_HINTS):
                sitemap_links += 1
                continue
            links = []
            for sib in h.find_next_siblings():
                links += [{"label": txt(a), "href": a["href"]}
                          for a in sib.find_all("a", href=True) if txt(a)]
                if len(links) > 8:
                    break
            if 1 <= len(links) <= 8:
                columns.append({"title": label, "links": links[:6]})
    else:
        notes.append("pied de page introuvable")
    if sitemap_links:
        notes.append("plan de site detecte en V1 — ABANDONNE en V2 (regle actee)")

    # --- mentions legales : on capture la date d'expiration ---
    legal = ""
    expire = None
    body = soup.get_text(" ", strip=True)
    m = re.search(r"(Offre r[ée]serv[ée]e aux particuliers.{20,600}?\.)", body)
    if m:
        legal = clean(m.group(1))
        d = re.search(r"avant le (\d{1,2})\s+(\w+)\s+(\d{4})", legal)
        if d:
            mois = {"janvier": "01", "février": "02", "mars": "03", "avril": "04",
                    "mai": "05", "juin": "06", "juillet": "07", "août": "08",
                    "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"}
            mm = mois.get(d.group(2).lower())
            if mm:
                expire = f"{d.group(3)}-{mm}-{int(d.group(1)):02d}"
    else:
        notes.append("mention legale de l'offre non trouvee")

    # --- assemblage ---
    site = f"{brand}-{market.lower()}"
    slug = urlparse(url).path
    page = {
        "page_key": f"{site}__{slug.strip('/').replace('/', '-')}",
        "brand": brand, "market": market, "lang": lang,
        "locale": f"{lang}_{market}", "template": "shared",
        "domain": dom, "slug": slug, "source_v1": url,
        "meta": {
            "title": title or TODO, "description": desc or TODO,
            "site_name": TODO, "author": TODO,
            "geo_region": market, "geo_country": TODO,
            "og_image_alt": TODO,
        },
        "header": {"logo": TODO, "logo_alt": TODO, "cta_label": TODO, "cta_href": f"{dom}/"},
        "breadcrumb": crumbs or [{"label": TODO, "href": dom}],
        "hero": {
            "image": "TODO_HERO_STELLANTIS",  # jamais un visuel V1 : trop basse definition
            "tag": TODO, "h1": h1,
            "lead": desc or TODO,
            "cta_label": TODO, "cta_href": f"{dom}/",
        },
        "subnav": [{"label": b["h2"][:24], "anchor": "#" + b["id"]} for b in blocks[:5]],
        "trust": [{"icon": "check", "label": TODO, "sub": TODO} for _ in range(4)],
        "blocks": blocks,
        "cta_final": {"tag": TODO, "h2": TODO, "lead": TODO,
                      "cta_label": TODO, "cta_href": f"{dom}/"},
        "footer": {
            "tagline": desc or TODO, "social": social, "columns": columns[:3],
            "legal": legal or TODO, "legal_expire": expire,
            "eco": TODO, "eco_link_label": TODO, "eco_link_href": TODO, "year": TODO,
        },
        "jsonld": {
            "service_name": TODO, "service_alt": [], "service_type": TODO,
            "service_description": desc or TODO,
            "provider_name": TODO, "provider_url": TODO,
            "area_served": TODO, "area_wikidata": TODO, "offer_description": TODO,
            "howto_name": TODO, "howto_description": TODO, "related": [],
        },
        "_extraction": {
            "canonical_v1": canon,
            "medias_trouves": len(medias),
            "blocs_detectes": len(blocks),
            "notes": notes,
        },
    }
    return page


def count_todo(obj):
    if isinstance(obj, str):
        return 1 if obj.startswith("TODO") else 0
    if isinstance(obj, dict):
        return sum(count_todo(v) for k, v in obj.items() if k != "_extraction")
    if isinstance(obj, list):
        return sum(count_todo(v) for v in obj)
    return 0


def run(url, brand, market, from_file=None, outdir=None):
    notes = []
    if from_file:
        html = Path(from_file).read_text(encoding="utf-8")
    else:
        import requests
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        html = r.text
    page = extract(html, url, brand, market, notes)
    site = f"{brand}-{market.lower()}"
    out = (Path(outdir) if outdir else ROOT / "content") / site
    out.mkdir(parents=True, exist_ok=True)
    dest = out / ((urlparse(url).path.rstrip("/").split("/")[-1] or "index") + ".draft.json")
    dest.write_text(json.dumps(page, ensure_ascii=False, indent=2), encoding="utf-8")
    todo = count_todo(page)
    print(f"  {dest.relative_to(ROOT) if dest.is_relative_to(ROOT) else dest}")
    print(f"    blocs {page['_extraction']['blocs_detectes']} | "
          f"medias {page['_extraction']['medias_trouves']} | champs a arbitrer {todo}")
    for n in notes:
        print("    ~", n)
    return todo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--brand")
    ap.add_argument("--market")
    ap.add_argument("--file", help="HTML local, pour tester hors ligne")
    ap.add_argument("--batch", help="CSV : url,brand,market")
    ap.add_argument("--out")
    a = ap.parse_args()

    if a.batch:
        rows = list(csv.DictReader(Path(a.batch).open(encoding="utf-8")))
        print(f"Extraction de {len(rows)} page(s)\n")
        total = 0
        for r in rows:
            try:
                total += run(r["url"], r["brand"], r["market"], outdir=a.out)
            except Exception as e:
                print(f"  ECHEC {r['url']} : {e}")
        print(f"\n{total} champ(s) a arbitrer au total.")
    elif a.url and a.brand and a.market:
        run(a.url, a.brand, a.market, from_file=a.file, outdir=a.out)
    else:
        ap.error("--url --brand --market, ou --batch")


if __name__ == "__main__":
    main()
