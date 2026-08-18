import { memo } from "react";

/** Perpetual animation, isolated and memoized so its infinite loop can never
 *  drag the dashboard's render cycle with it. */
export const LiveDot = memo(function LiveDot({ color }: { color: string }) {
  return (
    <span className="relative inline-flex h-2 w-2" aria-hidden="true">
      <span
        className="absolute inline-flex h-full w-full rounded-full opacity-60"
        style={{ background: color, animation: "pace-ping 2.4s cubic-bezier(0, 0, 0.2, 1) infinite" }}
      />
      <span className="relative inline-flex h-2 w-2 rounded-full" style={{ background: color }} />
      <style>{`@keyframes pace-ping {
        0% { transform: scale(1); opacity: 0.55; }
        70%, 100% { transform: scale(2.4); opacity: 0; }
      }`}</style>
    </span>
  );
});
