'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import maplibregl, { Map as MapLibreMap } from 'maplibre-gl'
import { MapboxOverlay } from '@deck.gl/mapbox'
import { GeoJsonLayer, ScatterplotLayer } from '@deck.gl/layers'
import { H3HexagonLayer } from '@deck.gl/geo-layers'
import { polygonToCells } from 'h3-js'
import 'maplibre-gl/dist/maplibre-gl.css'

import { CITIES, tileUrl } from '@/lib/cities'
import { rampLookup, VARIABLES, VariableKey } from '@/lib/colour'
import { BASEMAP_STYLE_URL } from '@/lib/basemap-style'
import type { AnomalyRow } from '@/lib/anomalies'

type CityKey = keyof typeof CITIES

interface MapViewProps {
  city?: CityKey
  variable?: VariableKey
  aggregation?: 'msoa' | 'h3'
  anomalies?: AnomalyRow[]
}

interface HoverState {
  name: string
  borough: string
  value: number
}

interface MSOAFeatureProperties {
  MSOA21CD?: string
  MSOA21NM?: string
  borough?: string
  mean_ndvi_late?: number
  mean_ndvi_early?: number
  mean_delta_ndvi?: number
  [key: string]: unknown
}

type MSOAGeoJSON = GeoJSON.FeatureCollection<GeoJSON.Polygon | GeoJSON.MultiPolygon, MSOAFeatureProperties>

type H3Resolution = 7 | 8 | 9

interface H3CellDatum extends MSOAFeatureProperties {
  hex: string
  resolution: H3Resolution
}

export default function MapView({
  city = 'london',
  variable = 'mean_ndvi_late',
  aggregation = 'msoa',
  anomalies,
}: MapViewProps): React.JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const overlayRef = useRef<MapboxOverlay | null>(null)
  const [features, setFeatures] = useState<MSOAGeoJSON | null>(null)
  const [hovered, setHovered] = useState<HoverState | null>(null)
  const [ready, setReady] = useState(false)
  const [zoom, setZoom] = useState(CITIES[city].initialZoom)

  const h3Resolution: H3Resolution = zoom < 10 ? 7 : zoom < 11.5 ? 8 : 9

  const h3Cells = useMemo(() => {
    if (!features || aggregation !== 'h3') return []

    const byHex = new Map<string, H3CellDatum>()
    for (const feature of features.features) {
      const polygons =
        feature.geometry.type === 'Polygon'
          ? [feature.geometry.coordinates]
          : feature.geometry.coordinates

      for (const polygon of polygons) {
        const cells = polygonToCells(polygon, h3Resolution, true)
        for (const hex of cells) {
          if (!byHex.has(hex)) {
            byHex.set(hex, {
              hex,
              resolution: h3Resolution,
              ...feature.properties,
            })
          }
        }
      }
    }

    return [...byHex.values()]
  }, [aggregation, features, h3Resolution])

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const cityCfg = CITIES[city]
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASEMAP_STYLE_URL,
      center: cityCfg.centre,
      zoom: cityCfg.initialZoom,
      attributionControl: { compact: true },
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left')

    const updateZoom = () => setZoom(map.getZoom())
    map.once('load', () => {
      updateZoom()
      setReady(true)
    })
    map.on('zoomend', updateZoom)
    mapRef.current = map

    const ro = new ResizeObserver(() => {
      try {
        map.resize()
      } catch {
        /* map may have been removed */
      }
    })
    ro.observe(containerRef.current)

    return () => {
      map.off('zoomend', updateZoom)
      ro.disconnect()
      map.remove()
      mapRef.current = null
      setReady(false)
    }
  }, [city])

  useEffect(() => {
    let cancelled = false
    const url = tileUrl(city, 'geojson', 'msoa.geojson')
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`failed to fetch ${url}: ${res.status}`)
        return res.json() as Promise<MSOAGeoJSON>
      })
      .then((data) => {
        if (!cancelled) setFeatures(data)
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error('msoa geojson load failed', err)
      })
    return () => {
      cancelled = true
    }
  }, [city])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !features) return

    const cfg = VARIABLES[variable]

    const layer =
      aggregation === 'h3'
        ? new H3HexagonLayer<H3CellDatum>({
            id: `h3-${h3Resolution}-${variable}`,
            data: h3Cells,
            pickable: true,
            filled: true,
            stroked: false,
            extruded: false,
            coverage: 0.88,
            getHexagon: (d) => d.hex,
            getFillColor: (d) => {
              const v = d[variable] as number | undefined
              return v == null || Number.isNaN(v)
                ? [180, 180, 180, 40]
                : rampLookup(cfg.ramp, v, 205)
            },
            onHover: (info) => {
              if (!info.object) {
                setHovered(null)
                return
              }
              const cell = info.object as H3CellDatum
              const value = Number(cell[variable])
              setHovered({
                name: cell.MSOA21NM ?? cell.hex,
                borough: `${cell.borough ?? ''} · H3 r${cell.resolution}`,
                value,
              })
            },
            updateTriggers: { getFillColor: [variable] },
          })
        : new GeoJsonLayer<MSOAFeatureProperties>({
            id: `msoa-${variable}`,
            data: features,
            stroked: true,
            filled: true,
            pickable: true,
            getFillColor: (f) => {
              const v = f.properties[variable] as number | undefined
              return v == null || Number.isNaN(v)
                ? [180, 180, 180, 40]
                : rampLookup(cfg.ramp, v, 200)
            },
            getLineColor: [255, 255, 255, 90],
            lineWidthMinPixels: 0.4,
            onHover: (info) => {
              if (!info.object) {
                setHovered(null)
                return
              }
              const props = (info.object as { properties: MSOAFeatureProperties }).properties
              const value = Number(props[variable])
              setHovered({
                name: props.MSOA21NM ?? '',
                borough: props.borough ?? '',
                value,
              })
            },
            updateTriggers: { getFillColor: [variable] },
          })

    const anomalyLayer = anomalies && anomalies.length > 0
      ? new ScatterplotLayer<AnomalyRow>({
          id: 'anomaly-markers',
          data: anomalies,
          pickable: true,
          stroked: true,
          filled: true,
          radiusUnits: 'pixels',
          getPosition: (d) => [d.lon, d.lat],
          getRadius: (d) => 4 + Math.min(8, Math.abs(d.residual_z) * 1.6),
          getFillColor: (d) =>
            d.residual >= 0 ? [16, 122, 87, 230] : [201, 30, 30, 230],
          getLineColor: [255, 255, 255, 230],
          lineWidthMinPixels: 1.4,
          onHover: (info) => {
            if (!info.object) {
              setHovered(null)
              return
            }
            const d = info.object as AnomalyRow
            setHovered({
              name: d.name,
              borough: `${d.borough} · residual ${d.residual >= 0 ? '+' : ''}${d.residual.toFixed(3)}`,
              value: d.surprise_score,
            })
          },
        })
      : null

    const layers = anomalyLayer ? [layer, anomalyLayer] : [layer]
    let overlay = overlayRef.current
    if (!overlay) {
      overlay = new MapboxOverlay({ interleaved: true, layers, widgets: [] })
      map.addControl(overlay)
      overlayRef.current = overlay
    } else {
      overlay.setProps({ layers, widgets: [] })
    }
  }, [aggregation, anomalies, city, features, h3Cells, h3Resolution, ready, variable])

  useEffect(() => {
    return () => {
      const map = mapRef.current
      if (overlayRef.current && map) {
        map.removeControl(overlayRef.current)
        overlayRef.current = null
      }
    }
  }, [])

  return (
    <>
      <div
        ref={containerRef}
        style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
      />
      {aggregation === 'h3' && (
        <div className="pointer-events-none absolute bottom-8 left-4 z-10 rounded-md bg-white/95 px-3 py-2 text-xs font-medium shadow-md ring-1 ring-black/5">
          H3 r{h3Resolution} · {h3Cells.length.toLocaleString('en-GB')} cells
        </div>
      )}
      {hovered && (
        <div className="pointer-events-none absolute left-4 top-4 z-10 rounded-md bg-white/95 p-3 text-sm shadow-md ring-1 ring-black/5 backdrop-blur dark:bg-neutral-900/95 dark:text-neutral-100">
          <div className="font-medium">{hovered.name}</div>
          <div className="text-xs text-neutral-500 dark:text-neutral-400">{hovered.borough}</div>
          <div className="mt-1 text-xs">
            {VARIABLES[variable].label}:{' '}
            <span className="font-mono">
              {Number.isFinite(hovered.value) ? hovered.value.toFixed(3) : 'no data'}
            </span>
          </div>
        </div>
      )}
    </>
  )
}
