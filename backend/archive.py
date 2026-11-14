"""Verified IRSA SIA2 discovery and allowlisted official cutout downloads."""
import hashlib
import io
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import numpy as np
from astropy.io.votable import parse_single_table
from astropy.time import Time

SIA = 'https://irsa.ipac.caltech.edu/SIA'
COLLECTIONS = ('spherex_dr1', 'spherex_dr1_deep', 'spherex_qr3', 'spherex_qr3_deep')


def validate_url(url: str) -> str:
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.netloc != 'irsa.ipac.caltech.edu' or parts.query or parts.fragment
            or not parts.path.startswith('/ibe/data/spherex/') or not parts.path.endswith('.fits')
            or '..' in parts.path or '%' in parts.path):
        raise ValueError('Only direct official IRSA SPHEREx FITS URLs are accepted.')
    return url


def search(ra: float, dec: float, radius: float, collection: str, limit: int) -> dict:
    with httpx.Client(timeout=60) as client:
        response = client.get(SIA, params=dict(COLLECTION=collection, POS=f'CIRCLE {ra} {dec} {radius}', MAXREC=limit))
        response.raise_for_status()
    table = parse_single_table(io.BytesIO(response.content)).to_table(use_names_over_ids=True)
    rows = []
    def value(row, name):
        v = row[name] if name in table.colnames else None
        if v is None or np.ma.is_masked(v): return None
        return v.item() if isinstance(v, np.generic) else v
    for row in table:
        url = str(value(row, 'access_url') or '')
        try: validate_url(url)
        except ValueError: continue
        mjd = value(row, 't_min')
        rows.append(dict(url=url, obs_id=value(row, 'obs_id'), collection=value(row, 'obs_collection'),
                         timestamp=Time(float(mjd), format='mjd', scale='utc').isot if mjd is not None else None,
                         mjd=mjd, min_um=float(value(row, 'em_min'))*1e6 if value(row,'em_min') is not None else None,
                         max_um=float(value(row, 'em_max'))*1e6 if value(row,'em_max') is not None else None,
                         detector=urlsplit(url).path.split('/')[-2]))
    rows.sort(key=lambda r: (r['mjd'] is None, r['mjd'] or 0, r['url']))
    return dict(results=rows, capped=len(table)>=limit, endpoint=SIA,
                note='Archive band bounds describe the exposure; local wavelength coverage is checked after loading.')


def download(url: str, directory: Path, ra: float | None, dec: float | None, size: float) -> tuple[Path,str]:
    validate_url(url)
    params = dict(center=f'{ra},{dec}', size=str(size)) if ra is not None and dec is not None else {}
    request_url = str(httpx.URL(url, params=params))
    key = hashlib.sha256(request_url.encode()).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'archive-{key}.fits'
    if target.exists(): return target, request_url
    partial = directory / f'archive-{key}.part'
    try:
        with httpx.Client(timeout=120) as client, client.stream('GET', request_url) as response:
            response.raise_for_status()
            with partial.open('wb') as stream:
                for chunk in response.iter_bytes(1024*1024):
                    stream.write(chunk)
                    if stream.tell() > 256*1024*1024: raise ValueError('Archive file exceeds 256 MiB.')
        # Admission and FITS validation are performed by register before library use.
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target, request_url
