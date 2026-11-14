# Phase 1 · real observation inspection

Inspected the exact user-selected [IRSA QR2 FITS observation](https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/2025W18_1B/l2b-v20-2025-240/4/level2_2025W18_1B_0023_2D4_spx_l2b-v20-2025-240.fits). File size: 71,634,240 bytes. SHA-256: `93967a91ac6293fd546262a1bbb31c44a19571182d7eac5809c9c1d404769358`.

| Field | Actual file value |
|---|---|
| OBSID | 2025W18_1B_0023_2 |
| DETECTOR | 4 |
| DATE-OBS | 2025-04-28T16:16:34.491 |
| TIMESYS | UTC |
| MJD-OBS | 60793.678176979 |
| IMAGE HDU creation DATE | 2025-09-18T06:35:59.746 |
| PRIMARY VERSION | 6.4+psffix1 |
| Release | QR2, established by the source archive path; absent in inspected release header aliases |
| INSTRUME / TELESCOP | Absent; mission attribution comes from the verified archive source |

| HDU | Shape (NumPy axis order) | Units / structure |
|---|---|---|
| PRIMARY | No data | Metadata |
| IMAGE | 2040 × 2040 | MJy / sr |
| FLAGS | 2040 × 2040 | Integer bit fields |
| VARIANCE | 2040 × 2040 | MJy2 / sr2 |
| ZODI | 2040 × 2040 | MJy / sr |
| PSF | 121 × 101 × 101 | Cube; independently inspected |
| WCS-WAVE | One-row binary table | X: 13J; Y: 20J; VALUES: 520E, TDIM=(2,13,20) |

The celestial WCS is RA/Dec TAN-SIP. Alternate WCS A describes detector coordinates. Alternate WCS W uses two WAVE-TAB axes, referencing WCS-WAVE, for wavelength and bandwidth in µm. The spectral SIP coefficients are disabled as specified in the official IRSA tutorial; celestial SIP remains enabled.

Evaluating the spectral WCS over all native detector pixels yields central wavelengths from **2.3980312347 to 3.8628580570 µm**, and bandwidths from **0.0350565091 to 0.1079664975 µm**. These are actual lookup-table bounds, not a hardcoded mission-wide wavelength range. The lookup is intended for visualization, not precision photometry.

## Example native pixel

At zero-based detector `(1020, 1020)` / FITS `(1021, 1021)`:

| Measurement | Readout |
|---|---|
| RA (ICRS) | 304.521290783936° |
| Dec (ICRS) | +39.078481682402° |
| IMAGE | 0.919340610504 MJy/sr |
| VARIANCE | 0.000825247029 (MJy/sr)² |
| sqrt(VARIANCE) | 0.028727113131 MJy/sr |
| ZODI | 0.062325563282 MJy/sr |
| FLAGS | 2097152; active bit 21 |
| Header bit 21 definition | MP_SOURCE: Pixel mapped to a known source |
| Central wavelength | 3.010280292306 µm |
| Bandwidth | 0.087495135381 µm |

This flag is informational: the optional all-nonzero-bits mask is deliberately conservative and can discard valid measurements. A nonzero flag is not automatically evidence of an invalid science pixel. No source SNR is inferred from the brightness/uncertainty ratio.

IMAGE contains 4,158,586 finite measurements out of 4,161,600 detector pixels; nonfinite values render transparently. No zodiacal model subtraction or other scientific modification is performed. IMAGE's 1st–99th percentile display interval is approximately 0.28968–16.97857 MJy/sr; this is a visual stretch, not a science filter.

The full-resolution reference observation loads successfully. No additional observations, epochs, source spectra, difference products, or candidate detections are introduced in Phase 1.

## Multi-observation workspace validation

The workspace was extended with eight additional **real IRSA cutouts** (nine files including the original). Their exact original archive URLs, SHA-256 file IDs, and observation times are recorded in `docs/workspace-observations.json`. These are local cached datasets, excluded from Git; no mock epochs were added. Some archive requests returned HTTP 503 and were reported as failures.

A 96 × 96 TAN grid at ICRS (304.52129078°, +39.07848168°), with 6.15 arcsec/grid-pixel, supports a real comparison of:

- Reference: 2025-04-28T16:20:52.353 UTC.
- New: 2025-10-29T07:13:13.772 UTC.
- Compatible valid overlap: 2,898 pixels / 31.4453125% of the grid.
- Target median Gaussian PSF FWHM: 6.1043278279 arcsec.
- Median new-minus-reference overlap offset removed: −0.0088488393 MJy/sr.

Compatibility is evaluated per sky pixel, so the derived images have a diagonal strip of real wavelength-compatible coverage and transparent excluded areas. Alignment does not manufacture coverage beyond this strip. Difference and approximate significance products were rendered and pixel-inspected in the browser. Positive/negative connected residual groups and tentative path checks were exercised; none are asserted to be real moving objects or discoveries.

Native-browser validation exercised detector wavelength selection, inverse-variance wavelength mosaics, registered playback controls, background-subtracted aperture spectra/time-series charts, before/after registration views, signed differences, significance maps, candidate tables, cross-epoch path tests, and mobile navigation. The production Next.js build and 25 scientific/API/regression tests pass.

A concurrent native-code crash was reproduced in Astropy 8.0.2's shared WCS-WAVE transform during browser testing. WCS calls now share a reentrant serialization lock. An isolated subprocess regression test checks repeated four-thread transforms against sequential results on the actual reference FITS file. This prevents the demonstrated WCSLIB race without changing the calibration values.
