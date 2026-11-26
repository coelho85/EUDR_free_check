// Settings of this installation of the EUDR free check. See README.md.
export const CONFIG = {
  // URL of tiles.json listing your JRC GFC2020 v4 10° Cloud-Optimized GeoTIFF tiles (build them with tools/build_tiles.py).
  TILES_MANIFEST: '',
  // Mapbox public token (pk.…) for high-resolution imagery at field scale. Empty = Sentinel-2 cloudless basemap only.
  MAPBOX_TOKEN: '',
  // Registration endpoint before download (worker-forms/). Empty = results download directly, no registration.
  FORMS_URL: '',
  // Optional Cloudflare Turnstile site key (spam protection for the registration form).
  TURNSTILE_SITEKEY: '',
};
