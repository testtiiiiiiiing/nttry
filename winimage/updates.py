"""Parallel, checksum-verified Microsoft package downloads with a reusable cache."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import uuid


def microsoft_url(url):
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or '').lower()
    allowed = host == 'download.microsoft.com' or host.endswith('.windowsupdate.com') or host.endswith('.dl.delivery.mp.microsoft.com')
    if parsed.scheme != 'https' or not allowed or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Gli aggiornamenti devono provenire da destinazioni HTTPS Microsoft consentite.')
    return url


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        microsoft_url(new_url)
        return super().redirect_request(request, fp, code, message, headers, new_url)


def checksum(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_manifest(path):
    source = Path(path)
    if source.stat().st_size > 1024**2:
        raise ValueError('Manifest superiore a 1 MiB.')
    data = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Il manifest deve essere un oggetto JSON.')
    rows = data.get('updates', [])
    if data.get('version') != 1 or not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise ValueError('Manifest: versione 1 e da 1 a 100 aggiornamenti richiesti.')
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Voce manifest non valida.')
        microsoft_url(row.get('url', ''))
        if not isinstance(row.get('sha256'), str) or not re.fullmatch(r'[0-9a-fA-F]{64}', row['sha256']):
            raise ValueError('Ogni download richiede lo SHA-256 atteso dalla fonte attendibile.')
        filename = row.get('filename', '')
        if not isinstance(filename, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+\.(cab|msu)', filename, re.I):
            raise ValueError('Nome pacchetto CAB/MSU non valido.')
    return rows


def download_updates(manifest, cache, emit=print, workers=3, opener=None):
    rows = load_manifest(manifest)
    cache = Path(cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    opener = opener or urllib.request.build_opener(CheckedRedirect()).open
    def fetch(row):
        digest = row['sha256'].lower()
        target = cache / (digest + '-' + row['filename'])
        if target.is_file() and checksum(target) == digest:
            emit('Cache verificata: ' + row['filename'])
            return str(target)
        temporary = cache / (uuid.uuid4().hex + '.part')
        try:
            request = urllib.request.Request(row['url'], headers={'User-Agent': 'WinImageStudio/2'})
            with opener(request, timeout=60) as response, temporary.open('xb') as output:
                microsoft_url(response.geturl())
                size = 0
                while chunk := response.read(1024**2):
                    size += len(chunk)
                    if size > 8 * 1024**3:
                        raise ValueError('Pacchetto superiore al limite di 8 GiB.')
                    output.write(chunk)
            if checksum(temporary) != digest:
                raise ValueError('SHA-256 non corrispondente: ' + row['filename'])
            temporary.replace(target)
            emit('Scaricato e verificato: ' + row['filename'])
            return str(target)
        finally:
            temporary.unlink(missing_ok=True)
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), 4))) as pool:
        # Return in manifest order, independent of download completion order.
        return list(pool.map(fetch, rows))
