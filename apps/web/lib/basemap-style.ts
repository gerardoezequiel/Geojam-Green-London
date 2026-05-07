/** No-key vector basemap with clear roads, parks and labels. */

import type { StyleSpecification } from 'maplibre-gl'

export const BASEMAP_STYLE_URL = 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json'

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
