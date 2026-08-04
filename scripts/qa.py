#!/usr/bin/env python3
"""
QA GATE — controle bloquant avant tout push en back-office.

Sort en code 1 si un controle BLOQUANT echoue. Les AVERTISSEMENTS n'arretent pas
la chaine mais sont listes.

Usage : python3 scripts/qa.py
"""
import json, re, sys, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TODAY = datetime.date.today()

# ---------- contraste ----------
def _lum(hexc):
    c = hexc.lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    vals = []
    for i in (0, 2, 4):
        v = int(c[i:i+2], 16) / 255
        vals.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]

def contrast(a, b):
    l1, l2 = sorted([_lum(a), _lum(b)], reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)

def flatten(alpha, fg="#ffffff", bg="#000000"):
    f, b = fg.lstrip("#"), bg.lstrip("#")
    out = ""
    for i in (0, 2, 4):
        out += f"{round(int(f[i:i+2],16)*alpha + int(b[i:i+2],16)*(1-alpha)):02x}"
    return "#" + out


class Report:
    def __init__(self):
        self.blocking, self.warnings, self.checks = [], [], 0

    def check(self, ok, msg, blocking=True):
        self.checks += 1
        if not ok:
            (self.blocking if blocking else self.warnings).append(msg)


def audit(path, themes):
    s = path.read_text(encoding="utf-8")
    r = Report()
    name = path.relative_to(ROOT)

    # Caracteres refuses par upload-artifact (NTFS notamment) : mieux vaut le
    # detecter ici que decouvrir l'echec au moment de l'upload CI.
    invalides = set(path.name) & set('"<>:|*?\r\n')
    r.check(not invalides, f"{name} : nom de fichier contient {invalides} (invalide pour l'upload CI)")

    # --- RGAA : structure ---
    hs = [int(h) for h in re.findall(r"<h([1-6])[^>]*>", s)]
    r.check(hs.count(1) == 1, f"{name} : {hs.count(1)} <h1> (il en faut exactement 1)")
    jumps = [f"h{a}->h{b}" for a, b in zip(hs, hs[1:]) if b - a > 1]
    r.check(not jumps, f"{name} : saut(s) de niveau de titre : {', '.join(jumps)}")

    imgs = re.findall(r"<img[^>]*>", s)
    r.check(all("alt=" in i for i in imgs), f"{name} : image(s) sans attribut alt")

    anon = 0
    for m in re.finditer(r"<a\s([^>]*)>(.*?)</a>", s, re.S):
        if not re.sub(r"<[^>]+>", "", m.group(2)).strip() and "aria-label" not in m.group(1):
            anon += 1
    r.check(anon == 0, f"{name} : {anon} lien(s) sans nom accessible")

    r.check('<html lang="' in s, f"{name} : attribut lang absent")
    r.check("skip-link" in s, f"{name} : skip-link absent")
    r.check("<main" in s, f"{name} : landmark <main> absent")
    r.check("focus-visible" in s, f"{name} : indicateur de focus absent")
    r.check("prefers-reduced-motion" in s, f"{name} : prefers-reduced-motion absent")

    # --- RGAA : contraste des opacites sur fond noir ---
    for label, pat, seuil in [
        ("footer-eco",  r"\.footer-eco\s*\{[^}]*rgba\(255,255,255,([\d.]+)\)", 4.5),
        ("footer-year", r"\.footer-year\s*\{[^}]*rgba\(255,255,255,([\d.]+)\)", 4.5),
    ]:
        m = re.search(pat, s)
        if m:
            ratio = contrast(flatten(float(m.group(1))), "#000000")
            r.check(ratio >= seuil,
                    f"{name} : contraste {label} {ratio:.2f}:1 < {seuil}:1 (opacite {m.group(1)})")

    # --- accent de marque sur fond sombre (puces, labels) ---
    m = re.search(r"--color-accent:\s*(#[0-9A-Fa-f]{6})", s)
    if m:
        ratio = contrast(m.group(1), "#000000")
        r.check(ratio >= 3.0,
                f"{name} : accent {m.group(1)} sur fond noir {ratio:.2f}:1 < 3:1",
                blocking=False)

    # --- SEO ---
    t = re.search(r"<title>(.*?)</title>", s)
    r.check(t is not None, f"{name} : <title> absent")
    if t:
        r.check(20 <= len(t.group(1)) <= 65,
                f"{name} : title {len(t.group(1))} car. (viser 20-65)", blocking=False)
    d = re.search(r'name="description" content="([^"]*)"', s)
    r.check(d is not None, f"{name} : meta description absente")
    if d:
        r.check(70 <= len(d.group(1)) <= 165,
                f"{name} : description {len(d.group(1))} car. (viser 70-165)", blocking=False)
    r.check('rel="canonical"' in s, f"{name} : canonical absent")
    r.check('property="og:image"' in s, f"{name} : og:image absent")
    r.check("hreflang" in s, f"{name} : hreflang absent (reporte, decision du 2026-08-03)",
            blocking=False)

    # --- maillage interne (sous-nav ancree) ---
    # Seuil abaisse de 3 a 1 : certains marches (PL, AT, LU) ont un V1 nettement
    # plus pauvre en blocs de contenu (voir README, section "Etat du parc"). Une
    # page fidele a un V1 court n'a legitimement qu'une ou deux sections.
    subnav = re.search(r'<nav class="subnav".*?</nav>', s, re.S)
    r.check(subnav is not None, f"{name} : sous-nav de maillage absente")
    if subnav:
        anchors = re.findall(r'href="#([^"]+)"', subnav.group(0))
        r.check(len(anchors) >= 1,
                f"{name} : sous-nav sans ancre")
        r.check(len(anchors) >= 3,
                f"{name} : sous-nav avec {len(anchors)} ancre(s), 3 recommandees",
                blocking=False)
        missing = [a for a in anchors if f'id="{a}"' not in s]
        r.check(not missing, f"{name} : ancre(s) de sous-nav sans cible : {missing}")

    # --- GEO / JSON-LD ---
    lds = re.findall(r'<script type="application/ld\+json">(.*?)</script>', s, re.S)
    types = []
    for b in lds:
        try:
            types.append(json.loads(b).get("@type"))
        except json.JSONDecodeError as e:
            r.check(False, f"{name} : JSON-LD invalide ({e})")
    for needed in ("Service", "WebPage"):
        r.check(needed in types, f"{name} : JSON-LD {needed} absent")
    # FAQPage non bloquant : plusieurs marches (PL, AT, LU) n'ont simplement pas
    # de FAQ structuree en V1 -- l'exiger partout pousserait a en inventer une.
    r.check("FAQPage" in types, f"{name} : JSON-LD FAQPage absent (V1 sans FAQ ?)",
            blocking=False)

    # --- medias ---
    hero = re.search(r'class="hero-(?:bg|media)"[^>]*><img src="([^"]+)"', s)
    if hero:
        u = hero.group(1)
        fichier = u.rsplit("/", 1)[-1].split("?")[0]
        # un UUID nu = visuel de bloc, dimensionne pour un conteneur, pas pour du plein cadre
        uuid_nu = re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                               fichier, re.I)
        r.check("/Stellantis/" in u or "/content/dam/" in u or not uuid_nu,
                f"{name} : hero servi depuis un visuel de bloc ({fichier[:20]}...) "
                f"-> pixellisation en plein cadre. Servir dans /Stellantis/ ou un asset HD nomme.")
    r.check("usine-a-sites-preproduction" not in s,
            f"{name} : reference au bucket de PREPRODUCTION")

    return r


def audit_content(path):
    """Controles sur la source, pas sur le rendu."""
    r = Report()
    page = json.loads(path.read_text(encoding="utf-8"))
    name = path.relative_to(ROOT)
    exp = page.get("footer", {}).get("legal_expire")
    if exp:
        d = datetime.date.fromisoformat(exp)
        r.check(d >= TODAY, f"{name} : mention legale EXPIREE le {exp}")
        r.check((d - TODAY).days > 30,
                f"{name} : mention legale expire dans {(d - TODAY).days} j ({exp})",
                blocking=False)
    return r


def main():
    themes = json.loads((ROOT / "themes/themes.json").read_text(encoding="utf-8"))
    files = sorted((ROOT / "dist").rglob("*.html"))
    if not files:
        print("Aucun artefact dans dist/. Lancer scripts/build.py d'abord.")
        sys.exit(1)

    blocking, warnings, checks = [], [], 0
    for f in files:
        r = audit(f, themes)
        blocking += r.blocking; warnings += r.warnings; checks += r.checks
    for f in sorted((ROOT / "content").rglob("*.json")):
        r = audit_content(f)
        blocking += r.blocking; warnings += r.warnings; checks += r.checks

    print(f"QA GATE — {len(files)} artefact(s), {checks} controles\n")
    if warnings:
        print(f"AVERTISSEMENTS ({len(warnings)}) — non bloquants")
        for w in warnings:
            print("  ~", w)
        print()
    if blocking:
        print(f"BLOQUANTS ({len(blocking)})")
        for b in blocking:
            print("  X", b)
        print("\nGATE : REFUSE — aucun push en back-office.")
        sys.exit(1)

    print("GATE : OK — artefacts autorises au push en back-office.")


if __name__ == "__main__":
    main()
