import { motion } from "framer-motion";
import { CaretRight, HeartBreak } from "@phosphor-icons/react";
import { useState } from "react";

import { EmptyState } from "../../components/States";
import { hms, km, mediumDate, pace } from "../../lib/format";
import type { Mode } from "../../lib/theme";
import { RunDetail } from "./RunDetail";
import type { Activity } from "../../api/types";

/** Rows separated by hairlines rather than boxed in cards — at this count the
 *  boxes would be pure chrome. */
export function ActivityTable({
  runs,
  limit,
  mode,
}: {
  runs: Activity[];
  limit?: number;
  mode: Mode;
}) {
  const rows = limit ? runs.slice(0, limit) : runs;
  const [open, setOpen] = useState<number | null>(null);

  if (rows.length === 0) {
    return (
      <EmptyState
        title="No runs in this range"
        body="Widen the date range, or run a sync to pull in anything recorded since the last import."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] border-collapse text-left">
        <thead>
          <tr
            className="border-b text-[11.5px] font-medium tracking-wide uppercase"
            style={{ borderColor: "var(--border-hairline)", color: "var(--text-muted)" }}
          >
            <th className="pb-2.5 font-medium">Date</th>
            <th className="pb-2.5 font-medium">Run</th>
            <th className="pb-2.5 text-right font-medium">Distance</th>
            <th className="pb-2.5 text-right font-medium">Time</th>
            <th className="pb-2.5 text-right font-medium">Pace</th>
            <th className="pb-2.5" />
          </tr>
        </thead>
        <tbody>
          {rows.flatMap((r, i) => {
            const paceS = r.moving_time_s / (r.distance_m / 1000);
            const isOpen = open === r.id;
            return [
              <motion.tr
                key={r.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: Math.min(i * 0.025, 0.4), duration: 0.3 }}
                className="cursor-pointer border-b transition-colors last:border-b-0"
                style={{ borderColor: "var(--border-hairline)" }}
                onClick={() => setOpen(isOpen ? null : r.id)}
              >
                <td
                  className="py-3 text-[13px] whitespace-nowrap"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {mediumDate(r.start_local)}
                </td>
                <td className="py-3 pr-4 text-[13.5px]" style={{ color: "var(--text-primary)" }}>
                  <span className="flex items-center gap-2">
                    <span className="truncate">{r.name ?? "Run"}</span>
                    {!r.has_heartrate && (
                      <HeartBreak
                        size={13}
                        weight="duotone"
                        style={{ color: "var(--text-muted)" }}
                        aria-label="No heart-rate data"
                      />
                    )}
                  </span>
                </td>
                <td
                  className="tnum py-3 text-right text-[13.5px] font-medium"
                  style={{ color: "var(--text-primary)" }}
                >
                  {km(r.distance_m)}
                </td>
                <td
                  className="tnum py-3 text-right text-[13.5px]"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {hms(r.moving_time_s)}
                </td>
                <td
                  className="tnum py-3 text-right text-[13.5px]"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {pace(paceS)}
                </td>
                <td className="py-3 pl-2 text-right">
                  <CaretRight
                    size={13}
                    weight="bold"
                    style={{
                      color: "var(--text-muted)",
                      transform: isOpen ? "rotate(90deg)" : undefined,
                      transition: "transform 200ms cubic-bezier(0.16, 1, 0.3, 1)",
                    }}
                  />
                </td>
              </motion.tr>,
              ...(isOpen
                ? [
                    <tr key={`${r.id}-detail`}>
                      <td colSpan={6} className="px-1">
                        <RunDetail activityId={r.id} mode={mode} />
                      </td>
                    </tr>,
                  ]
                : []),
            ];
          })}
        </tbody>
      </table>
    </div>
  );
}
