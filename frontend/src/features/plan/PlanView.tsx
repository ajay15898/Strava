import { motion } from "framer-motion";
import {
  ArrowsClockwise,
  CheckCircle,
  Circle,
  Flag,
  Lightning,
  Path,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import { useState } from "react";

import { api } from "../../api/client";
import { Panel, PanelHeading } from "../../components/Panel";
import { Skeleton, TableSkeleton } from "../../components/Skeleton";
import { EmptyState, ErrorState } from "../../components/States";
import { km, mediumDate, pace } from "../../lib/format";
import type { Mode } from "../../lib/theme";
import { CHART } from "../../lib/theme";
import { useApi } from "../../lib/useApi";
import type { PlanSession, PlanWeek, SessionStatus } from "../../api/types";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const PHASE_OF: Record<string, string> = {
  race: "Race week",
  taper: "Taper",
};

function SessionIcon({ type }: { type: string }) {
  if (type === "race") return <Flag size={14} weight="fill" />;
  if (type === "threshold") return <Lightning size={14} weight="fill" />;
  if (type === "long") return <Path size={14} weight="bold" />;
  return <Circle size={14} weight="bold" />;
}

function StatusControl({
  session,
  onChange,
  mode,
}: {
  session: PlanSession;
  onChange: (status: SessionStatus) => void;
  mode: Mode;
}) {
  const c = CHART[mode];
  const done = session.status === "done";
  const missed = session.status === "missed";

  const color = done ? c.good : missed ? c.critical : "var(--text-muted)";
  const Icon = done ? CheckCircle : missed ? XCircle : Circle;

  return (
    <button
      type="button"
      aria-label={done ? "Mark as not done" : "Mark as done"}
      onClick={() => onChange(done ? "planned" : "done")}
      className="grid h-7 w-7 shrink-0 place-items-center rounded-full transition-transform duration-200 active:scale-90"
      style={{ color }}
    >
      <Icon size={17} weight={done || missed ? "fill" : "bold"} />
    </button>
  );
}

function WeekRow({
  week,
  isCurrent,
  onStatus,
  mode,
}: {
  week: PlanWeek;
  isCurrent: boolean;
  onStatus: (id: number, status: SessionStatus) => void;
  mode: Mode;
}) {
  const c = CHART[mode];
  const phaseLabel = week.race_km > 0 ? PHASE_OF.race : undefined;

  return (
    <motion.li
      variants={{
        hidden: { opacity: 0, y: 10 },
        show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 110, damping: 20 } },
      }}
      className="border-t py-5 first:border-t-0"
      style={{ borderColor: "var(--border-hairline)" }}
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="flex items-center gap-2.5">
          <span
            className="text-[13.5px] font-semibold tracking-tight"
            style={{ color: isCurrent ? c.series1 : "var(--text-primary)" }}
          >
            Week {week.week_no}
          </span>
          <span className="text-[12.5px]" style={{ color: "var(--text-muted)" }}>
            {mediumDate(week.start)}
          </span>
          {phaseLabel && (
            <span
              className="rounded-full px-2 py-0.5 text-[11px] font-medium"
              style={{ background: `${c.warning}1f`, color: c.warning }}
            >
              {phaseLabel}
            </span>
          )}
          {isCurrent && (
            <span
              className="rounded-full px-2 py-0.5 text-[11px] font-medium"
              style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
            >
              This week
            </span>
          )}
        </span>
        <span className="tnum text-[12.5px]" style={{ color: "var(--text-secondary)" }}>
          {week.target_km.toFixed(1)} km
          {week.long_run_m > 0 && ` · long ${(week.long_run_m / 1000).toFixed(1)} km`}
        </span>
      </div>

      <div className="flex flex-col gap-1">
        {week.sessions.map((s) => (
          <div
            key={s.id}
            className="flex items-center gap-3 rounded-lg py-1.5"
            style={{ opacity: s.status === "missed" ? 0.55 : 1 }}
          >
            <StatusControl session={s} onChange={(st) => onStatus(s.id, st)} mode={mode} />

            <span
              className="w-9 shrink-0 text-[12px] font-medium"
              style={{ color: "var(--text-muted)" }}
            >
              {DAYS[s.day_of_week]}
            </span>

            <span
              className="flex w-[104px] shrink-0 items-center gap-1.5 text-[13px] capitalize"
              style={{
                color: s.session_type === "race" ? c.series2 : "var(--text-primary)",
              }}
            >
              <SessionIcon type={s.session_type} />
              {s.session_type}
            </span>

            <span
              className="tnum w-[68px] shrink-0 text-right text-[13px] font-medium"
              style={{
                color: "var(--text-primary)",
                textDecoration: s.status === "done" ? "line-through" : undefined,
              }}
            >
              {s.target_distance_m ? `${km(s.target_distance_m, 1)} km` : "—"}
            </span>

            <span className="tnum text-[12.5px]" style={{ color: "var(--text-secondary)" }}>
              {s.target_pace_low && s.target_pace_high
                ? `${pace(s.target_pace_low)}–${pace(s.target_pace_high)}`
                : ""}
            </span>

            {s.structure?.reps ? (
              <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>
                {String(s.structure.reps)}×{String(s.structure.rep_minutes)}min
              </span>
            ) : null}
          </div>
        ))}
      </div>
    </motion.li>
  );
}

export function PlanView({ mode }: { mode: Mode }) {
  const c = CHART[mode];
  const plan = useApi(() => api.plan(), []);
  const [busy, setBusy] = useState(false);

  const generate = async () => {
    setBusy(true);
    try {
      await api.generatePlan();
      plan.reload();
    } finally {
      setBusy(false);
    }
  };

  const setStatus = async (id: number, status: SessionStatus) => {
    await api.setSessionStatus(id, status);
    plan.reload();
  };

  const generateButton = (
    <button
      type="button"
      onClick={generate}
      disabled={busy}
      className="inline-flex items-center gap-2 rounded-full px-3.5 py-2 text-[12.5px] font-medium text-white transition-transform duration-200 active:scale-[0.98] disabled:opacity-60"
      style={{ background: "var(--accent)" }}
    >
      <ArrowsClockwise size={14} weight="bold" className={busy ? "animate-spin" : undefined} />
      {busy ? "Generating…" : plan.data ? "Regenerate" : "Generate plan"}
    </button>
  );

  if (plan.loading) {
    return (
      <Panel>
        <PanelHeading title="Training plan" />
        <Skeleton className="mb-5 h-16 w-full" radius="1rem" />
        <TableSkeleton rows={6} />
      </Panel>
    );
  }

  if (plan.status === 404) {
    return (
      <Panel>
        <PanelHeading title="Training plan" aside={generateButton} />
        <EmptyState
          title="No plan yet"
          body="Generate one from your current fitness. The engine is deterministic — same inputs, same plan, every time."
        />
      </Panel>
    );
  }

  if (plan.error || !plan.data) {
    return (
      <Panel>
        <ErrorState
          detail={plan.error ?? "Unavailable"}
          status={plan.status}
          onRetry={plan.reload}
        />
      </Panel>
    );
  }

  const p = plan.data;
  const meta = p.meta;
  const today = new Date().toISOString().slice(0, 10);
  const done = p.compliance.done ?? 0;
  const total = Object.values(p.compliance).reduce((a, b) => a + b, 0);

  return (
    <Panel>
      <PanelHeading
        title="Training plan"
        hint={`${p.weeks} weeks to ${mediumDate(p.race_date)} · engine ${p.engine_version} · goal ${p.goal_time_display}`}
        aside={generateButton}
      />

      {/* Targets, grouped by space rather than boxed. */}
      {meta && (
        <div className="mb-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { label: "Peak week", value: `${meta.peak_weekly_km.toFixed(1)}`, unit: "km" },
            {
              label: "Peak long run",
              value: (meta.peak_long_run_m / 1000).toFixed(1),
              unit: "km",
            },
            { label: "Total volume", value: meta.total_km.toFixed(0), unit: "km" },
            { label: "Completed", value: `${done}/${total}`, unit: "sessions" },
          ].map((t) => (
            <div key={t.label} className="flex flex-col gap-1">
              <span
                className="text-[11.5px] font-medium tracking-wide uppercase"
                style={{ color: "var(--text-muted)" }}
              >
                {t.label}
              </span>
              <span className="flex items-baseline gap-1.5">
                <span
                  className="tnum text-[22px] leading-none font-semibold tracking-tight"
                  style={{ color: "var(--text-primary)" }}
                >
                  {t.value}
                </span>
                <span className="text-[12px]" style={{ color: "var(--text-muted)" }}>
                  {t.unit}
                </span>
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Warnings are part of the plan, not a footnote. A compressed block has
          real costs and the athlete should see them before week one. */}
      {meta && meta.warnings.length > 0 && (
        <ul className="mb-6 flex flex-col gap-2">
          {meta.warnings.map((w) => (
            <li
              key={w}
              className="flex gap-2.5 rounded-xl p-3.5"
              style={{ background: `${c.warning}14` }}
            >
              <WarningCircle
                size={15}
                weight="fill"
                style={{ color: c.warning }}
                className="mt-[2px] shrink-0"
              />
              <span
                className="text-[12.5px] leading-relaxed"
                style={{ color: "var(--text-secondary)" }}
              >
                {w}
              </span>
            </li>
          ))}
        </ul>
      )}

      <motion.ul
        variants={{ hidden: {}, show: { transition: { staggerChildren: 0.05 } } }}
        initial="hidden"
        animate="show"
        className="flex flex-col"
      >
        {p.weeks_detail.map((w) => (
          <WeekRow
            key={w.week_no}
            week={w}
            isCurrent={today >= w.start && today <= w.end}
            onStatus={setStatus}
            mode={mode}
          />
        ))}
      </motion.ul>

      {meta && (
        <p className="mt-5 text-[12px]" style={{ color: "var(--text-muted)" }}>
          Paces derived from a {(meta.reference.distance_m / 1000).toFixed(0)} K in{" "}
          {Math.floor(meta.reference.duration_s / 60)}:
          {String(meta.reference.duration_s % 60).padStart(2, "0")} · easy{" "}
          {pace(meta.paces.easy.low)}–{pace(meta.paces.easy.high)} · long{" "}
          {pace(meta.paces.long.low)}–{pace(meta.paces.long.high)} · threshold{" "}
          {pace(meta.paces.threshold.low)}–{pace(meta.paces.threshold.high)} · goal{" "}
          {pace(meta.paces.goal.low)}–{pace(meta.paces.goal.high)} /km
        </p>
      )}
    </Panel>
  );
}
