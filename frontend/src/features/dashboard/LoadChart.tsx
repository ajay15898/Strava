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
import { shortDate } from "../../lib/format";
import type { Mode } from "../../lib/theme";
import { CHART } from "../../lib/theme";
import type { LoadDay } from "../../api/types";

/** Direct label pinned to the final point of a series.
 *  Recharts types `label` against its own loose props (x/y may be strings), so
 *  the render function coerces and the call site carries one narrow cast. */
function endLabel(color: string, text: string, lastIndex: number) {
  return ((props: { index?: number; x?: number | string; y?: number | string }) => {
    if (props.index !== lastIndex) return <g />;
    return (
      <text
        x={Number(props.x ?? 0) + 9}
        y={Number(props.y ?? 0) + 4}
        fill={color}
        fontSize={11.5}
        fontWeight={600}
      >
        {text}
      </text>
    );
  }) as never;
}

/** Fitness (CTL) against fatigue (ATL).
 *  Both are in the same load units, so they share one axis — a second y-scale
 *  here would let the curves cross wherever the scaling happened to put them,
 *  which is the most misleading thing a chart can do. */
export function LoadChart({ days, mode }: { days: LoadDay[]; mode: Mode }) {
  const c = CHART[mode];
  const data = days.map((d) => ({ ...d, label: shortDate(d.date) }));
  const lastIndex = data.length - 1;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 18, right: 54, bottom: 0, left: -18 }}>
        <CartesianGrid stroke={c.grid} vertical={false} strokeOpacity={0.7} />
        <XAxis
          dataKey="label"
          tick={{ fill: c.text, fontSize: 11.5 }}
          axisLine={{ stroke: c.grid }}
          tickLine={false}
          tickMargin={10}
          minTickGap={44}
        />
        <YAxis
          tick={{ fill: c.text, fontSize: 11.5 }}
          axisLine={false}
          tickLine={false}
          width={46}
          tickMargin={6}
        />
        <Tooltip
          cursor={{ stroke: c.axis, strokeWidth: 1, strokeDasharray: "3 3" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as (typeof data)[number];
            return (
              <TooltipShell
                title={new Date(d.date).toLocaleDateString(undefined, {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
                rows={[
                  { label: "Fitness (CTL)", value: d.ctl.toFixed(1), color: c.series1 },
                  { label: "Fatigue (ATL)", value: d.atl.toFixed(1), color: c.series2 },
                  { label: "Form (TSB)", value: d.tsb.toFixed(1) },
                ]}
              />
            );
          }}
        />
        {/* Direct-labelled at the line ends, so identity never rests on hue alone. */}
        <Line
          type="monotone"
          dataKey="ctl"
          stroke={c.series1}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4.5, strokeWidth: 2, stroke: c.surface }}
          label={endLabel(c.series1, "CTL", lastIndex)}
          isAnimationActive
        />
        <Line
          type="monotone"
          dataKey="atl"
          stroke={c.series2}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4.5, strokeWidth: 2, stroke: c.surface }}
          label={endLabel(c.series2, "ATL", lastIndex)}
          isAnimationActive
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
