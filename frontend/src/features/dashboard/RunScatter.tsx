import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import { TooltipShell } from "../../components/ChartTooltip";
import { km, mediumDate, pace, shortDate } from "../../lib/format";
import type { Mode } from "../../lib/theme";
import { CHART } from "../../lib/theme";
import type { Activity } from "../../api/types";

/** Every run, by date and distance.
 *  Chosen over another volume bar chart because it shows the two things that
 *  actually decide this goal at once: how the long run is progressing, and
 *  where the training stopped. Gaps are visible as empty vertical bands. */
export function RunScatter({ runs, mode }: { runs: Activity[]; mode: Mode }) {
  const c = CHART[mode];
  const data = runs.map((r) => ({
    t: new Date(r.start_local).getTime(),
    km: Number((r.distance_m / 1000).toFixed(2)),
    paceS: r.moving_time_s / (r.distance_m / 1000),
    name: r.name,
    date: r.start_local,
  }));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={{ top: 18, right: 10, bottom: 0, left: -18 }}>
        <CartesianGrid stroke={c.grid} vertical={false} strokeOpacity={0.7} />
        <XAxis
          dataKey="t"
          type="number"
          domain={["dataMin", "dataMax"]}
          tickFormatter={(v: number) => shortDate(new Date(v).toISOString())}
          tick={{ fill: c.text, fontSize: 11.5 }}
          axisLine={{ stroke: c.grid }}
          tickLine={false}
          tickMargin={10}
          minTickGap={46}
        />
        <YAxis
          dataKey="km"
          tick={{ fill: c.text, fontSize: 11.5 }}
          axisLine={false}
          tickLine={false}
          width={46}
          tickMargin={6}
          unit=""
        />
        <ZAxis range={[52, 52]} />
        <Tooltip
          cursor={{ stroke: c.axis, strokeWidth: 1, strokeDasharray: "3 3" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as (typeof data)[number];
            return (
              <TooltipShell
                title={mediumDate(d.date)}
                rows={[
                  { label: "Distance", value: `${km(d.km * 1000)} km`, color: c.series1 },
                  { label: "Pace", value: `${pace(d.paceS)} /km` },
                ]}
              />
            );
          }}
        />
        <Scatter
          data={data}
          fill={c.series1}
          fillOpacity={0.85}
          stroke={c.surface}
          strokeWidth={2}
          isAnimationActive
        />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
