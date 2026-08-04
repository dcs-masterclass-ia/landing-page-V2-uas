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
avec `Service` + `FAQPage` + `WebPage`, sous-nav d'au moins 3 ancres toutes resolues, hero non servi depuis un visuel de bloc
(un UUID S3 nu = image dimensionnee pour un conteneur, pixellisee en plein cadre), aucune reference au bucket de preproduction, mentions legales non expirees.

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
| 2026-08-03 | SPOTICAR, STELLANTIS &YOU, LANCIA et LEAPMOTOR sortis du scope (26 sites) |

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

## Extraction V1 (scripts/extract.py)

Produit un **brouillon** `content/<site>/<page>.draft.json` a partir d'une page V1 en ligne.

```bash
pip install beautifulsoup4 requests
python3 scripts/extract.py --batch sites.example.csv
python3 scripts/extract.py --url <URL> --brand citroen --market FR
python3 scripts/extract.py --file fixtures/page.html --url <URL> --brand citroen --market FR
```

Le brouillon n'est **jamais publiable tel quel**. Tout ce que la machine ne peut pas decider
seule est marque `TODO_ARBITRAGE` : c'est volontaire, un trou visible vaut mieux qu'un texte
invente. Workflow : extraire -> arbitrer les TODO -> renommer en `.json` -> `build` -> `qa`.

Ce que l'extracteur fait automatiquement :

- repare les concatenations cassees du V1 (fin de liste soudee au paragraphe suivant)
- deduplique le fil d'Ariane et retire le lien de la page courante
- exclut header / footer / nav du corpus, sinon les titres de pied de page remontent en blocs
- classe les blocs (`two_col`, `etapes`, `faq`) d'apres leur contenu
- **n'affecte jamais un visuel V1 au hero** : `TODO_HERO_STELLANTIS`, a servir dans `/Stellantis/`
- ignore les plans de site et le signale dans le rapport
- extrait la date d'expiration des mentions legales, que le QA Gate controle ensuite

## Inventaire et decouverte

`inventory/sites.csv` — 67 sites dans le scope. `inventory/hors-scope.csv` — 26 sites ecartes.

```bash
python3 scripts/discover.py --limit 5      # echantillon de test
python3 scripts/discover.py --country FR
python3 scripts/discover.py                # tout le parc (~2 min avec --delay 1)
```

Produit `inventory/pages.csv`, entree directe de `scripts/extract.py --batch`.
La decouverte suit robots.txt -> sitemap.xml (index compris) -> liens de la page d'accueil.
Les slugs de LP sont reconnus dans les 7 langues du parc ; les pages fonctionnelles
(cookies, mentions, PDF, accessibilite) sont exclues. Un site sans resultat est marque
`a_inspecter_manuellement` plutot que silencieusement ignore.

## Etat du parc

**67 sites, 9 pays, 9 marques — toutes couvertes par un theme.** Aucun site bloque.
Le Portugal est deja en V2, absent du parc.

Hors scope (decisions du 2026-08-03) : SPOTICAR (10), STELLANTIS &YOU (8), LANCIA (5),
LEAPMOTOR (3), soit 26 sites conserves dans `inventory/hors-scope.csv` plutot que
supprimes, pour pouvoir etre reintegres sans refaire l'inventaire.

| Marque | Sites | | Cluster | Sites | Pays |
|---|---|---|---|---|---|
| Citroen | 9 | | fr | 26 | BE, FR, LU |
| Opel | 9 | | nl | 9 | BE |
| Peugeot | 9 | | es | 9 | ES |
| Alfa Romeo | 8 | | de | 8 | AT, DE |
| DS Automobiles | 8 | | it | 8 | IT |
| Fiat | 7 | | pl | 6 | PL |
| Jeep | 7 | | en | 1 | UK |
| Abarth | 5 | | | | |
| Fiat Professional | 5 | | | | |

| Pays | BE | ES | LU | FR | IT | PL | DE | AT | UK |
|---|---|---|---|---|---|---|---|---|---|
| Sites | 18 | 9 | 9 | 8 | 8 | 6 | 5 | 3 | 1 |

**Cluster francophone** : 26 sites en francais sur 3 pays. Avec un wording repris a
l'identique et sans hreflang, les pages FR / BE-fr / LU d'une meme marque seront
identiques. Arbitrage assume, consigne ici pour memoire.

**Belgique** : 18 sites, chaque marque existant en `reprise.*` (fr) et `overname.*` (nl).
C'est le marche le plus lourd du parc.

**Moteurs de rendu** : 8 marques sur `templates/shared.html.j2`, Peugeot sur
`templates/peugeot.html.j2`. Les deux consomment **le meme schema de contenu** : un JSON
de page se rend dans l'un ou l'autre sans etre reecrit, le champ `template` decide.
Le nombre de pages par site sera connu apres `scripts/discover.py`.

Le template Peugeot a sa propre grammaire : radius 0 partout, hero plein cadre sombre,
bandeau de confiance en 4 colonnes, splits 50/50 alternes, FAQ en deux colonnes,
titres en capitales. Les blocs `two_col`, `etapes`, `comparatif`, `cote` et `faq` y ont
un rendu different mais consomment les memes champs.
