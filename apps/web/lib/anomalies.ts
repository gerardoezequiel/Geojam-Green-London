/** Loaders + types for the ML pipeline outputs. */

import { tileUrl } from '@/lib/cities'

export interface AnomalyRow {
  code: string
  name: string
  borough: string
  lon: number
  lat: number
  population: number
  ndvi_late: number
  ndvi_early: number
  delta_ndvi: number
  predicted_ndvi: number
  residual: number
  residual_z: number
  lisa_cluster: 'HH' | 'HL' | 'LH' | 'LL' | 'NS'
  surprise_score: number
}

export interface AnomaliesPayload {
  rows: AnomalyRow[]
}

export interface ModelMetrics {
  model_name?: string
  cv_mean_r2: number
  moran_i: number | null
  runtime_s: number
  feature_importances: Array<{ base_feature: string; importance: number }>
  rows: number
}

export async function loadAnomalies(city: string): Promise<AnomaliesPayload> {
  const url = tileUrl(city, 'json', 'anomalies.json')
  const res = await fetch(url)
  if (!res.ok) throw new Error(`failed to load anomalies: ${res.status}`)
  return (await res.json()) as AnomaliesPayload
}

export async function loadModelMetrics(city: string): Promise<ModelMetrics> {
  const url = tileUrl(city, 'json', 'metrics.json')
  const res = await fetch(url)
  if (!res.ok) throw new Error(`failed to load metrics: ${res.status}`)
  const text = await res.text()
  const raw = JSON.parse(text.replace(/\bNaN\b/g, 'null')) as ModelMetrics & {
    moran_i: number | string | null
  }
  // Some Python JSON writers serialise NaN as a bare literal. Normalise that to
  // null so the browser can keep loading the rest of the metrics.
  const moran = raw.moran_i
  return {
    ...raw,
    moran_i:
      typeof moran === 'number' && Number.isFinite(moran) ? moran : null,
  }
}

export function topByField<T>(rows: T[], field: keyof T, n: number, ascending = false): T[] {
  return [...rows]
    .sort((a, b) => {
      const av = Number(a[field])
      const bv = Number(b[field])
      return ascending ? av - bv : bv - av
    })
    .slice(0, n)
}
