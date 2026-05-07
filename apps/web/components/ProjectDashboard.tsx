'use client'

import { useEffect, useMemo, useState } from 'react'

import MapClient from '@/components/map/MapClient'
import { VARIABLES, VariableKey } from '@/lib/colour'
import {
  loadAnomalies,
  loadModelMetrics,
  topByField,
  type AnomalyRow,
  type ModelMetrics,
} from '@/lib/anomalies'

const VARIABLE_COPY: Record<VariableKey, string> = {
  mean_ndvi_late: 'Mean 2024 NDVI per MSOA from the July 2024 Sentinel-2 mosaic.',
  mean_ndvi_early: 'Mean 2019 NDVI per MSOA from the July 2019 Sentinel-2 mosaic.',
  mean_delta_ndvi: 'Difference between the two snapshots. Negative values mean lower 2024 NDVI.',
}

const ANOMALY_VISIBLE = 24

const ML_PIPELINE_STEPS = [
  {
    title: 'Slide 1 · The question',
    body: 'Can we explain why some London neighbourhoods are greener than others, and then find places that are greener or greyer than their urban context predicts?',
  },
  {
    title: 'Slide 2 · The data',
    body: 'We use Sentinel-2 red and near-infrared bands from July 2019 and July 2024, ONS MSOA boundaries, population density and distance-to-park features.',
  },
  {
    title: 'Slide 3 · The target',
    body: 'NDVI is calculated as (NIR - Red) / (NIR + Red). We aggregate the pixel-level NDVI into one mean value per MSOA so every neighbourhood becomes a modelling row.',
  },
  {
    title: 'Slide 4 · The model',
    body: 'We run a small ensemble bake-off: ExtraTreesRegressor and RandomForestRegressor. Both capture non-linear effects; the pipeline keeps the one with the best 5-fold cross-validated R².',
  },
  {
    title: 'Slide 5 · The result',
    body: 'The winning ensemble predicts expected 2024 NDVI. The residual is the story: actual minus predicted. Negative residuals are greyer than expected; positive residuals are greener than expected.',
  },
]

const CHALLENGE_ANSWERS = [
  {
    prompt: 'ΔNDVI',
    status: 'Solved',
    answer:
      'The app maps 2019 to 2024 NDVI change. In this two-scene comparison every shipped MSOA is lower in 2024, with the largest measured declines around Croydon and Bromley. Treat this as snapshot change, not a climate trend.',
  },
  {
    prompt: 'Sub-MSOA',
    status: 'Partial',
    answer:
      'H3 r7-r9 is now available as an interactive sub-MSOA view. It currently inherits MSOA values; the next step is true pixel-to-H3 zonal stats from the NDVI rasters.',
  },
  {
    prompt: 'Spectral features',
    status: 'Not shipped yet',
    answer:
      'The data pack contains blue, green, red and NIR bands, so NDWI-like water and NDVI heterogeneity are feasible. Bare soil is weaker without SWIR B11, but a red-greater-than-NIR proxy can be tested.',
  },
  {
    prompt: 'Multi-temporal',
    status: 'Not solved yet',
    answer:
      'We only have two scenes in the app. A proper answer needs a summer median per year from Earth Search or Planetary Computer, then H3/MSOA time-series parquet.',
  },
  {
    prompt: 'Equity lens',
    status: 'Partial',
    answer:
      'Population density is in the model and is negatively correlated with 2024 NDVI in the current MSOA outputs. Green-space-per-person needs accessible green area by LSOA or MSOA, not just NDVI.',
  },
]

export default function ProjectDashboard(): React.JSX.Element {
  const [variable, setVariable] = useState<VariableKey>('mean_ndvi_late')
  const [aggregation, setAggregation] = useState<'msoa' | 'h3'>('msoa')
  const [anomalies, setAnomalies] = useState<AnomalyRow[] | null>(null)
  const [metrics, setMetrics] = useState<ModelMetrics | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([loadAnomalies('london'), loadModelMetrics('london')])
      .then(([anomPayload, m]) => {
        if (cancelled) return
        setAnomalies(anomPayload.rows)
        setMetrics(m)
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error('failed to load ML outputs', err)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const greenest = useMemo(() => (anomalies ? topByField(anomalies, 'ndvi_late', 3) : []), [anomalies])
  const lowest = useMemo(() => (anomalies ? topByField(anomalies, 'ndvi_late', 3, true) : []), [anomalies])
  const declines = useMemo(() => (anomalies ? topByField(anomalies, 'delta_ndvi', 3, true) : []), [anomalies])
  const surprises = useMemo(
    () => (anomalies ? topByField(anomalies, 'surprise_score', ANOMALY_VISIBLE) : []),
    [anomalies],
  )

  const stats = useMemo(() => {
    if (!anomalies) return null
    const total = anomalies.length
    const meanLate = mean(anomalies.map((a) => a.ndvi_late))
    const meanEarly = mean(anomalies.map((a) => a.ndvi_early))
    const meanDelta = mean(anomalies.map((a) => a.delta_ndvi))
    const negDelta = anomalies.filter((a) => a.delta_ndvi < 0).length
    const boroughs = new Set(anomalies.map((a) => a.borough)).size
    return {
      total: total.toLocaleString(),
      boroughs: String(boroughs),
      meanLate: meanLate.toFixed(3),
      meanEarly: meanEarly.toFixed(3),
      meanDelta: meanDelta.toFixed(3),
      negShare: `${Math.round((negDelta / total) * 100)}%`,
    }
  }, [anomalies])

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 bg-[#f7f7f4] text-neutral-950 lg:grid-cols-[380px_minmax(0,1fr)]">
      <aside className="order-2 flex max-h-[48dvh] flex-col overflow-y-auto border-t border-neutral-200 bg-white lg:order-1 lg:max-h-none lg:border-r lg:border-t-0">
        <div className="border-b border-neutral-200 px-5 py-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-700">
            Methodology
          </p>
          <h2 className="mt-2 text-xl font-semibold tracking-tight">London greenness model</h2>
          <p className="mt-2 text-sm leading-6 text-neutral-600">
            This prototype turns the GeoJam London data pack into a browser map. It compares two
            Sentinel-2 L2A summer snapshots, aggregates NDVI to MSOA boundaries, and ships static
            assets that can be rendered without an application backend.
          </p>
          <div className="mt-4 rounded-md border border-emerald-700 bg-emerald-50 px-3 py-3">
            <div className="text-xs font-semibold uppercase tracking-[0.12em] text-emerald-800">
              Opening line
            </div>
            <p className="mt-1 text-sm leading-6 text-emerald-950">
              London&apos;s greenest MSOA in the 2024 snapshot is Richmond upon Thames 012, with a
              mean NDVI of about 0.505. But the more useful hackathon output is not just a ranking:
              it is a model that tells us which places are unexpectedly green or unexpectedly grey
              after accounting for urban context.
            </p>
          </div>
        </div>

        <section className="border-b border-neutral-200 px-5 py-4">
          <h3 className="text-sm font-semibold">Layer</h3>
          <div className="mt-3 grid grid-cols-1 gap-2">
            {(Object.keys(VARIABLES) as VariableKey[]).map((key) => {
              const active = variable === key
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setVariable(key)}
                  className={[
                    'rounded-md border px-3 py-2 text-left text-sm transition',
                    active
                      ? 'border-emerald-700 bg-emerald-50 text-emerald-950'
                      : 'border-neutral-200 bg-white text-neutral-700 hover:border-neutral-400',
                  ].join(' ')}
                >
                  <span className="block font-medium">{VARIABLES[key].label}</span>
                  <span className="mt-0.5 block text-xs text-neutral-500">{VARIABLE_COPY[key]}</span>
                </button>
              )
            })}
          </div>
        </section>

        <section className="border-b border-neutral-200 px-5 py-4">
          <h3 className="text-sm font-semibold">ML pipeline slides</h3>
          <div className="mt-3 snap-x space-y-2">
            {ML_PIPELINE_STEPS.map((step) => (
              <div key={step.title} className="rounded-md border border-neutral-200 px-3 py-3">
                <div className="text-sm font-semibold">{step.title}</div>
                <p className="mt-1 text-xs leading-5 text-neutral-600">{step.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="border-b border-neutral-200 px-5 py-4">
          <h3 className="text-sm font-semibold">Five-minute talk track</h3>
          <div className="mt-3 space-y-3 text-sm leading-6 text-neutral-600">
            <p>
              First, we convert satellite imagery into a simple ecological signal: NDVI. Healthy
              vegetation reflects near-infrared light and absorbs red light, so higher NDVI means
              more photosynthetically active green cover.
            </p>
            <p>
              Second, we aggregate the raster to neighbourhood units. This gives us a London-wide
              MSOA table with 2024 NDVI, 2019 NDVI, change, density, park distance and borough.
            </p>
            <p>
              Third, we build a predictive model without using the satellite-derived target as an
              input. We compare RandomForest, which averages many bootstrap decision trees, with
              ExtraTrees, which adds more random split selection. The winner learns expected
              greenness from built-form context. That makes the residual meaningful: it is the part
              of greenness the simple urban features did not explain.
            </p>
            <p>
              Finally, the app turns those outputs into a presentation map: choropleths for NDVI
              and change, H3 for sub-MSOA exploration, and red/green markers for ML surprises.
            </p>
          </div>
        </section>

        <section className="border-b border-neutral-200 px-5 py-4">
          <h3 className="text-sm font-semibold">Model</h3>
          {metrics ? (
            <>
              <dl className="mt-3 grid grid-cols-2 gap-2">
                <Stat label="CV mean R²" value={metrics.cv_mean_r2.toFixed(3)} />
                <Stat label="Model" value={metrics.model_name ?? 'forest'} />
                <Stat label="Rows trained" value={metrics.rows.toLocaleString()} />
                <Stat
                  label="Moran's I"
                  value={metrics.moran_i == null ? 'n/a' : metrics.moran_i.toFixed(3)}
                />
                <Stat label="Runtime" value={`${metrics.runtime_s.toFixed(2)} s`} />
              </dl>
              <h4 className="mt-4 text-xs font-semibold uppercase tracking-[0.1em] text-neutral-500">
                Top features
              </h4>
              <ul className="mt-2 space-y-1.5 text-sm">
                {metrics.feature_importances.slice(0, 5).map((f) => (
                  <li key={f.base_feature} className="grid grid-cols-[1fr_auto] items-center gap-3">
                    <span className="truncate text-neutral-700">{f.base_feature}</span>
                    <span className="font-mono text-xs text-neutral-500">
                      {(f.importance * 100).toFixed(1)}%
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs leading-5 text-neutral-500">
                Ensemble model selection over ExtraTrees and RandomForest. Both predict NDVI 2024
                from non-satellite features; the sidebar shows the winning model. Residuals drive
                the anomaly score; markers on the map are the {ANOMALY_VISIBLE} largest surprises.
              </p>
              <p className="mt-2 text-xs leading-5 text-neutral-500">
                Result: the model explains part of the spatial pattern, but the residuals are the
                more interesting product because they identify places whose greenness does not match
                their built-form context.
              </p>
            </>
          ) : (
            <p className="mt-3 text-sm text-neutral-500">Loading model outputs…</p>
          )}
        </section>

        <section className="border-b border-neutral-200 px-5 py-4">
          <h3 className="text-sm font-semibold">Available geographies</h3>
          <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
            <GeogButton
              name="MSOA"
              status="boundary"
              active={aggregation === 'msoa'}
              onClick={() => setAggregation('msoa')}
            />
            <GeogButton name="LSOA" status="asset missing" disabled />
            <GeogButton
              name="H3"
              status="auto r7-r9"
              active={aggregation === 'h3'}
              onClick={() => setAggregation('h3')}
            />
          </div>
          <p className="mt-3 text-xs leading-5 text-neutral-500">
            H3 is generated in the browser from the shipped MSOA polygons for this prototype.
            A production build should pre-bake true raster-zonal H3 parquet at resolutions 7, 8
            and 9. LSOA remains disabled until an LSOA geometry asset is present.
          </p>
        </section>

        <section className="border-b border-neutral-200 px-5 py-4">
          <h3 className="text-sm font-semibold">Current outputs</h3>
          {stats ? (
            <dl className="mt-3 grid grid-cols-2 gap-2">
              <Stat label="MSOAs rendered" value={stats.total} />
              <Stat label="Boroughs covered" value={stats.boroughs} />
              <Stat label="Mean NDVI 2024" value={stats.meanLate} />
              <Stat label="Mean NDVI 2019" value={stats.meanEarly} />
              <Stat label="Mean delta" value={stats.meanDelta} />
              <Stat label="Greyer in 2024" value={stats.negShare} />
            </dl>
          ) : (
            <p className="mt-3 text-sm text-neutral-500">Loading…</p>
          )}
        </section>

        <section className="border-b border-neutral-200 px-5 py-4">
          <h3 className="text-sm font-semibold">Outputs by place</h3>
          <OutputList
            title="Greenest 2024 MSOAs"
            rows={greenest.map((d) => ({ name: d.name, borough: d.borough, value: d.ndvi_late.toFixed(3) }))}
          />
          <OutputList
            title="Lowest 2024 NDVI"
            rows={lowest.map((d) => ({ name: d.name, borough: d.borough, value: d.ndvi_late.toFixed(3) }))}
          />
          <OutputList
            title="Largest measured decline"
            rows={declines.map((d) => ({
              name: d.name,
              borough: d.borough,
              value: d.delta_ndvi.toFixed(3),
            }))}
          />
        </section>

        <section className="border-b border-neutral-200 px-5 py-4">
          <h3 className="text-sm font-semibold">Top surprises (model residuals)</h3>
          <p className="mt-2 text-xs leading-5 text-neutral-500">
            Where 2024 NDVI deviates most from what the model predicted from urban features alone.
          </p>
          <div className="mt-3 divide-y divide-neutral-100 rounded-md border border-neutral-200">
            {surprises.slice(0, 6).map((d) => (
              <div key={d.code} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 px-3 py-2">
                <div>
                  <div className="text-sm font-medium">{d.name}</div>
                  <div className="text-xs text-neutral-500">{d.borough}</div>
                </div>
                <div
                  className={[
                    'rounded-sm px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
                    d.residual >= 0 ? 'bg-emerald-100 text-emerald-900' : 'bg-rose-100 text-rose-900',
                  ].join(' ')}
                >
                  {d.residual >= 0 ? 'greener' : 'greyer'}
                </div>
                <div className="font-mono text-xs text-neutral-600">
                  z {d.residual_z.toFixed(2)}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="border-b border-neutral-200 px-5 py-4">
          <h3 className="text-sm font-semibold">Challenge answers</h3>
          <div className="mt-3 space-y-2">
            {CHALLENGE_ANSWERS.map((item) => (
              <div key={item.prompt} className="rounded-md border border-neutral-200 px-3 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-semibold">{item.prompt}</div>
                  <div className="shrink-0 rounded-sm bg-neutral-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-neutral-600">
                    {item.status}
                  </div>
                </div>
                <p className="mt-1 text-xs leading-5 text-neutral-600">{item.answer}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="px-5 py-4">
          <h3 className="text-sm font-semibold">ML next steps</h3>
          <p className="mt-3 text-sm leading-6 text-neutral-600">
            The current ML layer is a tree-ensemble residual model with automatic selection between
            RandomForest and ExtraTrees. More interesting next layers are uncertainty bands, H3
            hot/cold spots, LSOA equity residuals, and a compact segmentation model over Sentinel-2
            bands to separate tree canopy, grass, water and bare surface.
          </p>

          <h3 className="mt-5 text-sm font-semibold">What we did</h3>
          <ol className="mt-3 space-y-2 text-sm leading-6 text-neutral-600">
            <li>1. Prepared Sentinel-2 red and near-infrared bands for 23 July 2019 and 29 July 2024.</li>
            <li>2. Computed NDVI as (NIR - Red) / (NIR + Red) at 20 m resolution.</li>
            <li>3. Aggregated each raster snapshot to ONS MSOA 2021 boundaries.</li>
            <li>4. Joined non-satellite features: population, density, park distance and area.</li>
            <li>5. Trained a RandomForest, computed residuals and a surprise score per MSOA.</li>
            <li>6. Rendered the final map with MapLibre GL and deck.gl in a static Next.js app.</li>
          </ol>
          <h3 className="mt-5 text-sm font-semibold">Stack</h3>
          <p className="mt-3 text-sm leading-6 text-neutral-600">
            Next.js 16, React 19, TypeScript, Tailwind CSS, MapLibre GL, deck.gl, GeoJSON, PMTiles,
            Cloud-Optimised GeoTIFFs, Parquet, DuckDB, dbt-duckdb, scikit-learn, pysal, ONS
            boundaries, NOMIS census data and OpenStreetMap parks.
          </p>
        </section>
      </aside>

      <section className="order-1 min-h-[52dvh] min-w-0 lg:order-2 lg:min-h-0">
        <div className="relative h-full min-h-[52dvh] lg:min-h-0">
          <MapClient
            city="london"
            variable={variable}
            aggregation={aggregation}
            anomalies={surprises}
          />
        </div>
      </section>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }): React.JSX.Element {
  return (
    <div className="rounded-md border border-neutral-200 px-3 py-2">
      <dt className="text-[11px] uppercase tracking-[0.1em] text-neutral-500">{label}</dt>
      <dd className="mt-1 font-mono text-sm font-semibold">{value}</dd>
    </div>
  )
}

function GeogButton({
  name,
  status,
  active = false,
  disabled = false,
  onClick,
}: {
  name: string
  status: string
  active?: boolean
  disabled?: boolean
  onClick?: () => void
}): React.JSX.Element {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={[
        'rounded-md border px-3 py-2 text-left',
        active
          ? 'border-emerald-700 bg-emerald-50'
          : 'border-neutral-200 bg-neutral-50 text-neutral-500',
        disabled ? 'cursor-not-allowed' : 'hover:border-neutral-400',
      ].join(' ')}
    >
      <div className={active ? 'font-semibold text-emerald-950' : 'font-semibold text-neutral-700'}>
        {name}
      </div>
      <div className={`mt-1 ${active ? 'text-emerald-800' : ''}`}>{status}</div>
    </button>
  )
}

function OutputList({
  title,
  rows,
}: {
  title: string
  rows: Array<{ name: string; borough: string; value: string }>
}): React.JSX.Element {
  return (
    <div className="mt-3">
      <h4 className="text-xs font-semibold uppercase tracking-[0.1em] text-neutral-500">{title}</h4>
      <div className="mt-2 divide-y divide-neutral-100 rounded-md border border-neutral-200">
        {rows.length === 0 ? (
          <div className="px-3 py-2 text-xs text-neutral-400">Loading…</div>
        ) : (
          rows.map((row) => (
            <div key={`${title}-${row.name}`} className="grid grid-cols-[1fr_auto] gap-3 px-3 py-2">
              <div>
                <div className="text-sm font-medium">{row.name}</div>
                <div className="text-xs text-neutral-500">{row.borough}</div>
              </div>
              <div className="font-mono text-sm">{row.value}</div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function mean(xs: number[]): number {
  return xs.length === 0 ? 0 : xs.reduce((a, b) => a + b, 0) / xs.length
}
