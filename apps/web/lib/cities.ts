export type City = {
  slug: string
  name: string
  centre: [number, number]
  initialZoom: number
  defaultLevel: 'msoa' | 'lsoa' | 'iris' | 'lor'
}

export const CITIES: Record<string, City> = {
  london: {
    slug: 'london',
    name: 'London',
    centre: [-0.1276, 51.5074],
    initialZoom: 9.5,
    defaultLevel: 'msoa',
  },
  berlin: {
    slug: 'berlin',
    name: 'Berlin',
    centre: [13.405, 52.52],
    initialZoom: 9.5,
    defaultLevel: 'lor',
  },
  paris: {
    slug: 'paris',
    name: 'Paris',
    centre: [2.3522, 48.8566],
    initialZoom: 11.5,
    defaultLevel: 'iris',
  },
}

export const TILES_BASE = process.env.NEXT_PUBLIC_TILES_URL ?? '/v1'

export const tileUrl = (city: string, kind: 'pmtiles' | 'parquet' | 'cogs', file: string) =>
  `${TILES_BASE}/${kind}/${city}/${file}`
