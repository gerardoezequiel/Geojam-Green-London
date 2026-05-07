import ProjectDashboard from '@/components/ProjectDashboard'

export default function Page(): React.JSX.Element {
  return (
    <main className="flex h-dvh flex-col">
      <header className="flex items-center justify-between border-b border-black/5 bg-white px-5 py-3 dark:border-white/10">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-semibold tracking-tight">Green London</h1>
          <span className="text-xs text-neutral-500 dark:text-neutral-400">
            Sentinel-2 NDVI by MSOA
          </span>
        </div>
        <nav className="flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400">
          <span className="rounded-full border border-black/10 px-2 py-0.5 dark:border-white/10">
            phase 0
          </span>
        </nav>
      </header>
      <ProjectDashboard />
    </main>
  )
}
