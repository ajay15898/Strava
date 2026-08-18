import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { TooltipShell } from "../../components/ChartTooltip";
import { distanceLabel, hms, mediumDate, pace } from "../../lib/format";
import type { Mode } from "../../lib/theme";
import { CHART } from "../../lib/theme";
import type { PacePoint } from "../../api/types";

/** Best effort at each distance, from Strava's own best_effort records.
 *  Pace rises with distance, so the line climbing left-to-right is the athlete
 *  slowing down as the distance grows — exactly the fade a race prediction
 *  extrapolates. */
export function PaceCurve({ points, mode }: { points: PacePoint[]; mode: Mode }) {
  const c = CHART[mode];
  const data = points.map((p) => ({
    ...p,
    x: p.distance_m,
    paceMin: p.pace_s_per_km / 60,
  }));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 18, right: 12, bottom: 0, left: -14 }}>
        <CartesianGrid stroke={c.grid} vertical={false} strokeOpacity={0.7} />
        <XAxis
          dataKey="x"
          type="number"
          scale="log"
          domain={["dataMin", "dataMax"]}
          ticks={data.map((d) => d.x)}
          tickFormatter={(v: number) => distanceLabel(v)}
          tick={{ fill: c.text, fontSize: 11.5 }}
          axisLine={{ stroke: c.grid }}
          tickLine={false}
          tickMargin={10}
        />
        <YAxis
          dataKey="paceMin"
          tickFormatter={(v: number) => pace(v * 60)}
          tick={{ fill: c.text, fontSize: 11.5 }}
          axisLine={false}
          tickLine={false}
          width={50}
          tickMargin={6}
          domain={["dataMin - 0.4", "dataMax + 0.4"]}
        />
        <Tooltip
          cursor={{ stroke: c.axis, strokeWidth: 1, strokeDasharray: "3 3" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as (typeof data)[number];
            return (
              <TooltipShell
                title={`${d.effort_type} · ${mediumDate(d.activity_date)}`}
                rows={[
                  { label: "Time", value: hms(d.duration_s), color: c.series1 },
                  { label: "Pace", value: `${pace(d.pace_s_per_km)} /km` },
                ]}
              />
            );
          }}
        />
        <Line
          type="monotone"
          dataKey="paceMin"
          stroke={c.series1}
          strokeWidth={2}
          // Markers are the point here — each is a real recorded effort, so they
          // get a surface ring to stay legible where the line passes behind them.
          dot={{ r: 4.5, fill: c.series1, stroke: c.surface, strokeWidth: 2 }}
          activeDot={{ r: 6, fill: c.series1, stroke: c.surface, strokeWidth: 2 }}
          isAnimationActive
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
