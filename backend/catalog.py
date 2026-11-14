"""Positional cross-reference against the CDS SIMBAD catalog."""
from functools import lru_cache
from math import isfinite
from urllib.parse import urlencode

import httpx

RADIUS_ARCSEC = 15
MAX_OBJECTS = 8
HOSTS = ('https://simbad.cfa.harvard.edu', 'https://simbad.cds.unistra.fr')


class CatalogUnavailable(Exception):
    pass


@lru_cache(maxsize=256)
def search_nearby(ra: float, dec: float) -> dict:
    # Values are validated numeric coordinates; no user text enters the ADQL.
    point = f"POINT('ICRS', {ra:.7f}, {dec:.7f})"
    catalog_point = "POINT('ICRS', b.ra, b.dec)"
    query = f"""
        SELECT TOP {MAX_OBJECTS + 1} b.main_id, b.otype, t.description, b.sp_type,
               DISTANCE({catalog_point}, {point}) AS distance_deg
        FROM basic AS b LEFT JOIN otypedef AS t ON b.otype = t.otype
        WHERE CONTAINS({catalog_point},
                       CIRCLE('ICRS', {ra:.7f}, {dec:.7f}, {RADIUS_ARCSEC/3600:.10f})) = 1
        ORDER BY distance_deg
    """
    params = dict(request='doQuery', lang='adql', format='json', query=query)
    for host in HOSTS:
        try:
            response = httpx.get(f'{host}/simbad/sim-tap/sync', params=params, timeout=5)
            response.raise_for_status()
            rows = response.json()['data']
            if not isinstance(rows, list):
                raise ValueError('Invalid SIMBAD response.')
            objects = []
            for name, code, description, spectral_type, distance in rows[:MAX_OBJECTS]:
                separation = float(distance) * 3600
                if not isinstance(name, str) or not isfinite(separation) or not 0 <= separation <= RADIUS_ARCSEC + 1e-5:
                    raise ValueError('Invalid SIMBAD object.')
                objects.append(dict(
                    name=name.strip(), type=description or code or 'Type not listed',
                    spectral_type=spectral_type.strip() if spectral_type else None,
                    separation_arcsec=separation,
                    url=f'{host}/simbad/sim-id?{urlencode({"Ident": name.strip()})}',
                ))
            return dict(radius_arcsec=RADIUS_ARCSEC, objects=objects, truncated=len(rows) > MAX_OBJECTS)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            continue
    raise CatalogUnavailable()
