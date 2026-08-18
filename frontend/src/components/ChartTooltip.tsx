import type { ReactNode } from "react";

export interface TooltipRow {
  label: string;
  value: string;
  color?: string;
}

/** One tooltip shape for every chart, so hover feels identical across the page. */
export function TooltipShell({ title, rows }: { title: string; rows: TooltipRow[] }) {
  return (
    <div
      className="pointer-events-none rounded-xl border px-3 py-2.5 text-[12.5px] shadow-lg"
      style={{
        background: "var(--surface-card)",
        borderColor: "var(--border-strong)",
        color: "var(--text-primary)",
      }}
    >
      <p className="mb-1.5 font-medium tracking-tight" style={{ color: "var(--text-secondary)" }}>
        {title}
      </p>
      <div className="flex flex-col gap-1">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center justify-between gap-5">
            <span className="flex items-center gap-1.5" style={{ color: "var(--text-secondary)" }}>
              {r.color && (
                <span
                  className="inline-block h-2 w-2 shrink-0 rounded-full"
                  style={{ background: r.color }}
                  aria-hidden="true"
                />
              )}
              {r.label}
            </span>
            <span className="tnum font-medium">{r.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Legend chips. Identity is never carried by color alone — every swatch is
 *  paired with its name here, and the lines are direct-labeled as well. */
export function Legend({ items }: { items: { name: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
      {items.map((i) => (
        <span
          key={i.name}
          className="flex items-center gap-1.5 text-[12.5px]"
          style={{ color: "var(--text-secondary)" }}
        >
          <span
            className="inline-block h-[3px] w-4 rounded-full"
            style={{ background: i.color }}
            aria-hidden="true"
          />
          {i.name}
        </span>
      ))}
    </div>
  );
}

export function ChartFrame({ children, height }: { children: ReactNode; height: number }) {
  return (
    <div style={{ height }} className="w-full">
      {children}
    </div>
  );
}
