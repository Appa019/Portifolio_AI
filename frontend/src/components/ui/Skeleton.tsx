interface SkeletonProps {
  width?: string
  height?: string
  className?: string
}

export default function Skeleton({ width = '100%', height = '1rem', className = '' }: SkeletonProps) {
  return (
    <div
      className={`skeleton-shimmer ${className}`}
      style={{ width, height }}
    />
  )
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="p-5" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <Skeleton width="40%" height="0.75rem" className="mb-3" />
      <Skeleton width="60%" height="1.5rem" className="mb-2" />
      {Array.from({ length: lines - 1 }).map((_, i) => (
        <Skeleton key={i} width={`${70 - i * 15}%`} height="0.75rem" className="mb-1.5" />
      ))}
    </div>
  )
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <div className="px-5 py-4" style={{ borderBottom: '1px solid #e2e8f0' }}>
        <Skeleton width="30%" height="0.875rem" />
      </div>
      <div className="p-4 space-y-3">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex gap-4">
            {Array.from({ length: cols }).map((_, c) => (
              <Skeleton key={c} width={`${100 / cols}%`} height="0.75rem" />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
