# Catalogue Crowbar

Ce dépôt dit à [Crowbar](https://github.com/DiamondDogz/crowbar-launcher) quels jeux PS4RT existent et où télécharger leurs runtimes.

- **`catalog.json`** : la liste des jeux et de leurs runtimes, modifiée à la main.
- **`releases.json`** : généré automatiquement toutes les heures. Pour chaque runtime, il donne la dernière version **stable** et la dernière **bêta**, avec l'adresse de téléchargement, la taille et l'empreinte SHA-256. Il liste aussi les 10 dernières versions, pour que les joueurs puissent en choisir une précise. C'est le seul fichier que Crowbar lit : les joueurs n'interrogent jamais l'API GitHub.

Rien de ce dépôt n'est un jeu, une clé ou un fichier de Sony : seulement des noms, des liens et des empreintes.

## Ajouter ou mettre à jour un port

1. Publiez votre runtime en **release GitHub** sur votre propre dépôt, avec une archive prête à dézipper (`.zip` pour Windows, `.tar.gz` pour Linux). Marquez les versions de test comme **Pre-release** : elles n'iront qu'aux joueurs qui ont choisi le canal bêta.
2. Proposez une modification de `catalog.json` (une *pull request*) qui ajoute votre runtime dans la fiche du jeu :

```json
{
  "platform": "windows",
  "repo": "VotrePseudo/Votre-Port",
  "tagPrefix": "windows-",
  "asset": "*.zip",
  "checksum": "{asset}.sha256",
  "maintainer": "VotrePseudo",
  "launch": "ps4rt-launch"
}
```

3. La vérification automatique de la pull request montre si votre archive est bien trouvée. Une fois la modification acceptée, votre port apparaît dans Crowbar dans l'heure.

Les nouvelles versions de votre runtime sont ensuite prises en compte **toutes seules** : il suffit de publier une nouvelle release.

## Les champs

| Champ | Rôle |
| --- | --- |
| `platform` | `windows` ou `linux` |
| `repo` | Dépôt GitHub du runtime, `propriétaire/nom` |
| `tagPrefix` | Facultatif : ne garder que les releases dont le tag commence ainsi (`windows-1.1.4`) |
| `asset` | Motif du fichier à télécharger dans la release (`*.zip`, `*-linux-x86_64.tar.gz`) |
| `checksum` | Facultatif : fichier d'empreinte publié à côté (`{asset}.sha256`). Sinon, Crowbar utilise l'empreinte fournie par GitHub |
| `maintainer` | Affiché aux joueurs avant l'installation |
| `launch` | Façon de lancer le jeu, reconnue aussi d'après les fichiers du runtime. `ps4rt-launch` = `scripts/ps4rt_launch.py --game <dossier>` ; `ps4rt-run` = `run.py` avec `PS4RT_GAME_DIR` (runtimes livrés avec le launcher Ravn) ; `native-play` = launcher natif sans Python, `bin/… Launcher.exe --play`, qui lance le jeu indiqué dans `out/launcher.ini`. Sous Windows, avec le Python de `python/` |

Pour une fiche de jeu : `titleIds` (les CUSA reconnus), `match` (expression reconnaissant le titre du `param.sfo`), `requiredVersion` (version minimale du jeu exigée par le runtime), `features` (réglages propres à ce runtime : `framerate`, `outlines`), puis `name`, `genre`, `glow` et `synopsis`, affichés dans Crowbar.

## Pour les mainteneurs du catalogue

- Les tests du script se lancent avec `python -m unittest discover -s scripts`.
- `python scripts/build_releases.py` régénère `releases.json` localement.
- Sur un dépôt public sans activité pendant 60 jours, GitHub suspend les tâches planifiées. Un commit ou un lancement manuel (onglet Actions, « Run workflow ») les réactive.
