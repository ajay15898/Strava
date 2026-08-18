import { motion } from "framer-motion";
import { ArrowBendDownRight, CheckCircle, Info, Warning } from "@phosphor-icons/react";

import { api } from "../../api/client";
import { Panel, PanelHeading } from "../../components/Panel";
import { Skeleton } from "../../components/Skeleton";
import { mediumDate } from "../../lib/format";
import type { Mode } from "../../lib/theme";
import { CHART } from "../../lib/theme";
import { useApi } from "../../lib/useApi";
import type { AdaptationSeverity } from "../../api/types";

const ICON = {
  action: ArrowBendDownRight,
  warning: Warning,
  info: Info,
} as const;

/** This week against what was prescribed, plus anything the adaptation rules
 *  have to say. The rules are deterministic — same history, same output — so
 *  this panel is a readout, never a suggestion generated on the fly. */
export function WeekDigest({ mode }: { mode: Mode }) {
  const c = CHART[mode];
  const digest = useApi(() => api.digest(), []);

  if (digest.loading) {
    return (
      <Panel>
        <PanelHeading title="This week" />
        <Skeleton className="h-24 w-full" radius="1rem" />
      </Panel>
    );
  }

  // A missing plan is already reported by the plan panel; stay quiet here.
  if (digest.error || !digest.data) return null;

  const d = digest.data;
  const pct = Math.round(d.completion * 100);
  const toneFor = (s: AdaptationSeverity) =>
    s === "action" ? c.critical : s === "warning" ? c.warning : c.series1;

  return (
    <Panel>
      <PanelHeading
        title={`Week ${d.week_no}`}
        hint={`From ${mediumDate(d.week_start)} · deterministic rules, no model judgement`}
        aside={
          <span className="tnum text-[12.5px]" style={{ color: "var(--text-muted)" }}>
            {d.sessions_done}/{d.sessions_total} sessions
          </span>
        }
      />

      <div className="mb-6 flex flex-wrap items-end gap-x-10 gap-y-4">
        <div className="flex flex-col gap-1">
          <span
            className="text-[11.5px] font-medium tracking-wide uppercase"
            style={{ color: "var(--text-muted)" }}
          >
            Completed
          </span>
          <span className="flex items-baseline gap-1.5">
            <span
              className="tnum text-[26px] leading-none font-semibold tracking-tight"
              style={{ color: "var(--text-primary)" }}
            >
              {d.actual_km.toFixed(1)}
            </span>
            <span className="text-[12.5px]" style={{ color: "var(--text-muted)" }}>
              of {d.planned_km.toFixed(1)} km
            </span>
          </span>
        </div>

        {/* A single progress bar, not a chart — one number does not need axes. */}
        <div className="min-w-[180px] flex-1">
          <div
            className="h-2 w-full overflow-hidden rounded-full"
            style={{ background: "var(--surface-sunken)" }}
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Week completion"
          >
            <motion.div
              className="h-full rounded-full"
              style={{ background: c.series1 }}
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(pct, 100)}%` }}
              transition={{ type: "spring", stiffness: 90, damping: 20 }}
            />
          </div>
          <span className="tnum mt-1.5 block text-[12px]" style={{ color: "var(--text-muted)" }}>
            {pct}% of the week
          </span>
        </div>
      </div>

      {d.adaptations.length === 0 ? (
        <p
          className="flex items-center gap-2 text-[13px]"
          style={{ color: "var(--text-secondary)" }}
        >
          <CheckCircle size={15} weight="fill" style={{ color: c.good }} />
          On plan — no adaptations triggered.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {d.adaptations.map((a) => {
            const tone = toneFor(a.severity);
            const Icon = ICON[a.severity];
            return (
              <li
                key={`${a.rule}-${a.message}`}
                className="flex gap-2.5 rounded-xl p-3.5"
                style={{ background: `${tone}14` }}
              >
                <Icon
                  size={15}
                  weight="fill"
                  style={{ color: tone }}
                  className="mt-[2px] shrink-0"
                />
                <div className="min-w-0">
                  <span
                    className="text-[12.5px] leading-relaxed"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {a.message}
                  </span>
                  {a.action !== "none" && (
                    <span
                      className="mt-1.5 block text-[11px] font-medium tracking-wide uppercase"
                      style={{ color: tone }}
                    >
                      {a.action.replace(/_/g, " ")}
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
