import json
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import add_runtime as ar  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SDK = Path(os.environ.get("CROWBAR_SDK", ROOT / "sdk"))
if not (SDK / "crowbar_sdk").is_dir():
    SDK = ROOT.parent / "crowbar-sdk"

BODY = """### Game

valkyria-revolution

### Game name

_No response_

### CUSA ids

_No response_

### GitHub repository

HekamiAeon/valkyria-revolution-ps4rt

### Release file

valkyria-revolution-linux-x86_64-*.tar.gz

### System

linux

### Checksum file

{asset}.sha256

### Tag prefix

_No response_

### Maintainer

HekamiAeon

### Rules

- [X] My release contains no game file, no key, no firmware and no third-party binary I may not redistribute
"""


class Form(unittest.TestCase):
    def test_parse_and_validate(self):
        f = ar.parse_form(BODY)
        self.assertEqual(f["repo"], "HekamiAeon/valkyria-revolution-ps4rt")
        self.assertEqual(f["platform"], "linux")
        self.assertEqual(f["name"], "")
        self.assertEqual(ar.validate_form(f), [])

    def test_rejects_hostile_values(self):
        f = ar.parse_form(BODY.replace("HekamiAeon/valkyria-revolution-ps4rt", "a/b; rm -rf /").replace("linux\n", "mac\n").replace("valkyria-revolution-linux-x86_64-*.tar.gz", "../../etc/passwd"))
        self.assertEqual(len(ar.validate_form(f)), 3)


class CatalogFile(unittest.TestCase):
    def test_dumps_keeps_the_hand_written_style(self):
        text = (ROOT / "catalog.json").read_text(encoding="utf-8")
        self.assertEqual(ar.dumps(json.loads(text)) + "\n", text)

    def test_apply_replaces_same_repo_and_platform(self):
        cat = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
        f = dict(ar.parse_form(BODY), _trophies=True)
        entry, what = ar.apply(cat, f, "x")
        game = next(g for g in cat["games"] if g["id"] == "valkyria-revolution")
        linux = [r for r in game["runtimes"] if r["platform"] == "linux"]
        self.assertEqual(len(linux), 1)
        self.assertEqual(linux[0], entry)
        self.assertTrue(entry["trophies"])
        self.assertEqual(entry["launch"], "crowbar-json")
        self.assertIn("remplacé", what)

    def test_new_game_needs_name_and_ids(self):
        cat = {"games": []}
        f = dict(ar.parse_form(BODY), game="my-game")
        with self.assertRaises(ValueError):
            ar.apply(cat, f, "x")
        f.update(name="My Game", titleIds="CUSA00001, CUSA00002")
        ar.apply(cat, f, "x")
        self.assertEqual(cat["games"][0]["titleIds"], ["CUSA00001", "CUSA00002"])


class Release(unittest.TestCase):
    def test_latest_release_with_matching_file(self):
        rels = [{"tag_name": "v2", "draft": True, "assets": [{"name": "a-2.tar.gz"}]},
                {"tag_name": "windows-1", "assets": [{"name": "a-1.tar.gz"}]},
                {"tag_name": "v1", "assets": [{"name": "notes.txt"}, {"name": "a-1.tar.gz"}]}]
        rel, asset = ar.latest_release("o/r", "v", "a-*.tar.gz", rels)
        self.assertEqual(rel["tag_name"], "v1")
        with self.assertRaises(LookupError):
            ar.latest_release("o/r", "", "*.zip", rels)

    def test_parse_sha256(self):
        h = "a" * 64
        self.assertEqual(ar.parse_sha256(f"{h}  file.tar.gz\n", "file.tar.gz"), h)
        self.assertEqual(ar.parse_sha256(h, "x"), h)
        self.assertIsNone(ar.parse_sha256(f"{h}  other\n", "x"))


@unittest.skipUnless((SDK / "crowbar_sdk").is_dir(), "crowbar-sdk not checked out")
class EndToEnd(unittest.TestCase):
    def run_with(self, manifest, extra=None):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            rt = d / "rt"
            (rt / "bin").mkdir(parents=True)
            (rt / "bin" / "ps4rt").write_text("x")
            if manifest:
                (rt / "crowbar.json").write_text(json.dumps(manifest))
            for name, data in (extra or {}).items():
                (rt / name).write_bytes(data)
            arc = d / "valkyria-revolution-linux-x86_64-1.0.tar.gz"
            with tarfile.open(arc, "w:gz") as t:
                t.add(rt, arcname="runtime")
            import hashlib
            sha = hashlib.sha256(arc.read_bytes()).hexdigest()
            rel = {"tag_name": "v1.0", "assets": [
                {"name": arc.name, "size": arc.stat().st_size, "browser_download_url": "dl://a"},
                {"name": arc.name + ".sha256", "size": 80, "browser_download_url": "dl://s"}]}
            body, report = d / "body.md", d / "report.md"
            body.write_text(BODY)
            cat = d / "catalog.json"
            shutil.copy(ROOT / "catalog.json", cat)
            fake_dl = lambda url, dest, size: (shutil.copy(arc, dest), sha)[1]
            with mock.patch.object(ar, "ROOT", d), mock.patch.object(ar, "latest_release", return_value=(rel, rel["assets"][0])), \
                    mock.patch.object(ar, "download", side_effect=fake_dl), \
                    mock.patch.object(ar, "http_get", return_value=f"{sha}  {arc.name}\n".encode()):
                code = ar.main(["--body", str(body), "--report", str(report), "--sdk", str(SDK)])
            return code, report.read_text(), json.loads(cat.read_text())

    GOOD = {"crowbar": 1, "name": "Valkyria Linux", "game": "valkyria-revolution", "titleIds": ["CUSA06810"],
            "launch": {"linux": ["bin/ps4rt", "--game", "{game}"]}, "features": {"trophies": True}}

    def test_good_release(self):
        code, report, cat = self.run_with(self.GOOD)
        self.assertEqual(code, 0, report)
        self.assertIn("SHA-256", report)
        game = next(g for g in cat["games"] if g["id"] == "valkyria-revolution")
        self.assertEqual(next(r for r in game["runtimes"] if r["platform"] == "linux")["launch"], "crowbar-json")

    def test_release_without_manifest_or_with_game_files(self):
        code, report, _ = self.run_with(None)
        self.assertEqual(code, 1)
        self.assertIn("crowbar.json", report)
        code, report, _ = self.run_with(self.GOOD, {"eboot.bin": b"x"})
        self.assertEqual(code, 1)
        self.assertIn("release.game-file", report)


if __name__ == "__main__":
    unittest.main()
