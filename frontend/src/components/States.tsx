import { ArrowClockwise, PlugsConnected, WifiSlash } from "@phosphor-icons/react";
import type { ReactNode } from "react";

function Frame({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-[220px] place-items-center px-6 py-10 text-center">
      <div className="max-w-[42ch]">{children}</div>
    </div>
  );
}

export function ErrorState({
  detail,
  status,
  onRetry,
}: {
  detail: string;
  status: number | null;
  onRetry: () => void;
}) {
  // 404 from this API means "not connected yet", which is a setup step rather
  // than a fault — say so instead of showing a scary failure.
  const notConnected = status === 404 && /athlete/i.test(detail);
  const Icon = notConnected ? PlugsConnected : WifiSlash;

  return (
    <Frame>
      <Icon size={26} weight="duotone" style={{ color: "var(--text-muted)" }} className="mx-auto" />
      <p className="mt-4 text-[15px] font-medium" style={{ color: "var(--text-primary)" }}>
        {notConnected ? "No Strava account connected" : "Could not load this"}
      </p>
      <p className="mt-1.5 text-[13px] leading-relaxed" style={{ color: "var(--text-secondary)" }}>
        {detail}
      </p>

      {notConnected ? (
        <a
          href="/api/auth/strava/authorize"
          className="mt-5 inline-flex items-center gap-2 rounded-full px-4 py-2 text-[13px] font-medium text-white transition-transform duration-200 active:scale-[0.98]"
          style={{ background: "var(--accent)" }}
        >
          Connect Strava
        </a>
      ) : (
        <button
          type="button"
          onClick={onRetry}
          className="mt-5 inline-flex items-center gap-2 rounded-full border px-4 py-2 text-[13px] font-medium transition-transform duration-200 active:scale-[0.98]"
          style={{ borderColor: "var(--border-strong)", color: "var(--text-primary)" }}
        >
          <ArrowClockwise size={15} weight="bold" />
          Try again
        </button>
      )}
    </Frame>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <Frame>
      <div
        className="mx-auto h-px w-16"
        style={{ background: "var(--border-strong)" }}
        aria-hidden="true"
      />
      <p className="mt-5 text-[15px] font-medium" style={{ color: "var(--text-primary)" }}>
        {title}
      </p>
      <p className="mt-1.5 text-[13px] leading-relaxed" style={{ color: "var(--text-secondary)" }}>
        {body}
      </p>
    </Frame>
  );
}
