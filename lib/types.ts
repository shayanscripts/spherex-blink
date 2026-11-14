export type Layer = "IMAGE" | "VARIANCE" | "FLAGS" | "ZODI";
export type HeaderCard = { key: string; value: string | number | boolean | null; comment: string };
export type HeaderValue = { key: string; value: string | number; extension: string } | null;
export type Extension = { index: number; name: string; kind: string; shape: number[]; unit: string | null; columns: { name: string; format: string; unit: string | null; dim: string | null }[] };
export type Stats = { min: number | null; max: number | null; low: number | null; high: number | null; valid_pixels: number; total_pixels: number };
export type Observation = {
  id: string; filename: string; bytes: number; shape: number[]; extensions: Extension[];
  center_wavelength_um?: number | null; center_bandwidth_um?: number | null;
  stats: Partial<Record<Layer, Stats>>; observation: HeaderValue; instrument: HeaderValue;
  timestamp: HeaderValue; time_system: HeaderValue; detector: HeaderValue; release: HeaderValue;
  processing_version: HeaderValue; spatial_wcs: boolean;
  spectral: { min_um: number | null; max_um: number | null; bandwidth_min_um: number | null; bandwidth_max_um: number | null; method: string; purpose: string } | null;
  flag_definitions: HeaderCard[]; notices: string[]; source_url: string; provenance: string;
};
export type Pixel = {
  x: number; y: number; fits_x: number; fits_y: number; layer: Layer; value: number | null; unit: string | null;
  ra_deg: number | null; dec_deg: number | null; wavelength_um: number | null; bandwidth_um: number | null;
  brightness: number | null; variance: number | null; uncertainty: number | null; flags: number | null;
  flag_bits: number[]; zodi: number | null; measurement_note: string;
};
export const layerInfo: Record<Layer, { label: string; description: string }> = {
  IMAGE: { label: "Science image", description: "Calibrated detector brightness. Display stretches change appearance only; pixel values stay untouched." },
  VARIANCE: { label: "Variance", description: "Per-pixel measurement variance. Negative or nonfinite values appear transparent; uncertainty is √variance." },
  FLAGS: { label: "Quality flags", description: "Integer pixel bit fields. Inspect a pixel for active bits; definitions are read verbatim from the FLAGS header." },
  ZODI: { label: "Zodiacal light", description: "Modeled zodiacal foreground. Shown independently here; comparison views can subtract it before alignment. Original FITS data stay unchanged." },
};
export function number(value: number | null | undefined, digits = 4) {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value !== 0 && (Math.abs(value) < 0.001 || Math.abs(value) >= 1e6)) return value.toExponential(3);
  return value.toLocaleString("en-US", { maximumFractionDigits: digits });
}

export type WorkspaceView = 'wavelengths' | 'timeline' | 'difference' | 'investigate' | 'archive';
export type SkyFrame = { id: string; observation:HeaderValue; time_system:HeaderValue; provenance:string; filename: string; timestamp: string|null; coverage: number; wavelength_min_um: number|null; wavelength_max_um: number|null; psf_fwhm_arcsec: number|null; source_url: string };
export type SkySession = { selection?:{library_count:number;checked:number;method:string}; id: string; frames: SkyFrame[]; grid: { ra:number; dec:number; size:number; scale:number; wavelength:number|null; width:number; subtract_zodi:boolean }; limits:number[]; distinct_epochs:number; comparisons:{reference:number;new:number;available:boolean;coverage:number;reason:string|null}[]; recommended_pair:{reference:number;new:number;coverage:number}|null; note:string };
export type Analysis = { id:string; checks:{label:string;detail:string}[]; exclusions?:{reason:string;pixels:number}[]; zodi_subtracted:boolean; overlap_fraction:number; valid_pixels:number; background_offset:number; psf_target_arcsec:number; reference_timestamp:string; new_timestamp:string; assumptions:string[]; unit:string };
export type Residual = { id:number; peak_x:number; peak_y:number; pattern:string; x:number; y:number; ra_deg:number; dec_deg:number; pixels:number; peak_sigma:number; sign:string; status:string; edge:boolean };
export type Motion = { negative_id:number; positive_id:number; separation_arcsec:number; speed_arcsec_hour:number; ra_motion_arcsec_hour:number; dec_motion_arcsec_hour:number; status:string };
export type CandidateResult = { candidates:Residual[]; motion_hypotheses:Motion[]; note:string };
