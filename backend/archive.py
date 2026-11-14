"""Verified IRSA SIA2 discovery and allowlisted official cutout downloads."""
import hashlib
import io
from collections.abc import Callable
from pathlib import Path
from threading import Event
from tempfile import NamedTemporaryFile
import time
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


class ArchiveUnavailable(RuntimeError):
    pass


class DownloadCancelled(RuntimeError):
    pass


def download(url: str, directory: Path, ra: float | None, dec: float | None, size: float,
             *, progress: Callable[[int, int | None], None] | None = None,
             cancel: Event | None = None) -> tuple[Path,str]:
    def check_cancelled():
        if cancel is not None and cancel.is_set():
            raise DownloadCancelled()
    check_cancelled()
    validate_url(url)
    params = dict(center=f'{ra},{dec}', size=str(size)) if ra is not None and dec is not None else {}
    request_url = str(httpx.URL(url, params=params))
    key = hashlib.sha256(request_url.encode()).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'archive-{key}.fits'
    if target.exists(): return target, request_url
    transient = {429, 500, 502, 503, 504}
    deadline = time.monotonic() + 100
    with httpx.Client() as client:
        for attempt in range(3):
            partial = None
            try:
                check_cancelled()
                if progress:progress(0,None)
                timeout = min(30., max(1., deadline - time.monotonic()))
                with client.stream('GET', request_url, timeout=timeout) as response:
                    response.raise_for_status()
                    length=response.headers.get('Content-Length','')
                    total=int(length) if length.isdecimal() and len(length)<16 and response.headers.get('Content-Encoding','identity')=='identity' else None
                    if progress:progress(0,total)
                    with NamedTemporaryFile(dir=directory, prefix=f'archive-{key}-', suffix='.part', delete=False) as stream:
                        partial = Path(stream.name)
                        for chunk in response.iter_bytes(64*1024):
                            check_cancelled()
                            if time.monotonic() > deadline:
                                raise httpx.ReadTimeout('FITS download timed out.')
                            stream.write(chunk)
                            if progress:progress(stream.tell(),total)
                            if stream.tell() > 256*1024*1024:
                                raise ValueError('Archive file exceeds 256 MiB.')
                # Admission and FITS validation are performed by register before library use.
                check_cancelled()
                partial.replace(target)
                return target, request_url
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                retryable = not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code in transient
                if not retryable:
                    raise
                delay = 2**attempt
                if isinstance(exc, httpx.HTTPStatusError):
                    retry_after = exc.response.headers.get('Retry-After', '')
                    if retry_after.isdecimal() and len(retry_after) < 10:
                        delay = max(delay, int(retry_after))
                if attempt == 2 or time.monotonic()+delay+1 >= deadline:
                    status = f' (HTTP {exc.response.status_code})' if isinstance(exc, httpx.HTTPStatusError) else ''
                    raise ArchiveUnavailable(f'IRSA temporarily could not serve this FITS file{status}. Try again in a few minutes.') from exc
                if cancel is None:time.sleep(delay)
                elif cancel.wait(delay):check_cancelled()
            finally:
                if partial is not None:
                    partial.unlink(missing_ok=True)
