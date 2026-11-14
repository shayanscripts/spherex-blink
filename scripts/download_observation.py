"""Download the exact user-selected IRSA observation and verify its pinned SHA-256."""
import hashlib
import json
import os
from pathlib import Path
from urllib.request import urlopen

root = Path(__file__).resolve().parent.parent
reference = json.loads((root / 'backend/dataset.json').read_text())
directory = Path(os.environ.get('SPHEREX_DATA_DIR', root / 'backend/data'))
directory.mkdir(parents=True, exist_ok=True)
target = directory / 'spherex_full.fits'
if target.exists():
    with target.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() == reference['sha256']:
            print(f'Already downloaded and verified: {target}')
            raise SystemExit(0)
partial = target.with_suffix('.fits.part')
try:
    with urlopen(reference['url'], timeout=120) as response, partial.open('wb') as stream:
        while chunk := response.read(1024 * 1024):
            stream.write(chunk)
            if stream.tell() > 256 * 1024 * 1024:
                raise ValueError('Download exceeds 256 MiB.')
    with partial.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != reference['sha256']:
        raise ValueError('Archive file checksum changed. Review the new file before updating dataset.json.')
    partial.replace(target)
    print(f'Downloaded and verified: {target}')
except BaseException:
    partial.unlink(missing_ok=True)
    raise
