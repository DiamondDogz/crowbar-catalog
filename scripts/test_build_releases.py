"""Tests de build_releases.py, sans réseau : python -m unittest discover scripts"""
import unittest

import build_releases as b

SPEC = {"platform": "windows", "repo": "x/y", "tagPrefix": "windows-", "asset": "*.zip"}


def rel(tag, date, pre=False, draft=False, assets=("Sakura.zip",)):
    return {"tag_name": tag, "published_at": date, "prerelease": pre, "draft": draft, "body": "notes", "html_url": "page",
            "assets": [{"name": n, "browser_download_url": "https://dl/" + n, "size": 10, "digest": "sha256:" + "a" * 64} for n in assets]}


class Resolve(unittest.TestCase):
    def test_stable_et_beta(self):
        releases = [rel("windows-1.2-test", "2026-11-04T00:00:00Z", pre=True),
                    rel("windows-1.1.4", "2026-11-01T00:00:00Z"),
                    rel("windows-1.1.3", "2026-10-01T00:00:00Z")]
        r = b.resolve(releases, SPEC)
        self.assertEqual(r["stable"]["version"], "1.1.4")
        self.assertEqual(r["beta"]["version"], "1.2-test")
        self.assertTrue(r["beta"]["prerelease"])
        self.assertEqual(r["stable"]["sha256"], "a" * 64)

    def test_ignore_brouillons_autres_tags_et_releases_sans_archive(self):
        releases = [rel("windows-2.0", "2026-12-01T00:00:00Z", draft=True),
                    rel("linux-9", "2026-11-20T00:00:00Z"),
                    rel("windows-1.9", "2026-11-10T00:00:00Z", assets=("source.tar.gz",)),
                    rel("windows-1.1.4", "2026-11-01T00:00:00Z")]
        r = b.resolve(releases, SPEC)
        self.assertEqual(r["stable"]["tag"], "windows-1.1.4")
        self.assertEqual(r["beta"]["tag"], "windows-1.1.4")

    def test_fichier_sha256_prioritaire(self):
        spec = {"platform": "linux", "repo": "h/s", "asset": "*-linux-x86_64.tar.gz", "checksum": "{asset}.sha256"}
        releases = [rel("v1.0", "2026-10-01T00:00:00Z", assets=("S-linux-x86_64.tar.gz", "S-linux-x86_64.tar.gz.sha256"))]
        read = lambda url, accept=None: ("b" * 64 + "  S-linux-x86_64.tar.gz\n").encode()
        r = b.resolve(releases, spec, read)
        self.assertEqual(r["stable"]["sha256"], "b" * 64)
        self.assertEqual(r["stable"]["version"], "v1.0")

    def test_build_signale_un_runtime_sans_archive(self):
        catalog = {"games": [{"id": "jeu", "runtimes": [SPEC]}]}
        result, problems = b.build(catalog, fetch=lambda repo: [rel("windows-1", "2026-01-01T00:00:00Z", assets=("autre.7z",))])
        self.assertEqual(result["games"]["jeu"], {})
        self.assertIn("autre.7z", problems[0])


if __name__ == "__main__":
    unittest.main()
