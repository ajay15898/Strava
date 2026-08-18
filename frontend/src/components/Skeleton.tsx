import { memo } from "react";

/** Shimmer is a perpetual animation, so it lives in its own memoized leaf and
 *  never re-renders with the page around it. */
export const Skeleton = memo(function Skeleton({
  className = "",
  radius = "0.75rem",
}: {
  className?: string;
  radius?: string;
}) {
  return (
    <div
      className={`relative overflow-hidden ${className}`}
      style={{ background: "var(--surface-sunken)", borderRadius: radius }}
    >
      <div
        className="absolute inset-0 -translate-x-full"
        style={{
          animation: "pace-shimmer 1.6s cubic-bezier(0.16, 1, 0.3, 1) infinite",
          background:
            "linear-gradient(90deg, transparent, rgb(255 255 255 / 0.14) 45%, transparent)",
        }}
      />
      <style>{`@keyframes pace-shimmer { 100% { transform: translateX(100%); } }`}</style>
    </div>
  );
});

/** Matches the real chart's geometry so nothing shifts when data lands. */
export function ChartSkeleton({ bars = 8, height = 220 }: { bars?: number; height?: number }) {
  // Fixed pattern, not random: a skeleton that reshuffles on every render reads
  // as a glitch rather than as loading.
  const heights = [42, 63, 51, 78, 35, 88, 58, 70, 46, 66, 54, 82];

  return (
    <div className="flex items-end gap-2" style={{ height }} aria-hidden="true">
      {Array.from({ length: bars }, (_, i) => (
        <div key={i} className="flex-1" style={{ height: `${heights[i % heights.length]}%` }}>
          <Skeleton className="h-full w-full" radius="4px" />
        </div>
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-3" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-11 w-full" radius="0.6rem" />
      ))}
    </div>
  );
}
