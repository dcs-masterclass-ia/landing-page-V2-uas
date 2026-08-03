# Retoma V2 — pipeline de deploiement multi-marques

Industrialisation des landing pages V2 sur les marches Stellantis.
**Le contenu est une donnee, le HTML est un rendu.** Aucun texte n'est ecrit dans un template.

## Chaine

```
content/<site>/<page>.json  ─┐
themes/themes.json          ─┼─> scripts/build.py ─> dist/<site>/<page>.html
templates/<tpl>.html.j2     ─┘                              │
                                                            v
                                                    scripts/qa.py  (GATE)
                                                            │
                                                     go / no-go BO
```

| Commande | Effet |
|---|---|
| `pip install jinja2` | dependance unique |
| `python3 scripts/build.py` | construit tout dans `dist/` |
| `python3 scripts/build.py citroen-fr` | construit un seul site |
| `python3 scripts/qa.py` | QA Gate — **exit 1** si un controle bloquant echoue |

## Regles structurantes

1. **Rien n'est genere en prose libre.** Le contenu vit dans `content/`, valide par schema.
2. **Aucune couleur en dur.** Les themes sortent de `themes/themes.json`. Un theme = accent + radius.
3. **Le hero se sert dans `/Stellantis/`.** Les dossiers numeriques S3 sont dimensionnes pour des
   conteneurs, pas pour du plein cadre : les y piocher produit un hero pixelise.
4. **Les plans de site ne sont jamais repris en V2.** Le maillage passe par la sous-nav ancree.
5. **Le QA Gate est bloquant.** Aucun artefact ne part en back-office sans un `exit 0`.
6. **Le registre porte l'idempotence.** `registry/registry.json` sait ce qui est deja pousse.
   Le back-office n'ayant pas d'API, c'est la seule protection contre les doublons.

## Controles du QA Gate

**Bloquants** — un seul <h1>, aucun saut de niveau Hn, tout `<img>` avec alt, tout lien avec un nom
accessible, `lang` / skip-link / `<main>` / focus visible / `prefers-reduced-motion`, contraste WCAG AA
sur les opacites de pied de page, title / description / canonical / og:image presents, JSON-LD valide
avec `Service` + `FAQPage` + `WebPage`, sous-nav d'au moins 3 ancres toutes resolues, hero issu de la
bibliotheque HD, aucune reference au bucket de preproduction, mentions legales non expirees.

**Avertissements** — longueurs title/description hors plage, contraste accent sur fond sombre,
hreflang absent, mention legale expirant sous 30 jours.

## Decisions actees

| Date | Decision |
|---|---|
| 2026-08-03 | Wording V1 repris a l'identique ; seules les corrections techniques et RGAA sont appliquees |
| 2026-08-03 | Plans de site jamais repris en V2 |
| 2026-08-03 | Correctif de contraste dans le template : opacites pied de page `.45 -> .62` et `.30 -> .55` |
| 2026-08-03 | hreflang reporte — cartographie des marches indisponible |
| 2026-08-03 | Maillage interne par sous-nav ancree (modele Peugeot) |

## Dettes ouvertes

- **Bucket de police** : `site-peugeot-test` est un chemin de test servi en production.
- **Logos blancs** : aucune declinaison blanche pour le pied de page ; `filter: invert()` en attendant.
- **Dimensions des medias** : la bibliotheque ne porte ni largeur, ni hauteur, ni poids.
- **Accent Jeep** : `#3D4F2F` non confirme officiellement.
- **GEO** : aucune donnee chiffree citable dans les pages. La data transactionnelle Autobiz est le
  levier non exploite.
- **Preproduction** : le logo Opel pointe vers `usine-a-sites-preproduction` (Opel PT et Opel FR).

## Push en back-office

Le BO n'expose pas d'API : l'ecriture se fait par navigateur. Sequence imposee —
`build` -> `qa` (exit 0) -> creation en **brouillon** par lots de 15-25 -> recette -> publication
validee explicitement. Le registre est mis a jour apres chaque lot.
