import { motion } from "framer-motion";
import { CheckCircle, Info, Warning, WarningOctagon } from "@phosphor-icons/react";

import { LiveDot } from "../../components/LiveDot";
import { hms, mediumDate, pace } from "../../lib/format";
import type { Mode } from "../../lib/theme";
import { CHART } from "../../lib/theme";
import type { Feasibility, Prediction, Verdict } from "../../api/types";

const VERDICT: Record<Verdict, { label: string; tone: "good" | "warning" | "critical" }> = {
  on_track: { label: "On track", tone: "good" },
  tight: { label: "Tight", tone: "warning" },
  unrealistic: { label: "Not yet supported", tone: "critical" },
};

const LIMITER_COPY: Record<string, string> = {
  long_run_durability: "Long-run durability",
  weekly_volume: "Weekly volume",
  speed: "Raw speed",
  none: "Nothing binding",
};

function Row({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div
      className="flex items-baseline justify-between gap-6 border-t py-2.5 first:border-t-0"
      style={{ borderColor: "var(--border-hairline)" }}
    >
      <span className="text-[13px]" style={{ color: "var(--text-secondary)" }}>
        {label}
      </span>
      <span
        className="tnum text-[13.5px] font-medium"
        style={{ color: muted ? "var(--text-muted)" : "var(--text-primary)" }}
      >
        {value}
      </span>
    </div>
  );
}

export function PredictionHero({
  prediction,
  feasibility,
  goalTimeS,
  goalDate,
  mode,
}: {
  prediction: Prediction;
  feasibility: Feasibility;
  goalTimeS: number | null;
  goalDate: string | null;
  mode: Mode;
}) {
  const c = CHART[mode];
  const verdict = VERDICT[feasibility.verdict] ?? VERDICT.tight;
  const toneColor = c[verdict.tone];
  const Icon =
    verdict.tone === "good" ? CheckCircle : verdict.tone === "warning" ? Warning : WarningOctagon;

  const delta = goalTimeS ? prediction.predicted_time_s - goalTimeS : null;

  return (
    <div className="grid gap-10 lg:grid-cols-[1.35fr_1fr] lg:gap-14">
      {/* Left: the headline number. Deliberately left-aligned — a centred hero
          would flatten the hierarchy between this and the breakdown beside it. */}
      <div className="min-w-0">
        <div className="flex items-center gap-2.5">
          <LiveDot color={toneColor} />
          <span
            className="text-[12px] font-medium tracking-wide uppercase"
            style={{ color: "var(--text-muted)" }}
          >
            Projected half marathon
          </span>
        </div>

        <motion.p
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 90, damping: 18, delay: 0.05 }}
          className="tnum mt-4 text-[clamp(3rem,9vw,5.25rem)] leading-[0.92] font-semibold tracking-tighter"
          style={{ color: "var(--text-primary)" }}
        >
          {prediction.predicted_time_display ?? hms(prediction.predicted_time_s)}
        </motion.p>

        <p className="mt-3 text-[14px]" style={{ color: "var(--text-secondary)" }}>
          <span className="tnum">{pace(prediction.predicted_pace_s_per_km)}</span> /km
          {delta !== null && (
            <>
              {" · "}
              <span className="tnum" style={{ color: delta > 0 ? toneColor : c.good }}>
                {delta > 0 ? "+" : "−"}
                {hms(Math.abs(delta))}
              </span>{" "}
              vs goal
            </>
          )}
        </p>

        <div className="mt-6 flex flex-wrap items-center gap-2.5">
          <span
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12.5px] font-medium"
            style={{ background: `${toneColor}1a`, color: toneColor }}
          >
            <Icon size={14} weight="fill" />
            {verdict.label}
          </span>
          <span
            className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12.5px]"
            style={{ borderColor: "var(--border-hairline)", color: "var(--text-secondary)" }}
          >
            Limiter: {LIMITER_COPY[feasibility.limiting_factor] ?? feasibility.limiting_factor}
          </span>
          {goalDate && (
            <span
              className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12.5px]"
              style={{ borderColor: "var(--border-hairline)", color: "var(--text-secondary)" }}
            >
              Race {mediumDate(goalDate)}
            </span>
          )}
        </div>
      </div>

      {/* Right: how the number was reached. Auditability is the whole premise —
          the projection is never presented without its derivation. */}
      <div className="min-w-0">
        <p
          className="mb-3 text-[12px] font-medium tracking-wide uppercase"
          style={{ color: "var(--text-muted)" }}
        >
          How this was derived
        </p>
        <Row
          label={`Reference · ${prediction.reference_effort_type}`}
          value={prediction.reference_duration_display ?? hms(prediction.reference_duration_s)}
        />
        <Row label="Riegel" value={hms(prediction.riegel_s)} />
        <Row label="Cameron" value={hms(prediction.cameron_s)} />
        <Row label="Blended" value={hms(prediction.blended_s)} />
        <Row
          label="Durability penalty"
          value={`+${prediction.durability_penalty_pct.toFixed(2)}%`}
        />
        <Row
          label="Long run ÷ race"
          value={prediction.durability_ratio.toFixed(3)}
          muted
        />

        {prediction.notes.length > 0 && (
          <div
            className="mt-4 flex gap-2.5 rounded-xl p-3.5"
            style={{ background: "var(--accent-soft)" }}
          >
            <Info
              size={15}
              weight="fill"
              style={{ color: "var(--accent)" }}
              className="mt-[2px] shrink-0"
            />
            <ul className="flex flex-col gap-1.5">
              {prediction.notes.map((n) => (
                <li
                  key={n}
                  className="text-[12.5px] leading-relaxed"
                  style={{ color: "var(--text-secondary)" }}
                >
                  {n}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
