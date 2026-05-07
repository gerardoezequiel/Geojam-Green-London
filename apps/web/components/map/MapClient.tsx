'use client'

import dynamic from 'next/dynamic'

const MapView = dynamic(() => import('@/components/map/MapView'), { ssr: false })

interface MapClientProps {
  city?: 'london' | 'berlin' | 'paris'
  variable?: 'mean_ndvi_late' | 'mean_ndvi_early' | 'mean_delta_ndvi'
}

export default function MapClient(props: MapClientProps): React.JSX.Element {
  return <MapView {...props} />
}
