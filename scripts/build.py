#!/usr/bin/env python3
"""
Build des LP V2 : content/<site>/<page>.json + themes/themes.json -> dist/<site>/<page>.html

Deterministe : meme entree = meme sortie. Aucune generation de texte ici.
Usage :
    python3 scripts/build.py              # tout
    python3 scripts/build.py citroen-fr   # un seul site
"""
import json, sys, html, datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
BUILD_DATE = datetime.date.today().isoformat()


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def esc(s):
    """Echappe pour un attribut JSON-LD tout en gardant le texte lisible."""
    return (s or "").replace("&nbsp;", "\u00a0").replace("&mdash;", "\u2014")


def strip_html(s):
    import re
    return re.sub(r"<[^>]+>", "", esc(s))


def build_jsonld(page, url):
    j = page["jsonld"]
    blocks = []

    service = {
        "@context": "https://schema.org", "@type": "Service",
        "@id": f"{url}#service",
        "name": j["service_name"], "alternateName": j["service_alt"],
        "description": j["service_description"], "serviceType": j["service_type"],
        "url": url,
        "provider": {
            "@type": "AutoDealer", "@id": f"{j['provider_url']}#organization",
            "name": j["provider_name"], "url": j["provider_url"],
            "sameAs": [s["href"] for s in page["footer"]["social"]],
        },
        "areaServed": {"@type": "Country", "name": j["area_served"], "@id": j["area_wikidata"]},
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR",
                   "description": j["offer_description"]},
    }
    blocks.append(service)

    steps = next((b for b in page["blocks"] if b["type"] == "etapes"), None)
    if steps:
        blocks.append({
            "@context": "https://schema.org", "@type": "HowTo",
            "name": j["howto_name"], "description": j["howto_description"],
            "estimatedCost": {"@type": "MonetaryAmount", "currency": "EUR", "value": "0"},
            "step": [{
                "@type": "HowToStep", "position": i + 1,
                "url": f"{url}#etape-{i+1}",
                "name": strip_html(s["h3"]),
                "itemListElement": [{"@type": "HowToDirection", "text": strip_html(p)}
                                    for p in s["paragraphs"]],
            } for i, s in enumerate(steps["steps"])],
        })

    faq = next((b for b in page["blocks"] if b["type"] == "faq"), None)
    if faq:
        entities = []
        for it in faq["items"]:
            parts = [strip_html(p) for p in it.get("paragraphs", [])]
            parts += [strip_html(b) for b in it.get("bullets", [])]
            parts += [strip_html(p) for p in it.get("paragraphs_after", [])]
            entities.append({
                "@type": "Question", "name": strip_html(it["q"]),
                "acceptedAnswer": {"@type": "Answer", "text": " ".join(parts)},
            })
        blocks.append({"@context": "https://schema.org", "@type": "FAQPage",
                       "mainEntity": entities})

    blocks.append({
        "@context": "https://schema.org", "@type": "WebPage", "@id": url, "url": url,
        "name": page["meta"]["title"], "description": page["meta"]["description"],
        "inLanguage": f"{page['lang']}-{page['market']}",
        "isPartOf": {"@type": "WebSite", "url": page["domain"],
                     "name": page["meta"]["site_name"]},
        "breadcrumb": {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": c["label"],
                 "item": c["href"] or url}
                for i, c in enumerate(page["breadcrumb"])],
        },
        "speakable": {"@type": "SpeakableSpecification",
                      "cssSelector": ["h1", "h2", ".callout-block"]},
        "relatedLink": j["related"],
    })

    return [json.dumps(b, ensure_ascii=False, indent=2) for b in blocks]


def main():
    themes = load(ROOT / "themes/themes.json")
    env = Environment(loader=FileSystemLoader(ROOT / "templates"),
                      trim_blocks=False, lstrip_blocks=False, autoescape=False)

    only = sys.argv[1] if len(sys.argv) > 1 else None
    sites = sorted(d for d in (ROOT / "content").iterdir() if d.is_dir())
    built, registry = 0, []

    for site in sites:
        if only and site.name != only:
            continue
        for f in sorted(site.glob("*.json")):
            page = load(f)
            theme = themes["brands"][page["brand"]]
            tpl = env.get_template(f"{theme['template']}.html.j2")
            url = page["domain"] + page["slug"]
            out_html = tpl.render(
                page=page, theme=theme, tokens=themes["tokens_communs"],
                url=url, jsonld=build_jsonld(page, url), build_date=BUILD_DATE,
            )
            out = ROOT / "dist" / site.name / (f.stem + ".html")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(out_html, encoding="utf-8")
            built += 1
            registry.append({
                "page_key": page["page_key"], "brand": page["brand"],
                "market": page["market"], "url": url,
                "artefact": str(out.relative_to(ROOT)),
                "octets": len(out_html.encode()), "build": BUILD_DATE,
                "bo_status": "non_pousse",
            })
            print(f"  OK  {out.relative_to(ROOT)}  ({len(out_html):,} car.)")

    reg_path = ROOT / "registry/registry.json"
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load(reg_path) if reg_path.exists() else {"pages": []}
    by_key = {p["page_key"]: p for p in existing.get("pages", [])}
    for r in registry:
        # on ne perd jamais le statut BO deja acquis
        r["bo_status"] = by_key.get(r["page_key"], {}).get("bo_status", "non_pousse")
        by_key[r["page_key"]] = r
    reg_path.write_text(json.dumps(
        {"maj": BUILD_DATE, "pages": sorted(by_key.values(), key=lambda p: p["page_key"])},
        ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{built} page(s) construite(s). Registre : registry/registry.json")


if __name__ == "__main__":
    main()
