/** Minimal MapLibre style for a clean cartographic basemap.
 *
 * Uses the OpenFreeMap Liberty style as a free, no-key vector basemap
 * (https://openfreemap.org). For production we would fork this style and
 * adjust the palette to the brand tokens.
 */

import type { StyleSpecification } from 'maplibre-gl'

export const BASEMAP_STYLE_URL = 'https://tiles.openfreemap.org/styles/positron'

export const FALLBACK_RASTER_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '&copy; OpenStreetMap',
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
}
