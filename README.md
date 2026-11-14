# SPHEREx Sky Explorer · Real-data science workspace

A Next.js App Router + TypeScript + Tailwind dashboard with a separate Python/FastAPI + Astropy scientific service. The application displays uploaded FITS measurements only. It contains no simulated sky or fabricated observation dates.

## Run locally

Use **Node.js 20.9+** and **Python 3.13**. The pinned Python packages are intended for a Python 3.13 virtual environment.

```bash
git clone https://github.com/M-Arham07/spherex-blink.git
cd spherex-blink
npm ci
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
```

Start the Python API in one terminal:

```bash
npm run backend
```

In a second terminal in the same folder, start Next.js:

```bash
BACKEND_URL=http://127.0.0.1:8000 npm run dev -- --port 3001
```

Open **http://127.0.0.1:3001**. The frontend proxies requests to the API on port 8000. If the app reports that the API is unavailable, check `curl http://127.0.0.1:3001/api/science/health`. On shells that do not support inline environment variables, put `BACKEND_URL=http://127.0.0.1:8000` in `.env.local` and run `npm run dev -- --port 3001`.

To preload the project’s reference observation (~68 MiB), run this from the project root, then refresh the app:

```bash
.venv/bin/python scripts/download_observation.py
```

You can also upload an uncompressed FITS file (up to 256 MiB), or set `SPHEREX_FITS_PATH=/absolute/path/file.fits` on the Python process before starting it. FITS data are stored in `backend/data/` by default; `SPHEREX_DATA_DIR` overrides that path. Local environment files and cached data are excluded from Git. For a Colab backend, set `BACKEND_URL` to the full private URL printed by the notebook and restart Next.js.

## Download several observations of one sky region

1. Open **Downloads** from Simple or Complex.
2. Choose **Cutout size** (3–60 arcmin). To get started without searching, click **Download sample** for two real observations of the same field. To download your own region, enter **RA and Dec in decimal degrees** under **Fixed sky region**. For the starter field, try RA `304.52129078`, Dec `39.07848168`.
3. Select an archive collection and click **Search IRSA at this position**. Filter by detector if desired; the detector number alone does not guarantee matching wavelengths.
4. Choose a count and click **Download N cutouts**. This takes the first matching results shown, downloading each at the same sky position and cutout size. **Add cutout** is still available for individual files.
5. Open **Observation library** to see successful downloads. Choose up to 12 observations and build a fixed-sky view to compare them. The download limit is separate from the 12-frame comparison limit.

Progress and failed files are shown in the app. **Stop after current file** preserves completed downloads. Keep the page open while the batch runs. Files go to the connected Python backend: your local cache when running locally, or the Colab runtime when using that backend.

## Simple and Complex views

The app starts in **Simple**: a guided layout based on the original Sky Motion Lab, with reference/current sky images, a timeline, automatic WCS registration and compatible-pair selection, difference/significance views, a detector wavelength slider, and a pixel inspector. It uses the same real scientific backend as the full workspace; there are no synthetic noise/drift controls or invented epochs.

Use the **Simple / Complex** switch in the header. **Complex** retains the complete dashboard, archive search, file inspector, custom sky grids, source charts, and candidate tools. Your view preference survives refresh. Switching views retains the mounted workspace and pauses playback in the view you leave. To change the simple field, expand **Change sky position**; for additional files, use **Load FITS file** or **Find more real observations**.

The Simple view auto-prepares cached observations. If only one real date exists, animation is disabled. Current-date choices are prechecked for wavelength, quality, and PSF overlap. Click **Subtract images** to run subtraction. Playback and Next/Previous use only matching dates for the chosen reference; incompatible dates stay visible but disabled. Choosing another reference automatically selects a compatible current date. If no real pair is available, the UI explains how to add coverage. Nothing is fabricated to make a control appear functional.

## Native observation viewer

- Loads and validates real FITS HDUs, preserving headers and each extension's independent shape.
- Renders IMAGE, VARIANCE, FLAGS, and ZODI with native pixel dimensions, nearest-neighbor enlargement, transparent missing values, zoom, pan, and a detector grid.
- Inspects original brightness, variance, sqrt(variance), flags and active bit indices, modeled zodiacal light, ICRS coordinates, wavelength, and bandwidth at a clicked pixel.
- Reads the primary celestial TAN/SIP WCS and the alternate spectral `W` WCS backed by `WCS-WAVE`. Spectral SIP is explicitly disabled following IRSA's reference tutorial. Wavelength and bandwidth units are converted to µm using the file's declared WCS units.
- Computes detector wavelength bounds from all pixels in bounded strips, rather than assuming full-mission spectral coverage.
- Locates an entered ICRS RA/Dec within the loaded exposure; reports no coverage outside it.
- Browses and searches every HDU's original headers, including table schemas and PSF cube dimensions. It does not misinterpret PSF planes as science frames.
- Offers grayscale, amber, and ice display palettes; linear, asinh, and logarithmic stretches; custom limits; and a conservative all-nonzero-flags mask. PNG downloads are processed display products, not science FITS exports.
- Includes accessible file loading, loading/error states, a field guide, responsive layouts, and keyboard pixel navigation.

## Data and provenance

The exact user-selected NASA/IPAC IRSA QR2 observation URL, filename, byte count, and pinned SHA-256 are in `backend/dataset.json`. The downloader verifies the checksum before installing the default. Uploaded bytes matching that checksum receive the same archive source link; other uploads are labeled as user supplied with unverified archive origin. Files are excluded from Git and remain on the local server.

The observation timestamp comes from `DATE-OBS` or explicitly identified observation-time alternatives; `DATE` (HDU creation time) is never substituted. Header release/version values are reported only when available. QR2 is taken from the verified reference archive path, not inferred from arbitrary filenames.

## Science workspace: Phases 2–5

All sidebar science sections are functional. Start with **Downloads** or select cached files in any science workspace. Enter ICRS coordinates, select up to 12 observations, and choose **Build fixed-sky view**. The region remains fixed when changing dates or wavelengths. A library row can open its native detector view. Uploading another file adds it to the library.

- **Wavelengths:** a 0.75–5 µm detector slider shows native pixels whose measured central wavelengths fall within the requested interval. Missing coverage is transparent. The alternate calibration-map mode displays the actual wavelength lookup. For a fixed-sky wavelength view, enable the interval filter and rebuild. The combined view uses inverse-variance weighting of compatible registered measurements, with no filling of missing sky coverage.
- **Timeline:** actual FITS observation timestamps, date selection, Previous/Next, Play/Pause, speed controls, shared brightness limits, and aligned-pair blinking. Frames are WCS-reprojected onto an explicit ICRS TAN grid. Playback uses distinct covered dates; fewer than two dates disables animation. A frame without usable coverage stays transparent. Clicking a source inspects the sky-grid pixel and measures the same sky position across selected observations.
- **Source measurements:** Plotly wavelength and time-series charts show background-subtracted aperture fluxes with measurement error bars and measured bandwidths. Photometry uses a two-native-pixel-radius aperture and a three-to-five-pixel background annulus. Invalid apertures and overly broad wavelength mixtures are excluded and reported.
- **Difference:** selects a reference and a new observation, checks units, flags, wavelength centers and bandwidths, matches approximate Gaussian PSFs using the median PSF_FWHM headers, and subtracts new − reference. Optional ZODI subtraction removes each native foreground model before registration; median-overlap background removal adjusts the remaining offset independently. Registered reference/new, signed difference, approximate significance, valid-overlap mask, and before-alignment native detector images are available. Clicking a derived image reports its actual numerical values.
- **Investigate:** separates positive/negative connected residual groups above a selected significance threshold and minimum pixel area. Candidate positions, peak significance, and edge status are displayed. Opposite-sign groups can form ambiguous two-epoch motion hypotheses with sky displacement and apparent velocity. A chosen hypothesis is tested for nearby significant residuals at the other selected epochs; unavailable or unmatched epochs remain explicit. SIMBAD links support manual catalog checks, not automatic identifications.
- **Archive:** uses the documented official SIA2 endpoint, DR1/QR3 wide/deep collections, and official center/size cutout parameters. Returns actual metadata, caches downloaded files, preserves source URLs/releases, and exposes errors without substitutes. Search results are capped at 100 by the UI (API permits 200); the response identifies a reached cap. Newly ingested data can lag in SIA2. Individual archive downloads may return HTTP 503; retry the requested cutout or choose another real exposure.

The backend recommends the selected pair with the largest compatible sky overlap. It does not assert that all observations in the library are scientifically interchangeable. Two files from the same OBSID/detector/time cannot be included together; this prevents double-counting full frames and their cutouts.

## Scientific assumptions and limits

- WCS-WAVE is a visualization approximation; precision work needs separate CWAVE/CBAND products. A single exposure does not contain a full source spectrum at each sky location.
- Native images retain detector orientation with FITS Y upwards. Registered images are north up, east left. Native and sky-grid pixel coordinates are distinct. Small cutouts stay visibly pixelated.
- Registered processing requires co-shaped IMAGE, VARIANCE, and FLAGS with declared brightness/squared-brightness units, plus valid celestial and spectral WCS. Missing requirements are rejected, not guessed.
- Registration uses bilinear `reproject_interp`. Measurement variance is propagated using the squared four-neighbor interpolation weights. Quality masks require valid contributing pixels. Resampling introduces covariance between neighboring output pixels. Gaussian smoothing propagates variance using the squared kernel but does not model the existing resampling covariance; significance is therefore approximate.
- Quality screening excludes nonzero bits except documented informational FULLSAMPLE (12) and SOURCE (21). This differs from the native viewer's optional conservative **all nonzero bits** display mask. Unknown bits are rejected. Header bit definitions remain inspectable.
- Comparison permits band-center offsets up to 25% of the narrower bandwidth and bandwidth differences up to 20% of the wider bandwidth, per sky pixel. This is an explicit approximation to spectral compatibility, not proof of identical full filter response. Gaussian PSF matching uses median header FWHM in arcseconds, not full spatially varying PSF kernels. Missing PSF_FWHM disables comparison.
- Optional median background fitting can suppress broad real variability; its estimation error and systematic calibration/foreground/PSF errors are absent from the displayed significance. No ZODI subtraction or correction is applied automatically.
- Inverse-variance wavelength mosaics are visualization products and do not homogenize PSFs or remove epoch variability. Samples are checked against a per-pixel spectral anchor before combination; different valid wavelengths are never silently mixed across a broad interval.
- Aperture fluxes use projection-plane pixel area as a local solid-angle approximation. Median-background uncertainty is approximated under independent Gaussian pixel noise. No PSF aperture correction, correlated-noise correction, or deblending is performed. Charts explicitly report unavailable samples; differing epochs/wavelengths can confound variability and spectral trends. These measurements are exploratory.
- Candidate significance is per pixel; adjacent groups contain correlated noise. Reported peak sigma is not a calibrated source significance or false-alarm probability. No global multiple-testing correction is applied. Gaussian PSF mismatch, calibration changes, variable objects, foregrounds, cosmic rays, and artifacts can generate residuals. Catalog links are manual searches; nothing is claimed to be a new object or Planet X.
- Motion hypotheses associate negative and positive residual lobes within a selected angular radius and are intrinsically ambiguous. Linear-path checks find the nearest positive residual within three sky-grid pixels; all comparisons share a reference and are correlated. They are not orbital fits, independent confirmations, or guaranteed source associations.
- Original observation times are preserved. DATE (file creation) is never substituted for DATE-OBS. Unknown releases/units remain explicit. Every on-screen measurement originates in a real uploaded/downloaded FITS file or a labeled processing result.
- This remains a trusted local application bound to loopback, without public-server authentication or user isolation. Disk files persist locally. Up to four registered sessions and four analyses are kept in memory; expired sessions must be rebuilt. Native observation arrays use a two-item memory cache; the grid is bounded to 256 × 256 and a workspace to 12 files.

## Verification

```bash
npm run typecheck
npm run build
npm run test:science
```

Tests use explicitly synthetic FITS files only as fixtures, never application data. They verify known-answer celestial WCS, wavelength/bandwidth `-TAB` mapping, spectral SIP removal, timestamp preservation, pixel and FITS coordinate conventions, original values, uncertainty, invalid variance, flag bits, transparent masking, image orientation, independent extension dimensions, absent calibration, file validation, caching, and API round trips.

Real-reference validation findings and the multi-observation validation are recorded in `docs/observation-report.md`. Native WCS transforms are serialized to avoid a reproduced Astropy 8.0.2 shared-WCS thread-safety crash; an isolated concurrent real-data regression test checks this. Browser verification uses native Python Playwright; see `scripts/test_browser.py` for the native viewer and `scripts/test_workspace_browser.py` for the real multi-observation workflow. Set `SPHEREX_APP_URL` if Next.js is running on a port other than 3000. The multi-observation check defaults to port 3001 and requires the real cutouts cached during development, or another library containing a compatible real pair. Install the optional test dependency with `.venv/bin/python -m pip install playwright`, then `.venv/bin/python -m playwright install chromium`. Keep both servers running before invoking it.

## Google Colab

For Nova Velorum, run the [standalone notebook](docs/spherex-colab-standalone.ipynb) or paste the [standalone script](docs/spherex-colab-standalone.py) into a Colab cell. It embeds the backend, prints the private API URL, then downloads and registers the observations. No separate ZIP is needed. Regenerate both files after backend edits with `python3 scripts/generate_standalone_colab.py`.

1. Upload [the notebook](docs/spherex-colab.ipynb) to Colab and run its cell. When prompted, upload [the backend bundle](docs/spherex-colab-backend.zip). The [plain Python cell](scripts/colab_backend_cell.py) is also available.
2. The cell downloads three full official IRSA exposures, previews a measured difference, and prints a temporary `BACKEND_URL` including a private path. Copy the **whole** line to `.env.local` at the project root.
3. Restart the local frontend with `npm run dev -- --port 3001`. Next.js uses the remote API while the Colab runtime and tunnel remain connected. Remove the line and restart to return to the local backend.

If running the script with `!python`, upload the ZIP through the Colab Files sidebar to `/content/spherex-colab-backend.zip` first. The upload picker only works when the code runs directly in a notebook cell. Shell mode saves the preview to `/content/spherex-colab/difference.png`.

The printed URL grants access to the notebook API; keep it private. This is a temporary interactive notebook workflow, not persistent hosting. See the [Colab FAQ](https://research.google.com/colaboratory/faq.html) and [Quick Tunnel limits](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

The preview uses a 160 × 160 grid at the same angular scale as the app. Full exposures cover more sky than the cutouts, but do not resolve finer detail. The starter field demonstrates measured residuals, not a verified astrophysical change. For a documented brightness change, see [NASA’s 3I/ATLAS observations](https://science.nasa.gov/photojournal/nasas-spherex-examines-comet-3i-atlass-coma/) and [the IRSA observation table](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/index.html).

## Sources

- [Official SPHEREx data product descriptions](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/)
- [Official IRSA SPHEREx tutorial and spectral WCS recipe](https://github.com/Caltech-IPAC/irsa-tutorials/blob/main/tutorials/spherex/spherex_intro.md)
- [Astropy WCS API](https://docs.astropy.org/en/stable/api/astropy.wcs.WCS.html)
- [SPHEREx archive access documentation](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/)

## Bulk download (200 native cutouts)

The resumable batch downloader fetches official IRSA DR1/QR3 observations around the original field (ICRS RA 304.52129078°, Dec +39.07848168°):

```bash
.venv/bin/python scripts/download_bulk_observations.py --count 200 --size-deg .2 --workers 8
```

A 0.2-degree cutout is approximately 117 × 117 native SPHEREx pixels; edge cutouts can be rectangular. Measurements are not JPEG-compressed, resampled or synthetically enhanced. All available detector-4 exposures are prioritized; the remaining selections spread other wavelength bands through the actual observation dates. These are 200 files, not a claim of 200 matching spectral observations or 200 distinct epochs.

Progress, source URLs, SHA-256 file IDs, dimensions, sizes, timestamps, release, and measured central wavelengths/bandwidths are recorded in `backend/data/bulk-200/manifest.json`. Canonical FITS files and metadata are installed in the existing `backend/data` library. Hard links avoid duplicating the downloaded FITS storage on the same filesystem. Re-running resumes the batch and retries unavailable files; an unsuccessful download is not replaced with generated data.

The science workspace still processes up to 12 selected files per session. The full library remains available for selection. Simple view prioritizes the active detector and nearby measured central wavelengths when choosing a subset from a large library. Comparisons retain their pixel-level compatibility checks.

As of the official IRSA documentation dated November 12, 2026, search uses DR1/QR3. Existing QR2 files remain readable; QR2 direct downloads remain available through February 2027, while QR2 is no longer searchable through SIA2.

### Automatic comparison

Simple view now runs **Find & compare automatically** on load. The backend searches the local library beyond the 12-frame display limit, rejects repeated exposures and equal/missing epochs, projects observations onto a shared ICRS WCS grid, and checks wavelength centers and bandwidths per overlapping pixel. Candidate pairs must retain usable pixels after quality masking and Gaussian PSF matching. A successful automatic session displays up to 12 observations, prioritizes wavelengths near the selected sky position, and chooses a reference with the most compatible dates (earliest on ties), then the partner with the largest usable overlap for that reference.

Brightness is converted to the common calibrated MJy/sr unit. The app enables ZODI subtraction by default in Simple and Complex: each observation uses its own IMAGE − ZODI before WCS registration. The optional background correction then removes the remaining median B−A offset over compatible pixels. PSF matching smooths to the larger FITS PSF_FWHM. The displayed A/B images are the matched arrays actually used in the subtraction. No arbitrary gain is fitted to already calibrated measurements.

Numbered red/blue markers and the residual list highlight connected positive/negative regions with at least three pixels above the selected approximate significance threshold (default 7σ in Simple). Simple shows the five strongest matches unless Show all matches is enabled. Clicking a marker or list entry reads its measured position and residual. The five-step status panel shows completion, overlap, PSF width, and background correction. These are unverified residuals: resampling correlations, calibration errors, and spatial PSF mismatch limit significance.

API: `POST /workspace/auto-session` accepts `{ra, dec, size?, scale?, preferred_id?}` and returns a regular workspace session plus search counts. A missing compatible pair returns an explicit 422 response; incompatible bands are never forced into a subtraction. Reprojection uses surface-brightness units as described in the [Reproject documentation](https://reproject.readthedocs.io/en/stable/celestial.html).

### Zodiacal foreground correction

**Subtract zodiacal light (ZODI)** is on by default in both comparison views. Simple rebuilds and recomputes when toggled; Complex invalidates the previous session and requires **Build fixed-sky view** again. The correction also applies to registered frames, coadds, source-aperture measurements, candidate detection, and tracking within that session. Native detector/wavelength inspection continues to show the original measurements.

Each ZODI plane must match IMAGE dimensions and declare compatible brightness units. Nonfinite model pixels are excluded from overlap. Missing/malformed models cause a clear error or exclusion from automatic pair selection; there is no silent uncorrected fallback. Both corrected and uncorrected session caches have distinct IDs. Original arrays and FITS files are untouched.

The API enables this with `subtract_zodi: true` in `/workspace/sessions` or `/workspace/auto-session`; its default remains false for existing API clients. The session grid records `subtract_zodi`, and analysis metadata records `zodi_subtracted`. Measurement variance is propagated as before; it does **not** include uncertainty or covariance in the zodiacal model. See the [official SPHEREx product description](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/) for the supplied ZODI layer.

### Simplified comparison interface

Simple view offers both the original side-by-side images and a before/after reveal image. Drag the center divider or use the range slider underneath; both support keyboard control. The signed difference remains below it. Dates/playback, processing evidence, highlighted-change lists, and More options are collapsed by default. ZODI subtraction stays enabled, and the pixel inspector appears after selecting a pixel.

The **Current observation** slider changes only B through compatible, timestamp-ordered observations; A stays fixed. The slider is disabled when only one compatible current date exists. **Mark changes on images** overlays the same measured residual coordinates on either layout. The difference/significance panel stays visible. Markers open the difference measurement in the pixel inspector.
