import { motion } from "framer-motion";
import { HeartBreak, Info } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "../../api/client";
import { TooltipShell } from "../../components/ChartTooltip";
import { Skeleton } from "../../components/Skeleton";
import { hms, pace } from "../../lib/format";
import type { Mode } from "../../lib/theme";
import { CHART } from "../../lib/theme";
import type { RunAnalysis, Split } from "../../api/types";

/** Per-kilometre splits and within-run analysis for one activity.
 *  Loaded on expand, never up front: streams are the expensive Strava call and
 *  most rows are never opened. */
export function RunDetail({ activityId, mode }: { activityId: number; mode: Mode }) {
  const c = CHART[mode];
  const [splits, setSplits] = useState<Split[] | null>(null);
  const [analysis, setAnalysis] = useState<RunAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    (async () => {
      try {
        const [s, a] = await Promise.all([api.splits(activityId), api.analysis(activityId)]);
        if (cancelled) return;
        setSplits(s);
        setAnalysis(a);

        // Streams arrive on demand. If this run has none yet, pull them and
        // re-read the analysis so decoupling can appear.
        if (!a.has_streams) {
          const r = await api.fetchStreams(activityId);
          if (!cancelled && r.status === "fetched") {
            setAnalysis(await api.analysis(activityId));
          }
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activityId]);

  if (loading) return <Skeleton className="h-40 w-full" radius="1rem" />;
  if (error) {
    return (
      <p className="py-4 text-[12.5px]" style={{ color: c.critical }}>
        {error}
      </p>
    );
  }

  // Whole kilometres only — a trailing 200 m bar is noise, not a split.
  const whole = (splits ?? []).filter((s) => s.distance_m >= 950 && s.pace_s_per_km);
  const fastest = Math.min(...whole.map((s) => s.pace_s_per_km ?? Infinity));

  const data = whole.map((s) => ({
    km: `${s.split_index}`,
    paceS: s.pace_s_per_km ?? 0,
    hr: s.avg_hr,
    isFastest: s.pace_s_per_km === fastest,
  }));

  const d = analysis?.decoupling;
  const f = analysis?.split_fade;

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      transition={{ type: "spring", stiffness: 120, damping: 22 }}
      className="overflow-hidden"
    >
      <div className="py-4">
        {data.length > 0 ? (
          <>
            <p
              className="mb-3 text-[11.5px] font-medium tracking-wide uppercase"
              style={{ color: "var(--text-muted)" }}
            >
              Pace per kilometre
            </p>
            <div style={{ height: 150 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data} margin={{ top: 6, right: 4, bottom: 0, left: -20 }} barCategoryGap="24%">
                  <XAxis
                    dataKey="km"
                    tick={{ fill: c.text, fontSize: 11 }}
                    axisLine={{ stroke: c.grid }}
                    tickLine={false}
                    tickMargin={8}
                  />
                  <YAxis
                    reversed
                    domain={["dataMin - 15", "dataMax + 15"]}
                    tickFormatter={(v: number) => pace(v)}
                    tick={{ fill: c.text, fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    width={48}
                  />
                  <Tooltip
                    cursor={{ fill: c.grid, fillOpacity: 0.3 }}
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const p = payload[0].payload as (typeof data)[number];
                      return (
                        <TooltipShell
                          title={`Kilometre ${p.km}`}
                          rows={[
                            { label: "Pace", value: `${pace(p.paceS)} /km`, color: c.series1 },
                            ...(p.hr ? [{ label: "Avg HR", value: `${Math.round(p.hr)} bpm` }] : []),
                          ]}
                        />
                      );
                    }}
                  />
                  {/* Axis is reversed, so a taller bar is a faster kilometre. */}
                  <Bar dataKey="paceS" radius={[4, 4, 0, 0]}>
                    {data.map((p) => (
                      <Cell key={p.km} fill={c.series1} fillOpacity={p.isFastest ? 1 : 0.5} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </>
        ) : (
          <p className="text-[12.5px]" style={{ color: "var(--text-muted)" }}>
            No kilometre splits recorded for this run.
          </p>
        )}

        <div className="mt-4 flex flex-wrap gap-x-8 gap-y-3">
          {f?.fade_pct != null && (
            <Stat
              label={f.negative_split ? "Negative split" : "Fade"}
              value={`${f.fade_pct > 0 ? "+" : ""}${f.fade_pct.toFixed(1)}%`}
              tone={f.negative_split ? c.good : f.fade_pct > 5 ? c.warning : undefined}
              note={
                f.first_km_pace_s && f.last_km_pace_s
                  ? `${pace(f.first_km_pace_s)} first, ${pace(f.last_km_pace_s)} last`
                  : undefined
              }
            />
          )}

          {d?.pct != null ? (
            <Stat
              label={`Decoupling (${d.method})`}
              value={`${d.pct > 0 ? "+" : ""}${d.pct.toFixed(1)}%`}
              tone={d.is_concerning ? c.warning : c.good}
              note={d.is_concerning ? "Aerobic durability is the limiter" : "Held effort throughout"}
            />
          ) : (
            <span
              className="flex items-start gap-1.5 text-[12px]"
              style={{ color: "var(--text-muted)" }}
            >
              <HeartBreak size={13} weight="duotone" className="mt-[2px] shrink-0" />
              <span className="max-w-[34ch] leading-relaxed">
                Decoupling needs heart rate. {d?.reason}
              </span>
            </span>
          )}
        </div>

        {analysis && !analysis.has_streams && (
          <p
            className="mt-3 flex items-center gap-1.5 text-[11.5px]"
            style={{ color: "var(--text-muted)" }}
          >
            <Info size={12} weight="fill" />
            Streams unavailable for this run.
          </p>
        )}
      </div>
    </motion.div>
  );
}

function Stat({
  label,
  value,
  tone,
  note,
}: {
  label: string;
  value: string;
  tone?: string;
  note?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span
        className="text-[11px] font-medium tracking-wide uppercase"
        style={{ color: "var(--text-muted)" }}
      >
        {label}
      </span>
      <span
        className="tnum text-[17px] leading-none font-semibold"
        style={{ color: tone ?? "var(--text-primary)" }}
      >
        {value}
      </span>
      {note && (
        <span className="text-[11.5px]" style={{ color: "var(--text-secondary)" }}>
          {note}
        </span>
      )}
    </div>
  );
}

export { hms };
