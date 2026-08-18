import { motion } from "framer-motion";
import type { ReactNode } from "react";

/** Deliberately not a card. At this density, metrics are grouped by a hairline
 *  and negative space rather than boxed — boxes here would add chrome without
 *  adding hierarchy. */
export function StatTile({
  label,
  value,
  unit,
  note,
  accent,
  icon,
}: {
  label: string;
  value: string;
  unit?: string;
  note?: ReactNode;
  accent?: string;
  icon?: ReactNode;
}) {
  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 10 },
        show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 110, damping: 20 } },
      }}
      className="flex flex-col gap-1.5"
    >
      <span
        className="flex items-center gap-1.5 text-[12px] font-medium tracking-wide uppercase"
        style={{ color: "var(--text-muted)" }}
      >
        {icon}
        {label}
      </span>
      <span className="flex items-baseline gap-1.5">
        <span
          className="tnum text-[28px] leading-none font-semibold tracking-tight"
          style={{ color: accent ?? "var(--text-primary)" }}
        >
          {value}
        </span>
        {unit && (
          <span className="text-[13px] font-medium" style={{ color: "var(--text-muted)" }}>
            {unit}
          </span>
        )}
      </span>
      {note && (
        <span className="text-[12.5px] leading-relaxed" style={{ color: "var(--text-secondary)" }}>
          {note}
        </span>
      )}
    </motion.div>
  );
}
