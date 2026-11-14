"""Download a resumable, verified library of real IRSA SPHEREx cutouts.

Run from the project root. No synthetic data, resampling or lossy compression.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
import numpy as np
from astropy.io.votable import parse_single_table
from astropy import log
from backend.archive import download, validate_url
from backend.science import Observation
log.setLevel('ERROR')


def save_json(path,value):
    temporary=path.with_suffix('.json.tmp');temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temporary.replace(path)


def discover(collection,ra,dec):
    with httpx.Client(timeout=120) as client:
        r=client.get('https://irsa.ipac.caltech.edu/SIA',params={'COLLECTION':collection,'POS':f'CIRCLE {ra} {dec} 0.001','MAXREC':2000});r.raise_for_status()
    table=parse_single_table(io.BytesIO(r.content)).to_table(use_names_over_ids=True)
    rows=[]
    for row in table:
        url=str(row['access_url'])
        try:validate_url(url)
        except ValueError:continue
        mjd=row['t_min'];mjd=None if np.ma.is_masked(mjd) else float(mjd)
        rows.append(dict(url=url,obs_id=str(row['obs_id']),mjd=mjd,detector=urlsplit(url).path.split('/')[-2],collection=collection))
    print(f'Discovered {len(rows)} {collection} images',flush=True)
    return rows


def choose(rows,count):
    # Prefer detector 4, then spread other bands through the date range.
    unique={}
    for row in rows:
        key=(row['obs_id'],row['detector'])
        # DR1 and QR3 represent distinct release windows; avoid duplicate products.
        if key not in unique or row['collection']=='spherex_dr1':unique[key]=row
    ordered=sorted(unique.values(),key=lambda r:(r['mjd'] or 0,r['detector']))
    priority=[r for r in ordered if r['detector']=='4']
    remaining=[r for r in ordered if r['detector']!='4']
    n=max(0,count-len(priority))
    selected_rest=[remaining[i] for i in np.linspace(0,len(remaining)-1,min(n,len(remaining)),dtype=int)] if n and remaining else []
    selected=(priority+selected_rest)[:count]
    selected_urls={r['url'] for r in selected}
    # Keep reserves for corrupt, uncovered or unavailable products.
    return selected+[r for r in ordered if r['url'] not in selected_urls]


def fetch(row,directory,ra,dec,size):
    last=None
    for attempt in range(5):
        try:
            path,request_url=download(row['url'],directory,ra,dec,size)
            return row,path,request_url,None
        except Exception as exc:
            last=str(exc)
            if attempt<4:time.sleep(min(20,2**attempt))
    return row,None,None,last


def admit(row,path,request_url,data_dir):
    obs=Observation.read(path)
    if not obs.spatial or not obs.spectral:raise ValueError('Celestial or wavelength calibration unavailable')
    pos=obs.locate(ARGS.ra,ARGS.dec)
    pixel=obs.pixel('IMAGE',pos['x'],pos['y'])
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    canonical=data_dir/f'{digest}.fits'
    if not canonical.exists():
        try:os.link(path,canonical)
        except OSError:
            import shutil
            shutil.copyfile(path,canonical)
    filename=Path(urlsplit(row['url']).path).name
    meta=obs.metadata(digest,filename)
    release=urlsplit(row['url']).path.split('/')[4].upper()
    meta['center_wavelength_um']=pixel['wavelength_um']
    meta['center_bandwidth_um']=pixel['bandwidth_um']
    meta['source_url']=request_url
    meta['provenance']='Downloaded from the official NASA/IPAC IRSA SPHEREx archive; native-resolution IRSA cutout.'
    meta['release']=meta['release'] or dict(key='Archive path',value=release,extension='IRSA')
    meta['notices']=[n for n in meta['notices'] if not n.startswith('SPHEREx provenance')]
    record=dict(filename=filename,archive=dict(url=request_url,original_url=row['url'],release=release),metadata=meta)
    save_json(data_dir/f'{digest}.json',record)
    return dict(id=digest,url=row['url'],cutout_url=request_url,filename=filename,bytes=canonical.stat().st_size,
                detector=row['detector'],shape=meta['shape'],timestamp=(meta['timestamp'] or {}).get('value'),release=release,
                center_wavelength_um=pixel['wavelength_um'],center_bandwidth_um=pixel['bandwidth_um'],path=str(canonical))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count',type=int,default=200);parser.add_argument('--ra',type=float,default=304.52129078)
    parser.add_argument('--dec',type=float,default=39.07848168);parser.add_argument('--size-deg',type=float,default=.2)
    parser.add_argument('--workers',type=int,default=4)
    ARGS=parser.parse_args()
    data_dir=Path(os.environ.get('SPHEREX_DATA_DIR',ROOT/'backend/data'));directory=data_dir/'bulk-200';directory.mkdir(parents=True,exist_ok=True)
    manifest_path=directory/'manifest.json';discovery_path=directory/'discovery.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else dict(requested=ARGS.count,ra=ARGS.ra,dec=ARGS.dec,size_deg=ARGS.size_deg,images=[],failures=[])
    if (manifest['ra'],manifest['dec'],manifest['size_deg'])!=(ARGS.ra,ARGS.dec,ARGS.size_deg):raise SystemExit('Existing batch uses different coordinates or cutout size.')
    manifest['images']=[item for item in manifest['images'] if Path(item['path']).is_file()]
    if len(manifest['images'])>=ARGS.count:
        print(f'Already complete: {len(manifest["images"])} verified cutouts');raise SystemExit(0)
    if discovery_path.exists():rows=json.loads(discovery_path.read_text())
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(discover,c,ARGS.ra,ARGS.dec) for c in ('spherex_dr1','spherex_qr3')]
            rows=sum((f.result() for f in futures),[])
        save_json(discovery_path,rows)
    completed={r['url'] for r in manifest['images']};queue=[r for r in choose(rows,ARGS.count) if r['url'] not in completed]
    print(f'Available unique exposures: {len(queue)+len(completed)}; already verified: {len(completed)}',flush=True)
    start=time.monotonic();pending={};position=0
    with ThreadPoolExecutor(max_workers=ARGS.workers) as pool:
        while len(manifest['images'])<ARGS.count and (position<len(queue) or pending):
            while len(pending)<min(ARGS.workers,ARGS.count-len(manifest['images'])) and position<len(queue):
                row=queue[position];position+=1;future=pool.submit(fetch,row,directory,ARGS.ra,ARGS.dec,ARGS.size_deg);pending[future]=row
            future=next(as_completed(pending));pending.pop(future);row,path,request_url,error=future.result()
            if not error:
                try:
                    item=admit(row,path,request_url,data_dir)
                    if not any(i['id']==item['id'] for i in manifest['images']):manifest['images'].append(item)
                    print(f'[{len(manifest["images"]):03d}/{ARGS.count}] D{item["detector"]} {item["timestamp"]} {item["shape"][1]}x{item["shape"][0]} {item["bytes"]/1048576:.2f} MiB',flush=True)
                except Exception as exc:error=str(exc)
            if error:
                manifest['failures'].append(dict(url=row['url'],error=error));print(f'RETRY EXHAUSTED / INVALID: {row["url"]}: {error}',flush=True)
            manifest['elapsed_seconds']=round(time.monotonic()-start,1);manifest['total_bytes']=sum(i['bytes'] for i in manifest['images'])
            save_json(manifest_path,manifest)
    manifest['complete']=len(manifest['images'])>=ARGS.count;save_json(manifest_path,manifest)
    print(json.dumps(dict(complete=manifest['complete'],verified=len(manifest['images']),bytes=manifest['total_bytes'],failed_attempts=len(manifest['failures']),manifest=str(manifest_path))),flush=True)
    raise SystemExit(0 if manifest['complete'] else 2)
