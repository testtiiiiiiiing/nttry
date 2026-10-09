import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from winimage.updates import download_updates, load_manifest, microsoft_url


class Response(io.BytesIO):
    def geturl(self):
        return 'https://download.microsoft.com/test.msu'


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.content = b'verified test package'
        self.digest = hashlib.sha256(self.content).hexdigest()
        self.manifest = self.root / 'updates.json'
        self.manifest.write_text(json.dumps({'version': 1, 'updates': [{'url': 'https://download.microsoft.com/test.msu', 'filename': 'test.msu', 'sha256': self.digest}]}))

    def test_verified_download_and_cache_reuse(self):
        opener = Mock(side_effect=lambda *a, **k: Response(self.content))
        files = download_updates(self.manifest, self.root / 'cache', emit=lambda s: None, opener=opener)
        self.assertEqual(Path(files[0]).read_bytes(), self.content)
        again = download_updates(self.manifest, self.root / 'cache', emit=lambda s: None, opener=opener)
        self.assertEqual(again, files)
        self.assertEqual(opener.call_count, 1)

    def test_bad_checksum_does_not_create_package_or_leave_partial_file(self):
        with self.assertRaises(ValueError):
            download_updates(self.manifest, self.root / 'cache', emit=lambda s: None, opener=lambda *a, **k: Response(b'wrong'))
        self.assertEqual(list((self.root / 'cache').iterdir()), [])

    def test_corrupt_cache_is_not_trusted(self):
        cache = self.root / 'cache'
        cache.mkdir()
        target = cache / (self.digest + '-test.msu')
        target.write_bytes(b'corrupt')
        download_updates(self.manifest, cache, emit=lambda s: None, opener=lambda *a, **k: Response(self.content))
        self.assertEqual(target.read_bytes(), self.content)

    def test_http_credentials_untrusted_domain_and_path_traversal_rejected(self):
        for url in ('http://download.microsoft.com/test', 'https://user:password@download.microsoft.com/test', 'https://download.microsoft.com.evil.test/test'):
            with self.assertRaises(ValueError):
                microsoft_url(url)
        data = json.loads(self.manifest.read_text())
        data['updates'][0]['filename'] = '../test.msu'
        self.manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            load_manifest(self.manifest)


if __name__ == '__main__':
    unittest.main()
