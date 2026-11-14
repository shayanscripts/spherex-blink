# SPHEREx Blink · SkyMotion Explorer

Explore real NASA SPHEREx FITS observations, compare the same sky region on two dates, and inspect where it appears to have changed. The app uses a Next.js frontend and a Python/FastAPI backend with Astropy and Reproject.

| What you want to know | Where to look |
| --- | --- |
| What got brighter or fainter? | **Simple → Motion Explorer → Subtract images** |
| Could something have moved? | **What changed? → Possible motion** |
| Is there a known object nearby? | Click a numbered marker or choose it under **Look up an object** |
| What does the source's infrared spectrum look like? | Click a marker, then **View spectral fingerprint** |
| How do I add more dates or wavelengths? | **Downloads** |
| Where are the original pixel values and FITS headers? | **Complex → Explore / Data Inspector** |

A marker is evidence that a patch changed in the subtraction. A motion arrow is a suggested association between two patches. A nearby catalog object or a similar spectrum can help investigate the change, but neither identifies its cause on its own.

## Run locally

Requirements: **Node.js 20.9+**, npm, and **Python 3.13**. Commands below use a Unix shell.

```bash
git clone https://github.com/M-Arham07/spherex-blink.git
cd spherex-blink
npm ci
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
```

Start the Python API from the project root in one terminal:

```bash
npm run backend
```

In a second terminal, start the frontend:

```bash
BACKEND_URL=http://127.0.0.1:8000 npm run dev -- --port 3001
```

Open [http://127.0.0.1:3001](http://127.0.0.1:3001). Next.js forwards science requests to port 8000. On shells without inline environment assignment, set `BACKEND_URL=http://127.0.0.1:8000` in `.env.local` before starting Next.js. On Windows, create the venv with `py -3.13 -m venv .venv` and use `.venv\Scripts\python.exe` for pip and for `-m uvicorn backend.main:app --host 127.0.0.1 --port 8000`.

Check the backend and frontend proxy separately if the app cannot connect:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:3001/api/science/health
```

| Setting | Where to set it | Purpose |
| --- | --- | --- |
| `BACKEND_URL` | Next.js environment or `.env.local` | Python API URL; defaults to `http://127.0.0.1:8000` |
| `SPHEREX_DATA_DIR` | Python process environment | FITS cache directory; defaults to `backend/data/` |
| `SPHEREX_FITS_PATH` | Python process environment | Optional path to an existing FITS file |

The local app binds to loopback. Environment files and cached FITS data are excluded from Git. To preload the original verified QR2 reference (~68 MiB), run `.venv/bin/python scripts/download_observation.py` and refresh. This gives you **one observation**; use the two-file sample for a comparison. You can also upload an uncompressed FITS file up to 256 MiB.

## First comparison: download the sample and find a change

1. In **Simple → Downloads**, choose **Native resolution · cutout**, pick **12 arcmin**, and click **Download sample**. This requests two real DR1 observations of the same field (RA `304.52129078°`, Dec `+39.07848168°`).
2. Click **Open in Motion Explorer**. The app searches the library for compatible observations and prepares a reference (A) and a current observation (B).
3. Use the **Current observation** slider to change B, or choose another reference under **Dates & playback**. Open **Side by side** or **Before / after** to inspect the images. Pinch, Ctrl + scroll, or use the zoom controls to zoom the aligned images together. **Original FITS coverage** shows each file's native field with independent zoom; a cutout can show less sky than a full exposure.
4. Click **Subtract images**. Under **What changed?**, choose **Difference** for brightness changes or **Significance** for change relative to estimated noise. Blue marks where B is fainter; red marks where B is brighter. Checkerboard pixels were excluded. The warning lists how much was excluded and why.
5. Select a numbered circle or click the corresponding button under **Look up an object**. The panel opens **Nearby known objects** automatically. The pixel inspector shows measurements at the residual peak and patches from both original observations when available.

### Possible motion

After subtraction, select **Possible motion** under **What changed?**. The app uses the same candidate response as **Brightness changes**, so switching views does not recompute the subtraction. It shows up to three blue-to-red pairs, ordered by the strength of their weaker mark. Selecting a pair draws one arrow from the reference position to the current position and shows the angular separation. The view skips edge fragments and offsets smaller than the matched image's sharpness. If a marker has another eligible partner, the app flags that ambiguity.

An arrow shows a **possible** path, not an orbit or a verified moving object. A changing source, a nearby source, or a subtraction artifact can also leave blue and red marks. **Complex → Investigate → Test across dates** checks a selected linear path for nearby residuals in other workspace observations; those checks share a reference image.

### What object is nearby?

The app sends the marker's sky coordinates to [CDS SIMBAD](https://simbad.harvard.edu/simbad/) and searches within **15 arcseconds**. It lists catalog names, object types, any available spectral type, and angular distance, closest first. **No SIMBAD objects found** means the lookup succeeded but returned no catalog entry within the radius. **SIMBAD lookup unavailable** means the lookup could not run.

A nearby star is a lead. To establish that it caused a brightness change, you would need to compare measurements at the star's own position in the two original images at compatible wavelengths. The current lookup does not perform that attribution.

## Spectral Fingerprint

A spectrum shows how bright a source is at different infrared wavelengths. Use it to explore what an object resembles.

- **Simple:** click a change marker, then **View spectral fingerprint** under the inspector.
- **Complex → Investigate:** select a residual or choose **View spectrum** on a tentative motion pair.
- **Complex → Timeline:** click a source in the registered image to measure a fixed sky position without first running subtraction.

Choose **Cached observation library** or **Current workspace only**, and a date window for a fixed source. Use **DR1 or QR3** files covering the position in several detector bands. A single exposure measures one band at that position. The app evaluates up to 120 eligible cached files per request and reports when it reaches the cap. Moving candidates are measured along the interpolated path between the chosen epochs, without extrapolation or a stellar classification.

The backend uses the native detector [effective PSF](https://caltech-ipac.github.io/irsa-tutorials/spherex-psf/), IMAGE, VARIANCE, FLAGS, and the selected ZODI correction to fit a point source and local background at the sky position. Wavelength and bandwidth come from FITS WCS-WAVE. Each usable exposure contributes one flux measurement in mJy. Vertical bars show **1σ flux uncertainty**; horizontal bars show **filter bandwidth**. Open **Measurement details and exclusions** for the source file, date, fit score, flags, and rejected samples.

When enough bands pass the fit checks, the app compares the measured shape with observed G2 V, M6 V, and L5 spectra from the [NASA IRTF SpeX library](https://irsa.ipac.caltech.edu/data/IRTF_Extra/SpectralLibrary/speclib.html). The backend fetches and caches the reference FITS files, converts them to compatible flux units, averages their flux over the shared passbands, and fits one brightness scale per template. Matching needs five non-overlapping bands spanning at least 0.4 µm within 24 hours, with at least three at signal-to-noise of 3 or higher. Poor or ambiguous matches show **Insufficient data**, even when the plot contains many measured points. Try an isolated source if the point-source fits fail, or download other bands close in time if wavelength coverage is the problem.

## Download more observations

1. Open **Simple → Downloads**. Choose **Native resolution · cutout** for a small region, or **Native resolution · full detector** for the entire 2,040 × 2,040 detector image. Both keep the same native sharpness. A full frame typically uses about 70 MB; calibration extensions also contribute to cutout size.
2. For a cutout, choose **3, 6, 12, 30, or 60 arcmin**. An arcminute is 1/60 of a degree; this setting controls how much sky the cutout covers. At 12 arcmin a typical cutout is about 117 × 117 native pixels, unless clipped at a detector edge.
3. Open **Download a different sky region**, enter RA/Dec in decimal degrees, and select **2–500 observations**. Click **Download region**. The archive may have fewer matching files than requested. **Complex → Downloads** also offers explicit collection and detector filters.
4. Follow current-file bytes, total size when reported by IRSA, files processed, and estimated batch size. **Pause** finishes the current file before stopping; **Resume** continues with the next file; **Cancel** stops the batch and preserves completed files. Keep the tab open while the batch runs.
5. Check **Save destination** before starting. Files go to the connected backend: the local PC or the Colab runtime. They become available in the app's observation library; they are not automatically saved to your browser's Downloads folder.

If IRSA reports **503**, retry later, reduce the batch size, or choose a different real exposure. Failed downloads are reported and are never replaced by simulated data. The download count is separate from the 12-file workspace limit.

For a resumable command-line batch of 200 native cutouts around the sample field:

```bash
.venv/bin/python scripts/download_bulk_observations.py --count 200 --size-deg .2 --workers 8
```

Rerunning retries unavailable files and reuses the completed ones. The default batch records archive URLs, SHA-256 IDs, timestamps, sizes, dimensions, and wavelength information in `backend/data/bulk-200/manifest.json`. The file count is not a count of distinct dates or wavelength-compatible images.

## Complex workspace

Select files in **Observation library**, enter a fixed sky position, and choose **Build fixed-sky view**. One workspace holds up to 12 files. Duplicate copies of the same exposure and detector are rejected.

| View | What it shows |
| --- | --- |
| **Explore / Data Inspector** | Native IMAGE, VARIANCE, FLAGS, and ZODI pixels; FITS headers and extension schemas; WCS coordinates; brightness, noise, wavelength, and bandwidth. Display stretches and PNG exports are for viewing. |
| **Wavelengths** | Measured detector wavelengths, a calibration map, and a registered inverse-variance weighted image when the wavelength filter is enabled. |
| **Timeline** | Actual observation dates, aligned playback, pixel inspection, aperture flux charts, and fixed-position Spectral Fingerprint. |
| **Difference imaging** | Registered or native inputs, signed B−A image, approximate significance, and the valid-overlap mask. |
| **Investigate** | Residual groups, configurable threshold and size, possible motion pairs, checks across epochs, catalog lookup, and spectra. |
| **Downloads** | IRSA search and file import, with archive provenance and release labels. |

## How the measurements work

1. **Pick two compatible dates.** Simple automatically prepares a pair from the library. It checks for distinct observation times and usable overlap before offering a date. Subtraction starts only when you click **Subtract images**.
2. **Align and screen the pixels.** Celestial WCS maps the images to the same ICRS sky grid. The app checks pixel flags, variance, and spectral overlap. Band centers may differ by at most 25% of the narrower bandwidth, and bandwidths by at most 20% of the wider bandwidth.
3. **Account for foreground, background, and sharpness.** The default in Simple and Complex subtracts each file's ZODI model before registration. Optional median-overlap background correction removes the remaining offset. Gaussian PSF matching smooths to the wider header PSF_FWHM. Neither input FITS file is modified.
4. **Subtract and group residuals.** The app computes B−A in MJy/sr and an approximate significance image using propagated variance. Simple starts at 7σ and requires at least three connected pixels; it shows the five strongest regions by default.

Resampling correlates nearby pixels. Reported significance is an estimate, not the probability that a source changed. The calculation does not capture all ZODI, calibration, or PSF errors. WCS-WAVE is approximate; [IRSA recommends CWAVE and CBAND for precision work](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/#additional-product-spectral-wcs). The workspace's legacy aperture charts and the Spectral Fingerprint's native PSF fits use different measurement methods.

The pinned reference file's URL, expected size, and checksum are recorded in [backend/dataset.json](backend/dataset.json). Archive imports retain source URLs; other uploads are labeled user supplied unless their bytes match the verified reference. Observation dates come from observing-time FITS keywords, never the file creation date.

## Use a Google Colab backend

1. Open the [standalone Colab notebook](docs/spherex-colab-standalone.ipynb), or paste the [standalone Python script](docs/spherex-colab-standalone.py) directly into a Colab cell. It embeds the backend, starts the API, prints a private tunnel URL, and downloads and registers real Nova Velorum FITS observations. No separate ZIP upload is needed.
2. Copy the full `BACKEND_URL=...` line into the project's `.env.local`. Stop and restart Next.js with `npm run dev -- --port 3001` **without** the inline local URL override.
3. Keep the Colab runtime active. Refresh the app, check **Save destination**, and look in **Complex → Observation library** for the registered files. Downloads and the cache now live in the Colab runtime.
4. To return to the local cache, set `BACKEND_URL=http://127.0.0.1:8000` and restart Next.js with the local Python service running.

Keep the tunnel URL private. A reset Colab runtime can lose its files and change its URL. After backend edits, regenerate the standalone files with `python3 scripts/generate_standalone_colab.py`. The older [ZIP-based notebook](docs/spherex-colab.ipynb) and [backend ZIP](docs/spherex-colab-backend.zip) remain available.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Science service unavailable | Check both health URLs above and restart Next.js after changing `BACKEND_URL`. |
| No compatible overlap | Add observations of the same position and similar bands, or select another date. Having the same detector number is not enough. |
| Images show different amounts of sky | Original FITS coverage can differ between a cutout and a full frame. Use the aligned comparison for a shared sky scale. |
| Checkerboard gaps | Read the exclusion breakdown; flagged, out-of-frame, or wavelength-incompatible pixels are not used. |
| No numbered changes or possible motion | Try another compatible date. A lower threshold can show weaker residuals and more noise. |
| Spectrum has points but says **Insufficient data** | Check fit scores, signal-to-noise, distinct wavelength coverage, and the time window in **Measurement details and exclusions**. |
| Workspace or analysis expired | Rebuild the view or run subtraction again. The backend keeps a bounded in-memory cache; disk files remain in the library. |

## Development and sources

```bash
npm run typecheck
npm run test:science
npm run build
```

FastAPI serves interactive API docs at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) while running locally. The frontend uses `/api/science/*`. Key endpoints include `/workspace/auto-session` for pair preparation, `/analysis` for subtraction, `/analysis/{id}/candidates` for residuals and motion pairs, `/catalog/nearby` for SIMBAD, and `/analysis/{id}/fingerprint` for candidate spectra.

Science tests use controlled FITS fixtures; the app uses real observations. See [the observation report](docs/observation-report.md) and [the browser workflow check](scripts/test_workspace_browser.py) for real-data validation.

- [NASA/IPAC IRSA SPHEREx data products](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/)
- [IRSA archive search and access](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/)
- [IRSA effective PSF tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-psf/)
- [CDS SIMBAD astronomical database](https://simbad.harvard.edu/simbad/)
- [NASA IRTF SpeX spectral library](https://irsa.ipac.caltech.edu/data/IRTF_Extra/SpectralLibrary/speclib.html)
