import { MoonStars, Sun } from "@phosphor-icons/react";

import { MagneticButton } from "./components/MagneticButton";
import { Dashboard } from "./features/dashboard/Dashboard";
import { useTheme } from "./lib/theme";

export default function App() {
  const { mode, toggle } = useTheme();

  return (
    <div className="min-h-[100dvh]">
      <header
        className="sticky top-0 z-30 border-b backdrop-blur-xl"
        style={{
          borderColor: "var(--border-hairline)",
          background: "color-mix(in srgb, var(--surface-page) 82%, transparent)",
        }}
      >
        <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-6 px-4 py-4 sm:px-8">
          <div className="flex items-baseline gap-3">
            <span
              className="text-[17px] font-semibold tracking-tight"
              style={{ color: "var(--text-primary)" }}
            >
              Pace
            </span>
            <span
              className="hidden text-[13px] sm:inline"
              style={{ color: "var(--text-muted)" }}
            >
              Half marathon under 2:00:00
            </span>
          </div>

          <MagneticButton
            onClick={toggle}
            label={mode === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          >
            {mode === "dark" ? (
              <Sun size={16} weight="bold" />
            ) : (
              <MoonStars size={16} weight="bold" />
            )}
          </MagneticButton>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-4 py-8 sm:px-8 sm:py-10">
        <Dashboard mode={mode} />
      </main>
    </div>
  );
}
