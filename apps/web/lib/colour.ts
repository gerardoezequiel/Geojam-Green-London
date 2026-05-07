/** Linear interpolation between RGB colours.
 *
 * Given a numeric value and a colour ramp (sorted ascending stops), return the
 * interpolated RGBA tuple. Used for choropleth fill colours driven by
 * mean_ndvi_late, mean_delta_ndvi etc.
 */

type Stop = [number, [number, number, number]]
type Ramp = readonly Stop[]

export const RAMP_NDVI: Ramp = [
  [0.0, [165, 0, 38]],
  [0.15, [215, 48, 39]],
  [0.25, [244, 109, 67]],
  [0.35, [253, 174, 97]],
  [0.45, [254, 224, 144]],
  [0.55, [217, 239, 139]],
  [0.65, [166, 217, 106]],
  [0.75, [102, 189, 99]],
  [0.85, [26, 152, 80]],
]

export const RAMP_DELTA: Ramp = [
  [-0.25, [103, 0, 31]],
  [-0.15, [178, 24, 43]],
  [-0.08, [214, 96, 77]],
  [-0.03, [244, 165, 130]],
  [0.0, [247, 247, 247]],
  [0.03, [146, 197, 222]],
  [0.08, [67, 147, 195]],
  [0.15, [33, 102, 172]],
  [0.25, [5, 48, 97]],
]

export function rampLookup(ramp: Ramp, value: number, alpha = 200): [number, number, number, number] {
  if (Number.isNaN(value)) return [180, 180, 180, 60]
  if (value <= ramp[0][0]) return [...ramp[0][1], alpha] as [number, number, number, number]
  const last = ramp[ramp.length - 1]
  if (value >= last[0]) return [...last[1], alpha] as [number, number, number, number]
  for (let i = 0; i < ramp.length - 1; i += 1) {
    const [a, ca] = ramp[i]
    const [b, cb] = ramp[i + 1]
    if (value >= a && value <= b) {
      const t = (value - a) / (b - a)
      return [
        Math.round(ca[0] + (cb[0] - ca[0]) * t),
        Math.round(ca[1] + (cb[1] - ca[1]) * t),
        Math.round(ca[2] + (cb[2] - ca[2]) * t),
        alpha,
      ]
    }
  }
  return [180, 180, 180, alpha]
}

export const VARIABLES = {
  mean_ndvi_late: { label: 'NDVI 2024', ramp: RAMP_NDVI, range: [0.05, 0.55] },
  mean_ndvi_early: { label: 'NDVI 2019', ramp: RAMP_NDVI, range: [0.1, 0.7] },
  mean_delta_ndvi: { label: 'NDVI change 2019-2024', ramp: RAMP_DELTA, range: [-0.25, 0.05] },
} as const

export type VariableKey = keyof typeof VARIABLES
