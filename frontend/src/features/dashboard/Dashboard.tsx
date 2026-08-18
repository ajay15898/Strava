import { motion } from "framer-motion";
import { CalendarX, Heartbeat, Path, TrendUp } from "@phosphor-icons/react";

import { api } from "../../api/client";
import { Legend } from "../../components/ChartTooltip";
import { Panel, PanelHeading } from "../../components/Panel";
import { ChartSkeleton, Skeleton, TableSkeleton } from "../../components/Skeleton";
import { EmptyState, ErrorState } from "../../components/States";
import { StatTile } from "../../components/StatTile";
import { ActivityTable } from "../activities/ActivityTable";
import { PlanView } from "../plan/PlanView";
import { CoachPanel } from "../coach/CoachPanel";
import { WeekDigest } from "../plan/WeekDigest";
import { hms, mediumDate } from "../../lib/format";
import type { Mode } from "../../lib/theme";
import { CHART } from "../../lib/theme";
import { useApi } from "../../lib/useApi";
import { LoadChart } from "./LoadChart";
import { PaceCurve } from "./PaceCurve";
import { PredictionHero } from "./PredictionHero";
import { RunScatter } from "./RunScatter";
import { VolumeChart } from "./VolumeChart";

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07, delayChildren: 0.04 } },
};

export function Dashboard({ mode }: { mode: Mode }) {
  const c = CHART[mode];

  const athlete = useApi(() => api.athlete(), []);
  const summary = useApi(() => api.summary(), []);
  const load = useApi(() => api.load(), []);
  const curve = useApi(() => api.curve(), []);
  const prediction = useApi(() => api.prediction(), []);
  const feasibility = useApi(() => api.feasibility(), []);
  const runs = useApi(() => api.activities({ type: "Run", limit: 400 }), []);

  // A missing athlete is the one failure that blocks everything, so it takes
  // over the page rather than repeating itself in six panels.
  if (summary.status === 404 && summary.error) {
    return (
      <Panel>
        <ErrorState detail={summary.error} status={summary.status} onRetry={summary.reload} />
      </Panel>
    );
  }

  const s = summary.data;
  const currentLoad = load.data?.at(-1);

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="flex flex-col gap-6">
      {/* Prediction: the reason the page exists, so it gets the widest radius
          and the most air. */}
      <Panel className="!rounded-[2.5rem]">
        {prediction.loading || feasibility.loading ? (
          <div className="grid gap-10 lg:grid-cols-[1.35fr_1fr]">
            <div className="flex flex-col gap-4">
              <Skeleton className="h-3.5 w-44" />
              <Skeleton className="h-20 w-72" radius="1rem" />
              <Skeleton className="h-3.5 w-56" />
            </div>
            <div className="flex flex-col gap-2.5">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          </div>
        ) : prediction.error || feasibility.error ? (
          <ErrorState
            detail={prediction.error ?? feasibility.error ?? "Unavailable"}
            status={prediction.status ?? feasibility.status}
            onRetry={() => {
              prediction.reload();
              feasibility.reload();
            }}
          />
        ) : prediction.data && feasibility.data ? (
          <PredictionHero
            prediction={prediction.data}
            feasibility={feasibility.data}
            goalTimeS={athlete.data?.goal_time_s ?? null}
            goalDate={athlete.data?.goal_race_date ?? null}
            mode={mode}
          />
        ) : null}
      </Panel>

      {/* Metrics grouped by negative space and a hairline, not by boxes. */}
      <Panel>
        {summary.loading ? (
          <div className="grid gap-8 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="flex flex-col gap-2">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-7 w-20" />
                <Skeleton className="h-3 w-32" />
              </div>
            ))}
          </div>
        ) : s ? (
          <motion.div variants={container} className="grid gap-8 sm:grid-cols-2 xl:grid-cols-4">
            <StatTile
              label="Last 2 weeks"
              value={s.km_per_week_2wk.toFixed(1)}
              unit="km / wk"
              icon={<TrendUp size={13} weight="bold" />}
              note={`Trailing 4 weeks: ${s.km_per_week_4wk.toFixed(1)} km/wk`}
            />
            <StatTile
              label="Total volume"
              value={s.total_km.toFixed(1)}
              unit="km"
              icon={<Path size={13} weight="bold" />}
              note={`${s.total_run_days} run days since ${mediumDate(s.window_start)}`}
            />
            <StatTile
              label="Longest gap"
              value={String(s.longest_gap_days)}
              unit="days"
              accent={s.longest_gap_days >= 7 ? c.warning : undefined}
              icon={<CalendarX size={13} weight="bold" />}
              note={`${s.gaps.length} gaps of a week or more`}
            />
            <StatTile
              label="Form (TSB)"
              value={currentLoad ? currentLoad.tsb.toFixed(1) : "—"}
              accent={currentLoad && currentLoad.tsb < -20 ? c.critical : undefined}
              icon={<Heartbeat size={13} weight="bold" />}
              note={
                currentLoad
                  ? `Fitness ${currentLoad.ctl.toFixed(1)} · Fatigue ${currentLoad.atl.toFixed(1)}`
                  : "No load data"
              }
            />
          </motion.div>
        ) : null}
      </Panel>

      <WeekDigest mode={mode} />

      <CoachPanel mode={mode} />

      <PlanView mode={mode} />

      {/* Asymmetric: the scatter carries the story, the gap list annotates it. */}
      <div className="grid gap-6 lg:grid-cols-[1.75fr_1fr]">
        <Panel>
          <PanelHeading
            title="Every run, by date and distance"
            hint="Empty vertical bands are training gaps — the pattern this plan exists to break."
          />
          {runs.loading ? (
            <ChartSkeleton bars={14} height={260} />
          ) : runs.error ? (
            <ErrorState detail={runs.error} status={runs.status} onRetry={runs.reload} />
          ) : runs.data && runs.data.length > 0 ? (
            <div style={{ height: 260 }}>
              <RunScatter runs={runs.data} mode={mode} />
            </div>
          ) : (
            <EmptyState title="No runs yet" body="Run a backfill to import your Strava history." />
          )}
        </Panel>

        <Panel>
          <PanelHeading title="Interruptions" hint="Gaps of seven days or more." />
          {summary.loading ? (
            <TableSkeleton rows={5} />
          ) : s && s.gaps.length > 0 ? (
            <ul className="flex flex-col">
              {s.gaps.map((g) => (
                <li
                  key={g.start}
                  className="flex items-center justify-between gap-4 border-t py-3 first:border-t-0"
                  style={{ borderColor: "var(--border-hairline)" }}
                >
                  <span className="text-[13px]" style={{ color: "var(--text-secondary)" }}>
                    {mediumDate(g.start)} &rarr; {mediumDate(g.end)}
                  </span>
                  <span
                    className="tnum shrink-0 rounded-full px-2.5 py-1 text-[12px] font-medium"
                    style={{
                      background: g.days >= 10 ? `${c.warning}1f` : "var(--surface-sunken)",
                      color: g.days >= 10 ? c.warning : "var(--text-secondary)",
                    }}
                  >
                    {g.days}d
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No gaps" body="No break of a week or more in this window." />
          )}
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.25fr]">
        <Panel>
          <PanelHeading title="Weekly volume" hint="Last eight weeks. Peak week at full strength." />
          {summary.loading ? (
            <ChartSkeleton bars={8} height={230} />
          ) : s && s.weeks.length > 0 ? (
            <div style={{ height: 230 }}>
              <VolumeChart weeks={s.weeks} mode={mode} />
            </div>
          ) : (
            <EmptyState title="No weekly data" body="Import activities to see volume by week." />
          )}
        </Panel>

        <Panel>
          <PanelHeading
            title="Pace at distance"
            hint="Best recorded effort at each distance, from Strava's own best-effort records."
          />
          {curve.loading ? (
            <ChartSkeleton bars={8} height={230} />
          ) : curve.error ? (
            <ErrorState detail={curve.error} status={curve.status} onRetry={curve.reload} />
          ) : curve.data && curve.data.length > 0 ? (
            <div style={{ height: 230 }}>
              <PaceCurve points={curve.data} mode={mode} />
            </div>
          ) : (
            <EmptyState
              title="No best efforts"
              body="Best efforts arrive with activity detail. Run a backfill to populate them."
            />
          )}
        </Panel>
      </div>

      <Panel>
        <PanelHeading
          title="Fitness and fatigue"
          hint="Load is derived from pace against threshold, not heart rate — none is recorded."
          aside={
            <Legend
              items={[
                { name: "Fitness (CTL)", color: c.series1 },
                { name: "Fatigue (ATL)", color: c.series2 },
              ]}
            />
          }
        />
        {load.loading ? (
          <ChartSkeleton bars={20} height={250} />
        ) : load.error ? (
          <ErrorState detail={load.error} status={load.status} onRetry={load.reload} />
        ) : load.data && load.data.length > 0 ? (
          <div style={{ height: 250 }}>
            <LoadChart days={load.data} mode={mode} />
          </div>
        ) : (
          <EmptyState title="No load series" body="Load is computed from imported activities." />
        )}
      </Panel>

      <Panel>
        <PanelHeading
          title="Recent runs"
          hint={
            s && !s.has_recent_heartrate
              ? "No heart rate recorded on any recent run — effort data is power and pace only."
              : undefined
          }
          aside={
            runs.data ? (
              <span className="tnum text-[12.5px]" style={{ color: "var(--text-muted)" }}>
                {runs.data.length} runs
              </span>
            ) : undefined
          }
        />
        {runs.loading ? (
          <TableSkeleton rows={8} />
        ) : runs.error ? (
          <ErrorState detail={runs.error} status={runs.status} onRetry={runs.reload} />
        ) : runs.data ? (
          <ActivityTable runs={runs.data} limit={12} />
        ) : null}
      </Panel>

      {s && (
        <p className="px-2 pb-2 text-[12px]" style={{ color: "var(--text-muted)" }}>
          Window {mediumDate(s.window_start)} &rarr; {mediumDate(s.window_end)} ·{" "}
          {s.total_km.toFixed(1)} km over {s.total_run_days} run days · duplicates and sub-500 m
          records excluded ·{" "}
          {s.last_heartrate_date
            ? `last heart rate ${mediumDate(s.last_heartrate_date)}`
            : "no heart-rate data on record"}
          {prediction.data && ` · projection ${hms(prediction.data.predicted_time_s)}`}
        </p>
      )}
    </motion.div>
  );
}
