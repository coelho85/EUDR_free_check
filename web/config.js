// Settings of this installation of the EUDR free check. See README.md.
export const CONFIG = {
  // tiles.json listing the JRC GFC2020 v4 10° Cloud-Optimized GeoTIFF tiles (build your own with tools/build_tiles.py).
  // The default points to the GeoAnalytics Lab mirror, which accepts requests from http://localhost:8765 for evaluation.
  TILES_MANIFEST: 'https://maps.geoanalyticslab.com/gfc2020/v4/cog10/tiles.json',
  // Mapbox public token (pk.…) for high-resolution imagery at field scale. Empty = Sentinel-2 cloudless basemap only.
  MAPBOX_TOKEN: '',
  // Registration endpoint before download (worker-forms/). Empty = results download directly, no registration.
  FORMS_URL: '',
  // Optional Cloudflare Turnstile site key (spam protection for the registration form).
  TURNSTILE_SITEKEY: '',
};
