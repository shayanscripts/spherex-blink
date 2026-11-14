"""Golden checks for the real user-selected observation; skipped if not downloaded."""
import hashlib
import json
from pathlib import Path

import pytest

from backend.science import Observation

REFERENCE = Path(__file__).resolve().parents[1] / "data/spherex_full.fits"


@pytest.mark.skipif(not REFERENCE.exists(), reason="Reference FITS has not been downloaded")
def test_real_reference_file_and_measurements():
    manifest = json.loads((REFERENCE.parent.parent / "dataset.json").read_text())
    with REFERENCE.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == manifest["sha256"]
    obs = Observation.read(REFERENCE)
    assert obs.arrays["IMAGE"].shape == (2040, 2040)
    assert obs.headers["IMAGE"]["DATE-OBS"] == "2025-04-28T16:16:34.491"
    assert obs.headers["IMAGE"]["DETECTOR"] == 4
    pixel = obs.pixel("IMAGE", 1020, 1020)
    assert pixel["ra_deg"] == pytest.approx(304.521290783936, abs=1e-9)
    assert pixel["dec_deg"] == pytest.approx(39.07848168240153, abs=1e-9)
    assert pixel["brightness"] == pytest.approx(.9193406105041504)
    assert pixel["uncertainty"] == pytest.approx(.028727113131022552)
    assert pixel["wavelength_um"] == pytest.approx(3.0102802923061702)
    assert pixel["bandwidth_um"] == pytest.approx(.08749513538091776)
    assert pixel["flag_bits"] == [21]


@pytest.mark.skipif(not REFERENCE.exists(), reason='Reference FITS has not been downloaded')
def test_concurrent_real_tab_transforms_do_not_crash_or_corrupt():
    # Run the former native-code crash in isolation so it produces a test failure,
    # rather than taking down pytest itself if the WCSLIB regression returns.
    import subprocess
    import sys
    code = '''
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
from backend.science import Observation
obs=Observation.read(Path("backend/data/spherex_full.fits"))
x=np.arange(10000).reshape(100,100)%2040;y=x.copy()
expected=obs.spectral_values(x,y)[0]
def read(_):
    for i in range(20):
        actual=obs.spectral_values(x,y)[0]
        np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-12)
with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(read,range(4)))
'''
    result=subprocess.run([sys.executable,'-X','faulthandler','-c',code],capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stdout+result.stderr
