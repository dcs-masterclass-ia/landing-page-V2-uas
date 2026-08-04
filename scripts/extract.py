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
# Meme politique que discover.py : un UA "bot" se fait refouler en 403 sur
# plusieurs marches. On se presente comme un navigateur reel.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr,en;q=0.8,de;q=0.6,nl;q=0.6,es;q=0.6,it;q=0.6,pl;q=0.6",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
SESSION = None

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
MOIS = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12, "décembre": 12,
    "januar": 1, "februar": 2, "marz": 3, "märz": 3, "april": 4, "juni": 6, "juli": 7,
    "august": 8, "oktober": 10, "november": 11, "dezember": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "gennaio": 1, "febbraio": 2, "aprile": 4, "maggio": 5, "giugno": 6, "luglio": 7,
    "settembre": 9, "ottobre": 10, "dicembre": 12,
    "januari": 1, "februari": 2, "maart": 3, "mei": 5, "augustus": 8, "december": 12,
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6,
    "lipca": 7, "sierpnia": 8, "wrzesnia": 9, "pazdziernika": 10, "listopada": 11,
    "grudnia": 12,
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7,
    "october": 10, "december": 12,
}


def date_expiration(texte):
    """Reconnait '31 aout 2026', '31. August 2026', '31/08/2026' dans les 7 langues du parc."""
    m = re.search(r"(\d{1,2})\s*\.?\s+([A-Za-zÀ-ſ]+)\s+(\d{4})", texte)
    if m and m.group(2).lower() in MOIS:
        return f"{m.group(3)}-{MOIS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    n = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", texte)
    if n:
        return f"{n.group(3)}-{int(n.group(2)):02d}-{int(n.group(1)):02d}"
    return None


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

    # --- logo : capte dans header/nav uniquement, l'exact inverse du filtre content ---
    logo_url, logo_alt = None, None
    header_dom = soup.find(["header", "nav"]) or soup
    for img in header_dom.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if src and not src.startswith("data:"):
            logo_url = urljoin(dom, src)
            logo_alt = clean(img.get("alt", "")) or brand.replace("-", " ").title()
            break

    # --- CTA : texte des boutons/liens d'action, verbatim V1 ---
    cta_texts = []
    for a in soup.find_all("a", href=True):
        cls = " ".join(a.get("class") or [])
        if re.search(r"btn|cta|button", cls, re.I):
            t = txt(a)
            if t and t not in cta_texts:
                cta_texts.append(t)
    cta_principal = cta_texts[0] if cta_texts else None

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

    # Lecture en ORDRE DE DOCUMENT plutot que par freres : les titres reels sont
    # imbriques dans des <div>/<section>, leurs paragraphes ne sont donc pas leurs
    # freres. On aplatit le document et on segmente sur les titres.
    # Certains marches (AT, DE) ne balisent PAS leurs sous-titres : les sections
    # sont de simples <div> de texte. Segmenter sur les titres HTML n'y trouve rien.
    # On extrait donc un flux d'unites de texte en ordre de document, puis on
    # classe chaque unite par sa forme : courte et sans ponctuation finale = titre.
    unites = []
    for noeud in corpus.find_all(True):
        if noeud.name in ("script", "style", "svg", "noscript"):
            continue
        propre = clean("".join(c for c in noeud.strings
                               if c.parent is noeud))          # texte en propre
        if len(propre) < 3:
            continue
        unites.append({"tag": noeud.name, "texte": propre,
                       "classe": " ".join(noeud.get("class") or [])})

    def est_titre(u):
        if u["tag"] in ("h1", "h2", "h3", "h4", "h5", "h6"):
            return len(u["texte"]) < 160          # un h2-phrase reste du corps
        if u["tag"] in ("p", "li", "td"):
            return False
        if re.search(r"title|heading|titre|subtitle", u["classe"], re.I):
            return True
        return (len(u["texte"]) < 80
                and not u["texte"].rstrip().endswith((".", "!", "?", ":", ";")))

    segments, courant, vus = [], None, set()
    for u in unites:
        if u["texte"] in vus:                     # meme texte remonte par un parent
            continue
        vus.add(u["texte"])
        if u["tag"] == "h1" or any(k in u["texte"].lower() for k in SITEMAP_HINTS):
            courant = None
            continue
        if est_titre(u):
            courant = {"titre": u["texte"], "niveau": u["tag"], "p": [], "li": []}
            segments.append(courant)
        elif courant is not None:
            (courant["li"] if u["tag"] == "li" else courant["p"]).append(u["texte"])
        elif len(u["texte"]) > 120:               # corps orphelin avant tout titre
            courant = {"titre": TODO, "niveau": "none", "p": [u["texte"]], "li": []}
            segments.append(courant)

    blocks = []
    for i, seg in enumerate(segments):
        if not seg["p"] and not seg["li"]:
            continue
        if sum(len(t) for t in seg["p"] + seg["li"]) < 40:      # bruit d interface
            continue
        titre = seg["titre"]
        is_faq = bool(re.search(r"question|faq|perguntas|preguntas|domande|h\u00e4ufig|"
                                r"veelgeste|pytania|frage", titre, re.I))
        is_steps = any(re.match(r"^(\u00e9tape|etape|passo|paso|schritt|stap|step|krok)\s*\d",
                                t, re.I) for t in seg["p"] + seg["li"])
        img = medias[min(i, len(medias) - 1)] if medias else None
        blocks.append({
            "type": "faq" if is_faq else ("etapes" if is_steps else "two_col"),
            "id": slugify(titre)[:40] or f"bloc-{i+1}",
            "h2": titre,
            "niveau_v1": seg["niveau"],
            "titre_absent_en_v1": seg["niveau"] == "none" or not re.match(r"h[1-6]", seg["niveau"]),
            "paragraphs": [{"text": t} for t in seg["p"]],
            "bullets": seg["li"],
            "image": img["url"] if img else TODO,
            "image_alt": img["alt"] if img else TODO,
            "tag": TODO,
            "image_side": "left" if i % 2 else "right",
        })
    sans_titre = sum(1 for b in blocks if b["titre_absent_en_v1"])
    if sans_titre:
        notes.append(f"{sans_titre} bloc(s) sans titre balise en V1 — titre deduit du texte, A VERIFIER")
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
    if not m and foot:
        # repli multilingue : le plus long paragraphe du pied de page qui ne soit
        # pas une liste de liens est presque toujours la mention legale
        cands = [txt(x) for x in foot.find_all(["p", "div", "small", "span"])
                 if not x.find("a") and 80 < len(txt(x)) < 900]
        if cands:
            legal = max(cands, key=len)
            notes.append("mention legale reperee par repli multilingue — A VERIFIER")
    if m:
        legal = clean(m.group(1))
    if legal:
        expire = date_expiration(legal)
        if not expire:
            notes.append("date d'expiration de la mention legale non reconnue")
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
        "header": {"logo": logo_url or TODO, "logo_alt": logo_alt or TODO,
                  "cta_label": cta_principal or TODO, "cta_href": f"{dom}/"},
        "breadcrumb": crumbs or [{"label": TODO, "href": dom}],
        "hero": {
            "image": "TODO_HERO_STELLANTIS",
            "tag": TODO, "h1": h1,
            "lead": desc or TODO,
            "cta_label": cta_principal or TODO, "cta_href": f"{dom}/",
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


def fetch(url, tentatives=3):
    """Session persistante + reprise avec attente croissante : une 403 ponctuelle
    vient souvent d'une cadence trop soutenue, pas d'un blocage definitif."""
    global SESSION
    import requests, time as _t
    if SESSION is None:
        SESSION = requests.Session()
        SESSION.headers.update(HEADERS)
    derniere = None
    for essai in range(tentatives):
        try:
            r = SESSION.get(url, timeout=30, allow_redirects=True)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding or r.encoding
                return r.text
            derniere = f"HTTP {r.status_code}"
            if r.status_code in (403, 429, 503) and essai < tentatives - 1:
                _t.sleep(2 ** essai * 2)      # 2s, puis 4s
                continue
            break
        except requests.RequestException as e:
            derniere = type(e).__name__
            if essai < tentatives - 1:
                _t.sleep(2 ** essai * 2)
    raise RuntimeError(derniere or "echec")


def run(url, brand, market, from_file=None, outdir=None, site_key=None, lang=None):
    notes = []
    html = Path(from_file).read_text(encoding="utf-8") if from_file else fetch(url)
    page = extract(html, url, brand, market, notes)
    if lang:                      # discover.py distingue les versions linguistiques (BE fr/nl)
        page['lang'] = lang
        page['locale'] = f"{lang}_{market}"
    site = site_key or f"{brand}-{market.lower()}"
    page['page_key'] = f"{site}__" + urlparse(url).path.strip('/').replace('/', '-')
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
    ap.add_argument("--delay", type=float, default=1.0,
                    help="attente entre pages, en secondes")
    a = ap.parse_args()

    if a.batch:
        rows = list(csv.DictReader(Path(a.batch).open(encoding="utf-8")))
        print(f"Extraction de {len(rows)} page(s)\n")
        total = 0
        manquants = [c for c in ("url", "brand") if c not in rows[0]]
        if manquants:
            sys.exit(f"Colonnes absentes du CSV : {', '.join(manquants)}")
        import time as _t
        for n, r in enumerate(rows):
            if n:
                _t.sleep(a.delay)
            try:
                total += run(r["url"], r["brand"],
                             r.get("market") or r.get("country"),
                             outdir=a.out,
                             site_key=r.get("site_key"), lang=r.get("lang"))
            except Exception as e:
                print(f"  ECHEC {r['url']} : {type(e).__name__} {e}")
        print(f"\n{total} champ(s) a arbitrer au total.")
    elif a.url and a.brand and a.market:
        run(a.url, a.brand, a.market, from_file=a.file, outdir=a.out)
    else:
        ap.error("--url --brand --market, ou --batch")


if __name__ == "__main__":
    main()
