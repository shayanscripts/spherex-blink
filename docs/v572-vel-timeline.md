# Nova Velorum 2025: V572 Vel at a fixed position

Use ICRS/J2000 RA **156.307917°**, Dec **−53.522028°**. [OGLE position](https://www.astronomerstelegram.org/?read=17253) · [IRSA sky search](https://irsa.ipac.caltech.edu/applications/spherex/?api=spectral-images&ra=156.307917&dec=-53.522028&sr=30s).

The observers reported a June 17 non-detection, then a June 20 infrared detection in D1 and D4, ahead of the June 25 optical discovery. The June 25 epoch was already saturated in those bands. [Original detection report](https://www.astronomerstelegram.org/?read=17601). For later evolution, a [follow-up report](https://www.astronomerstelegram.org/?read=18127) identifies dust emission in spectra assembled in December 2025–January 2026 and May–July 2026.

The preview uses these **FITS header UTC timestamps** from locally downloaded official DR1 cutouts. They are distinct from the fractional dates quoted in the discovery report.

| UTC | Band at target | View |
| --- | --- | --- |
| 2025-06-17 12:13:01.779 | 1.262 µm | Before the reported outburst |
| 2025-06-20 20:11:43.974 | 2.511 µm | Bright target, flagged |
| 2025-06-21 23:49:46.294 | 0.873 µm | Bright target, flagged |

The three source URLs are pinned in [the preview script](../scripts/preview_v572_vel.py). The images use original detector crops and the same asinh stretch, set using the baseline field so bright nova pixels cannot darken the rest of the view. They are **not suitable for quantitative subtraction or a light curve**: wavelengths differ, and the nova pixels are rejected by the app's quality mask in the two outburst frames. The target ring comes from each FITS file's WCS.

In an existing Colab runtime, replace `/content/spherex-colab-backend.zip` with [the updated bundle](spherex-colab-backend.zip) and paste/run [the nova cell](../scripts/colab_nova_cell.py). This reuses the existing backend directory and does not restart the tunnel. For a fresh runtime, run both code cells in [the notebook](spherex-colab.ipynb).
