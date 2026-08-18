import { useEffect, useState } from "react";

export type Mode = "light" | "dark";

/** Chart marks need real hex, not CSS vars — Recharts writes SVG attributes.
 *  These are the exact values validated by the dataviz palette checker against
 *  each surface (#ffffff light, #18181b dark): all six checks pass in both. */
export const CHART = {
  light: {
    series1: "#2a78d6",
    series2: "#eb6834",
    grid: "#e4e4e7",
    axis: "#a1a1aa",
    text: "#52525b",
    surface: "#ffffff",
    good: "#1baf7a",
    warning: "#eda100",
    critical: "#e34948",
  },
  dark: {
    series1: "#3987e5",
    series2: "#d95926",
    grid: "#3f3f46",
    axis: "#71717a",
    text: "#a1a1aa",
    surface: "#18181b",
    good: "#199e70",
    warning: "#c98500",
    critical: "#e66767",
  },
} as const;

const STORAGE_KEY = "pace-theme";

function resolve(): Mode {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useTheme() {
  const [mode, setMode] = useState<Mode>(() => resolve());

  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    localStorage.setItem(STORAGE_KEY, mode);
  }, [mode]);

  useEffect(() => {
    // Follow the OS only while the user has expressed no preference.
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (!localStorage.getItem(STORAGE_KEY)) setMode(mq.matches ? "dark" : "light");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return {
    mode,
    palette: CHART[mode],
    toggle: () => setMode((m) => (m === "light" ? "dark" : "light")),
  };
}
