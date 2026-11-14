import io

import numpy as np
import pytest
from astropy.io import fits
from PIL import Image

from backend.science import Observation, header_cards


def test_wcs_known_reference_and_roundtrip(fixture_fits):
    obs = Observation.read(fixture_fits)
    pixel = obs.pixel("IMAGE", 2, 2)
    assert pixel["ra_deg"] == pytest.approx(180)
    assert pixel["dec_deg"] == pytest.approx(45)
    assert obs.locate(180, 45) == dict(x=2, y=2)
    with pytest.raises(ValueError, match="coverage"):
        obs.locate(190, 45)


def test_values_uncertainty_flags_and_no_subtraction(fixture_fits):
    obs = Observation.read(fixture_fits)
    pixel = obs.pixel("IMAGE", 2, 2)
    assert pixel["brightness"] == 14
    assert pixel["variance"] == 4
    assert pixel["uncertainty"] == 2
    assert pixel["zodi"] == 1
    assert pixel["flags"] == 5
    assert pixel["flag_bits"] == [0, 2]
    assert pixel["fits_x"] == pixel["fits_y"] == 3
    assert "snr" not in pixel


def test_invalid_variance_has_no_uncertainty(fixture_fits):
    obs = Observation.read(fixture_fits)
    assert obs.pixel("IMAGE", 0, 0)["uncertainty"] is None
    assert obs.pixel("IMAGE", 1, 0)["variance"] is None


def test_actual_timestamp_not_processing_date(fixture_fits):
    metadata = Observation.read(fixture_fits).metadata("test", fixture_fits.name)
    assert metadata["timestamp"]["value"] == "2025-04-28T16:16:34.491"
    assert metadata["timestamp"]["key"] == "DATE-OBS"
    assert metadata["release"] is None
    assert any("very small" in notice for notice in metadata["notices"])
    assert metadata["flag_definitions"][0]["key"] == "MP_TEST"


def test_tab_wavelength_and_bandwidth_known_answers(fixture_fits):
    obs = Observation.read(fixture_fits)
    assert obs.spectral is not None, obs.spectral_error
    pixel = obs.pixel("IMAGE", 2, 2)
    assert pixel["wavelength_um"] == pytest.approx(2.6)
    assert pixel["bandwidth_um"] == pytest.approx(.14)
    assert obs.spectral.sip is None
    metadata = obs.metadata("test", fixture_fits.name)
    assert metadata["spectral"]["min_um"] == pytest.approx(2)
    assert metadata["spectral"]["max_um"] == pytest.approx(3.5)


def test_spectral_sip_is_disabled(fixture_fits):
    with fits.open(fixture_fits, mode="update") as hdus:
        hdus["IMAGE"].header["A_ORDER"] = 2
        hdus["IMAGE"].header["B_ORDER"] = 2
        hdus["IMAGE"].header["A_2_0"] = .1
        hdus["IMAGE"].header["B_0_2"] = .1
    obs = Observation.read(fixture_fits)
    assert obs.spectral.sip is None
    assert obs.pixel("IMAGE", 2, 2)["wavelength_um"] == pytest.approx(2.6)


def test_mismatched_extensions_never_share_pixels(fixture_fits):
    with fits.open(fixture_fits, mode="update") as hdus:
        hdus["VARIANCE"].data = np.ones((3, 4))
    obs = Observation.read(fixture_fits)
    assert obs.pixel("IMAGE", 2, 2)["variance"] is None
    other = obs.pixel("VARIANCE", 1, 1)
    assert other["value"] == 1
    assert other["ra_deg"] is None
    assert other["brightness"] is None
    assert next(ext for ext in obs.extensions if ext["name"] == "PSF")["shape"] == [3, 5, 5]


def test_render_mask_and_y_orientation(fixture_fits):
    obs = Observation.read(fixture_fits)
    rendered = Image.open(io.BytesIO(obs.render("IMAGE", "linear", "gray", True, 0, 35)))
    assert rendered.size == (6, 6)
    pixels = np.asarray(rendered)
    assert pixels[3, 2, 3] == 0  # (x=2,y=2) maps to row 6-1-2
    assert pixels[5, 0, 0] == 0
    assert pixels[0, 5, 0] == 255


def test_missing_calibration_is_not_invented(fixture_fits):
    with fits.open(fixture_fits, mode="update") as hdus:
        del hdus["WCS-WAVE"]
    obs = Observation.read(fixture_fits)
    assert obs.spectral is None
    assert obs.pixel("IMAGE", 2, 2)["wavelength_um"] is None
    assert obs.metadata("test", "test.fits")["spectral"] is None


def test_no_observation_timestamp_inferred_from_date(fixture_fits):
    with fits.open(fixture_fits, mode="update") as hdus:
        del hdus["IMAGE"].header["DATE-OBS"]
    obs = Observation.read(fixture_fits)
    assert obs.metadata("test", "test.fits")["timestamp"] is None


def test_pixel_bounds_and_header_preservation(fixture_fits):
    obs = Observation.read(fixture_fits)
    assert next(card for card in header_cards(obs, "PRIMARY") if card["key"] == "SIMPLE")["value"] is True
    with pytest.raises(ValueError):
        obs.pixel("IMAGE", 6, 0)
    assert next(card for card in header_cards(obs, "IMAGE") if card["key"] == "DATE")["value"] == "2026-01-01T00:00:00"
