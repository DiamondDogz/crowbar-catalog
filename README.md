# Crowbar catalog

This repository tells [Crowbar](https://github.com/DiamondDogz/crowbar) which PS4RT games exist and where to download their runtimes.

Version française : [README.fr.md](README.fr.md).

- **`catalog.json`**: the list of games and their runtimes, edited by hand.
- **`releases.json`**: generated automatically every hour.
  - For each runtime, it gives the latest **stable** version and the latest **beta**, with the download address, the size and the SHA-256 checksum.
  - It also lists the 10 most recent versions, so players can pick a specific one.
  - It is the only file Crowbar reads: players never query the GitHub API.

Nothing in this repository is a game, a key or a Sony file: only names, links and checksums.

## Adding or updating a port

1. Publish your runtime as a **GitHub release** on your own repository, with an archive ready to unzip (`.zip` for Windows, `.tar.gz` for Linux). Mark test versions as **Pre-release**: they only reach players who chose the beta channel.
2. Propose a change to `catalog.json` (a *pull request*) that adds your runtime to the game's entry:

```json
{
  "platform": "windows",
  "repo": "YourName/Your-Port",
  "tagPrefix": "windows-",
  "asset": "*.zip",
  "checksum": "{asset}.sha256",
  "maintainer": "YourName",
  "launch": "ps4rt-launch"
}
```

3. The automatic check on the pull request shows whether your archive is found. Once the change is accepted, your port appears in Crowbar within the hour.

After that, new versions of your runtime are picked up **on their own**: just publish a new release.

## Fields

| Field | Role |
| --- | --- |
| `platform` | `windows` or `linux` |
| `repo` | The runtime's GitHub repository, `owner/name` |
| `tagPrefix` | Optional: only keep releases whose tag starts with this (`windows-1.1.4`) |
| `asset` | Pattern of the file to download from the release (`*.zip`, `*-linux-x86_64.tar.gz`) |
| `checksum` | Optional: a checksum file published next to it (`{asset}.sha256`). Otherwise, Crowbar uses the checksum GitHub provides |
| `maintainer` | Shown to players before installation |
| `launch` | How to launch the game; Crowbar also recognises it from the runtime's files. See below |

The `launch` values:

- `ps4rt-launch`: `scripts/ps4rt_launch.py --game <folder>`.
- `ps4rt-run`: `run.py` with `PS4RT_GAME_DIR`, for runtimes shipped with the Ravn launcher.
- `native-play`: a native launcher without Python, `bin/… Launcher.exe --play`, which launches the game named in `out/launcher.ini`.

On Windows, Python scripts run with the runtime's own Python in `python/`.

A game entry can also have these fields:

- `titleIds`: the CUSA numbers it recognises.
- `match`: an expression that recognises the title in `param.sfo`.
- `requiredVersion`: the minimum game version the runtime needs.
- `languages`: the languages of the game's text, as PS4 system language numbers (0 Japanese, 1 English, 2 French, 3 Spanish, 4 German…). Without it, Crowbar reads them from the trophy file.
- `features`: settings specific to this runtime (`framerate`, `outlines`).
- `name`, `genre`, `glow` and `synopsis`, shown in Crowbar.

## For catalog maintainers

- Run the script's tests with `python -m unittest discover -s scripts`.
- `python scripts/build_releases.py` regenerates `releases.json` locally.
- On a public repository with no activity for 60 days, GitHub suspends scheduled workflows. A commit or a manual run (Actions tab, "Run workflow") turns them back on.
