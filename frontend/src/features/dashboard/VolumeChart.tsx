import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { TooltipShell } from "../../components/ChartTooltip";
import { shortDate } from "../../lib/format";
import type { Mode } from "../../lib/theme";
import { CHART } from "../../lib/theme";
import type { Week } from "../../api/types";

export function VolumeChart({ weeks, mode }: { weeks: Week[]; mode: Mode }) {
  const c = CHART[mode];
  const peak = Math.max(...weeks.map((w) => w.km));

  const data = weeks.map((w) => ({
    label: shortDate(w.start),
    km: Number(w.km.toFixed(1)),
    runDays: w.run_days,
    start: w.start,
    end: w.end,
  }));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 18, right: 4, bottom: 0, left: -18 }} barCategoryGap="26%">
        <CartesianGrid stroke={c.grid} strokeDasharray="0" vertical={false} strokeOpacity={0.7} />
        <XAxis
          dataKey="label"
          tick={{ fill: c.text, fontSize: 11.5 }}
          axisLine={{ stroke: c.grid }}
          tickLine={false}
          tickMargin={10}
        />
        <YAxis
          tick={{ fill: c.text, fontSize: 11.5 }}
          axisLine={false}
          tickLine={false}
          width={46}
          tickMargin={6}
        />
        <Tooltip
          cursor={{ fill: c.grid, fillOpacity: 0.35 }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as (typeof data)[number];
            return (
              <TooltipShell
                title={`${shortDate(d.start)} – ${shortDate(d.end)}`}
                rows={[
                  { label: "Distance", value: `${d.km.toFixed(1)} km`, color: c.series1 },
                  { label: "Run days", value: String(d.runDays) },
                ]}
              />
            );
          }}
        />
        {/* 4px rounded top corners, anchored flat to the baseline. */}
        <Bar dataKey="km" radius={[4, 4, 0, 0]} isAnimationActive>
          {data.map((d) => (
            <Cell
              key={d.start}
              fill={c.series1}
              // The peak week reads as the reference point; the rest recede
              // slightly. Same hue — this is emphasis, not a second category.
              fillOpacity={d.km === peak ? 1 : 0.5}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
