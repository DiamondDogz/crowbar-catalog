import unittest

from build_components import pick


class Pick(unittest.TestCase):
    def test_archive_generique(self):
        assets = [
            {"name": "mpv-dev-x86_64-20261021-git-1a2b3c4.7z"},
            {"name": "mpv-x86_64-v3-20261021-git-1a2b3c4.7z"},
            {"name": "mpv-x86_64-20261021-git-1a2b3c4.7z"},
            {"name": "ffmpeg-x86_64-git-abc.7z"},
        ]
        self.assertEqual(pick(assets)["name"], "mpv-x86_64-20261021-git-1a2b3c4.7z")

    def test_rien(self):
        self.assertIsNone(pick([{"name": "mpv-i686-20261021-git-1a2b3c4.7z"}]))


if __name__ == "__main__":
    unittest.main()
