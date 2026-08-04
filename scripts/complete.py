#!/usr/bin/env python3
"""
COMPLETEUR DE BROUILLONS -> content/ pret pour build.py

Ne resout QUE ce qui est mecaniquement deductible :
  1. Propagation intra-site : logo, reseaux sociaux, colonnes de footer, mention
     legale sont identiques sur toutes les pages d'un meme site. Si une page les a
     captes et qu'une autre a echoue, on propage -- jamais entre sites differents.
  2. Champs structurels : meta.geo_country, jsonld.area_served/wikidata depuis le
     code marche ; meta.author/site_name depuis marque+marche ; footer.year =
     annee courante ; og_image_alt = H1 (meme information, autre champ).
  3. JSON-LD service/howto/faq derives du contenu deja extrait (meme logique que
     build.py), jamais reecrit a la main.

Ce qui N'EST PAS resolu, volontairement : tout texte marketing que le V1 ne
fournit pas (libelles des trust cards, tag du hero, CTA courts, titre/lead du
bloc CTA final quand absents). Inventer ce texte sur 428 pages en 7 langues
produirait du faux contenu de marque non verifiable -- c'est un arbitrage
humain, pas une extraction.

Usage : python3 complete.py <dossier_drafts> <dossier_sortie>
"""
import json, sys, re, datetime
from pathlib import Path
from collections import defaultdict

TODO = "TODO_ARBITRAGE"
ANNEE = str(datetime.date.today().year)

PAYS = {
    "FR": ("France", "https://www.wikidata.org/wiki/Q142"),
    "BE": ("Belgique" , "https://www.wikidata.org/wiki/Q31"),
    "LU": ("Luxembourg", "https://www.wikidata.org/wiki/Q32"),
    "DE": ("Allemagne", "https://www.wikidata.org/wiki/Q183"),
    "AT": ("Autriche", "https://www.wikidata.org/wiki/Q40"),
    "ES": ("Espagne", "https://www.wikidata.org/wiki/Q29"),
    "IT": ("Italie", "https://www.wikidata.org/wiki/Q38"),
    "PL": ("Pologne", "https://www.wikidata.org/wiki/Q36"),
    "UK": ("Royaume-Uni", "https://www.wikidata.org/wiki/Q145"),
}


def is_todo(v):
    return isinstance(v, str) and v.startswith("TODO")


def count_todo(o, skip=("_extraction",)):
    if isinstance(o, str):
        return 1 if o.startswith("TODO") else 0
    if isinstance(o, dict):
        return sum(count_todo(v) for k, v in o.items() if k not in skip)
    if isinstance(o, list):
        return sum(count_todo(v) for v in o)
    return 0


def strip_html(s):
    return re.sub(r"<[^>]+>", "", (s or "").replace("&nbsp;", " "))


def build_jsonld(page):
    """Meme logique que build.py : derive du contenu deja present, n'invente rien."""
    j = dict(page["jsonld"])
    market, brand = page["market"], page["brand"]

    if is_todo(j.get("area_served")):
        j["area_served"] = PAYS.get(market, (market, None))[0]
    if is_todo(j.get("area_wikidata")):
        j["area_wikidata"] = PAYS.get(market, (None, None))[1]
    if is_todo(j.get("service_name")):
        j["service_name"] = f"{page['meta']['title'].split('|')[0].strip()}"
    if is_todo(j.get("service_description")) and not is_todo(page["meta"]["description"]):
        j["service_description"] = page["meta"]["description"]
    if is_todo(j.get("offer_description")):
        j["offer_description"] = j.get("service_description") if not is_todo(j.get("service_description")) else TODO
    if is_todo(j.get("provider_name")):
        j["provider_name"] = page["header"].get("logo_alt") if not is_todo(page["header"].get("logo_alt")) else TODO
    if is_todo(j.get("provider_url")):
        j["provider_url"] = page["domain"]
    if is_todo(j.get("service_type")):
        j["service_type"] = "Reprise automobile"

    etapes = next((b for b in page["blocks"] if b["type"] == "etapes"), None)
    if etapes and is_todo(j.get("howto_name")):
        j["howto_name"] = page["hero"]["h1"] if not is_todo(page["hero"]["h1"]) else TODO
    if etapes and is_todo(j.get("howto_description")) and not is_todo(page["meta"]["description"]):
        j["howto_description"] = page["meta"]["description"]

    if not j.get("related"):
        j["related"] = []  # liste vide valide : pas de lien connexe fiable sans risque de 404
    return j


def site_constants(pages):
    """Premiere valeur non-TODO trouvee pour chaque champ propageable, tous
    volets du site confondus. Ne traverse jamais les frontieres d'un site."""
    const = {
        "logo": None, "logo_alt": None,
        "social": None, "columns": None,
        "legal": None, "legal_expire": None,
        "eco": None, "eco_link_label": None, "eco_link_href": None,
    }
    for p in pages:
        if const["logo"] is None and not is_todo(p["header"].get("logo")):
            const["logo"] = p["header"]["logo"]
        if const["logo_alt"] is None and not is_todo(p["header"].get("logo_alt")):
            const["logo_alt"] = p["header"]["logo_alt"]
        if const["social"] is None and p["footer"].get("social"):
            const["social"] = p["footer"]["social"]
        if const["columns"] is None and p["footer"].get("columns"):
            const["columns"] = p["footer"]["columns"]
        if const["legal"] is None and not is_todo(p["footer"].get("legal")) and p["footer"].get("legal"):
            const["legal"] = p["footer"]["legal"]
        if const["legal_expire"] is None and p["footer"].get("legal_expire"):
            const["legal_expire"] = p["footer"]["legal_expire"]
        if const["eco"] is None and not is_todo(p["footer"].get("eco")):
            const["eco"] = p["footer"]["eco"]
        if const["eco_link_label"] is None and not is_todo(p["footer"].get("eco_link_label")):
            const["eco_link_label"] = p["footer"]["eco_link_label"]
        if const["eco_link_href"] is None and not is_todo(p["footer"].get("eco_link_href")):
            const["eco_link_href"] = p["footer"]["eco_link_href"]
    return const


def complete_page(page, const, ui):
    m = page["market"]
    langue = ui.get(page.get("lang"), ui.get("en"))
    ui_appliquee = False

    if is_todo(page["meta"].get("geo_country")):
        page["meta"]["geo_country"] = PAYS.get(m, (m,))[0]
    if is_todo(page["meta"].get("author")):
        page["meta"]["author"] = f"{page['brand'].replace('-', ' ').title()} {m}"
    if is_todo(page["meta"].get("site_name")):
        page["meta"]["site_name"] = page["meta"]["author"]
    if is_todo(page["meta"].get("og_image_alt")) and not is_todo(page["hero"]["h1"]):
        page["meta"]["og_image_alt"] = page["hero"]["h1"]

    if const["logo"] and is_todo(page["header"].get("logo")):
        page["header"]["logo"] = const["logo"]
    if const["logo_alt"] and is_todo(page["header"].get("logo_alt")):
        page["header"]["logo_alt"] = const["logo_alt"]

    if const["social"] and not page["footer"].get("social"):
        page["footer"]["social"] = const["social"]
    if const["columns"] and not page["footer"].get("columns"):
        page["footer"]["columns"] = const["columns"]
    if const["legal"] and (is_todo(page["footer"].get("legal")) or not page["footer"].get("legal")):
        page["footer"]["legal"] = const["legal"]
    if const["legal_expire"] and not page["footer"].get("legal_expire"):
        page["footer"]["legal_expire"] = const["legal_expire"]
    if const["eco"] and is_todo(page["footer"].get("eco")):
        page["footer"]["eco"] = const["eco"]
    if const["eco_link_label"] and is_todo(page["footer"].get("eco_link_label")):
        page["footer"]["eco_link_label"] = const["eco_link_label"]
    if const["eco_link_href"] and is_todo(page["footer"].get("eco_link_href")):
        page["footer"]["eco_link_href"] = const["eco_link_href"]
    if is_todo(page["footer"].get("year")):
        page["footer"]["year"] = ANNEE
    if is_todo(page["footer"].get("tagline")) and not is_todo(page["meta"]["description"]):
        page["footer"]["tagline"] = page["meta"]["description"]

    # --- chrome UI generique par langue : jamais de contenu editorial ---
    if langue:
        if is_todo(page["hero"].get("tag")):
            page["hero"]["tag"] = langue["hero_tag"]; ui_appliquee = True
        if is_todo(page["hero"].get("cta_label")):
            page["hero"]["cta_label"] = langue["cta_label"]; ui_appliquee = True
        if is_todo(page["header"].get("cta_label")):
            page["header"]["cta_label"] = langue["cta_label"]; ui_appliquee = True
        for i, t in enumerate(page.get("trust", [])):
            if is_todo(t.get("label")) and i < len(langue["trust"]):
                t["label"] = langue["trust"][i]["label"]
                t["sub"] = langue["trust"][i]["sub"]
                t["icon"] = langue["trust"][i]["icon"]
                ui_appliquee = True
        cf = page.get("cta_final", {})
        if is_todo(cf.get("tag")):
            cf["tag"] = langue["cta_final_tag"]; ui_appliquee = True
        if is_todo(cf.get("h2")):
            cf["h2"] = langue["cta_final_h2"]; ui_appliquee = True
        if is_todo(cf.get("lead")):
            cf["lead"] = langue["cta_final_lead"]; ui_appliquee = True
        if is_todo(cf.get("cta_label")):
            cf["cta_label"] = langue["cta_final_cta"]; ui_appliquee = True

    page["_migration"] = page.get("_migration", {})
    page["_migration"]["chrome_ui_generee"] = ui_appliquee
    page["_migration"]["_note_chrome_ui"] = (
        "Libelles d'interface generiques appliques depuis i18n/ui_strings.json "
        "(badge hero, CTA de repli, cartes de confiance, bloc CTA final). "
        "Pas des citations V1 -- a relire pour le ton de marque avant publication."
    ) if ui_appliquee else None

    page["jsonld"] = build_jsonld(page)
    return page


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    dst.mkdir(parents=True, exist_ok=True)
    ui_path = Path(__file__).resolve().parent.parent / "i18n" / "ui_strings.json"
    ui = json.loads(ui_path.read_text(encoding="utf-8")) if ui_path.exists() else {}
    ui = {k: v for k, v in ui.items() if k != "_meta"}

    by_site = defaultdict(list)
    for f in sorted(src.glob("*/*.draft.json")):
        by_site[f.parent.name].append(f)

    avant_total = apres_total = 0
    ui_appliquee_n = 0
    rapport = []
    for site, files in sorted(by_site.items()):
        pages = [json.loads(f.read_text(encoding="utf-8")) for f in files]
        const = site_constants(pages)
        out_dir = dst / site
        out_dir.mkdir(parents=True, exist_ok=True)
        for f, page in zip(files, pages):
            avant = count_todo(page)
            page = complete_page(page, const, ui)
            apres = count_todo(page)
            avant_total += avant
            apres_total += apres
            if page["_migration"].get("chrome_ui_generee"):
                ui_appliquee_n += 1
            out = out_dir / f.name.replace(".draft.json", ".json")
            out.write_text(json.dumps(page, ensure_ascii=False, indent=2), encoding="utf-8")
        rapport.append((site, len(files), avant_total, apres_total))

    resolu = avant_total - apres_total
    print(f"{sum(len(v) for v in by_site.values())} pages sur {len(by_site)} sites\n")
    print(f"TODO avant  : {avant_total}")
    print(f"TODO apres  : {apres_total}")
    print(f"Resolus automatiquement : {resolu} ({resolu/avant_total*100:.0f}%)")
    print(f"Pages avec chrome UI generee (i18n) : {ui_appliquee_n}")
    print(f"\nRestants (arbitrage humain requis) : {apres_total}")
    print(f"-> {dst}")


if __name__ == "__main__":
    main()
