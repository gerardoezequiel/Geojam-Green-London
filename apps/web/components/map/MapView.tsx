'use client'

import { useEffect, useRef, useState } from 'react'
import maplibregl, { Map as MapLibreMap } from 'maplibre-gl'
import { Protocol as PMTilesProtocol } from 'pmtiles'
import { MapboxOverlay } from '@deck.gl/mapbox'
import { MVTLayer } from '@deck.gl/geo-layers'
import 'maplibre-gl/dist/maplibre-gl.css'

import { CITIES } from '@/lib/cities'
import { tileUrl } from '@/lib/cities'
import { rampLookup, VARIABLES, VariableKey } from '@/lib/colour'
import { BASEMAP_STYLE_URL } from '@/lib/basemap-style'

type Props = {
  city?: keyof typeof CITIES
  variable?: VariableKey
}

export default function MapView({ city = 'london', variable = 'mean_ndvi_late' }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const overlayRef = useRef<MapboxOverlay | null>(null)
  const [hovered, setHovered] = useState<{ name: string; value: number; borough: string } | null>(null)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const protocol = new PMTilesProtocol()
    maplibregl.addProtocol('pmtiles', protocol.tile)

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

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
      maplibregl.removeProtocol('pmtiles')
    }
  }, [city])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const onLoad = () => {
      const cfg = VARIABLES[variable]
      const layer = new MVTLayer({
        id: `msoa-${variable}`,
        data: `pmtiles://${tileUrl(city, 'pmtiles', 'msoa.pmtiles')}/{z}/{x}/{y}`,
        minZoom: 8,
        maxZoom: 14,
        getFillColor: (f: { properties: Record<string, unknown> }) => {
          const v = f.properties[variable] as number | undefined
          return v == null ? [180, 180, 180, 40] : rampLookup(cfg.ramp, v, 200)
        },
        getLineColor: [255, 255, 255, 90],
        lineWidthMinPixels: 0.4,
        pickable: true,
        onHover: (info) => {
          if (!info.object) {
            setHovered(null)
            return
          }
          const p = (info.object as { properties: Record<string, unknown> }).properties
          setHovered({
            name: String(p.MSOA21NM ?? p.id ?? ''),
            borough: String(p.borough ?? ''),
            value: Number(p[variable] ?? NaN),
          })
        },
        updateTriggers: { getFillColor: [variable] },
      })

      const overlay = new MapboxOverlay({ interleaved: true, layers: [layer] })
      map.addControl(overlay)
      overlayRef.current = overlay
    }

    if (map.loaded()) onLoad()
    else map.once('load', onLoad)

    return () => {
      if (overlayRef.current) {
        map.removeControl(overlayRef.current)
        overlayRef.current = null
      }
    }
  }, [city, variable])

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="absolute inset-0" />
      {hovered && (
        <div className="pointer-events-none absolute left-4 top-4 rounded-md bg-white/95 p-3 text-sm shadow-md ring-1 ring-black/5 backdrop-blur dark:bg-neutral-900/95 dark:text-neutral-100">
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
    </div>
  )
}
