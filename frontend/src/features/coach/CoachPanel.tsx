import { motion } from "framer-motion";
import { ArrowUp, PaperPlaneTilt, SealCheck, ShieldWarning } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";

import { ApiError, api } from "../../api/client";
import { Panel, PanelHeading } from "../../components/Panel";
import { Skeleton } from "../../components/Skeleton";
import type { Mode } from "../../lib/theme";
import { CHART } from "../../lib/theme";
import { useApi } from "../../lib/useApi";
import type { CoachMessage } from "../../api/types";

const PROMPTS = [
  "How am I tracking against the goal?",
  "What should I focus on this week?",
  "Is my long run progressing fast enough?",
];

/** Verification state, shown rather than hidden.
 *  The guard is the reason a free-tier model is acceptable here, so whether it
 *  passed is information the athlete is entitled to see. */
function VerifyBadge({
  verified,
  fallback,
  mode,
}: {
  verified: boolean;
  fallback: boolean;
  mode: Mode;
}) {
  const c = CHART[mode];
  const tone = fallback ? c.warning : c.good;
  const Icon = fallback ? ShieldWarning : SealCheck;
  const label = fallback ? "Engine summary — model failed the numeric check" : "Numbers verified";

  if (!verified && !fallback) return null;

  return (
    <span
      className="mt-2 inline-flex items-center gap-1.5 text-[11.5px] font-medium"
      style={{ color: tone }}
    >
      <Icon size={13} weight="fill" />
      {label}
    </span>
  );
}

export function CoachPanel({ mode }: { mode: Mode }) {
  const c = CHART[mode];
  const history = useApi(() => api.coachHistory(), []);

  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unconfigured, setUnconfigured] = useState(false);
  const [local, setLocal] = useState<CoachMessage[]>([]);
  const [meta, setMeta] = useState<Record<number, { verified: boolean; fallback: boolean }>>({});
  const endRef = useRef<HTMLDivElement>(null);

  const messages = [...(history.data ?? []), ...local];

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages.length, pending]);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || pending) return;

    setDraft("");
    setPending(question);
    setError(null);

    try {
      const reply = await api.askCoach(question);
      const now = new Date().toISOString();
      const userMsg: CoachMessage = { id: -Date.now(), role: "user", content: question, created_at: now };
      const botMsg: CoachMessage = { id: -Date.now() - 1, role: "assistant", content: reply.content, created_at: now };
      setLocal((m) => [...m, userMsg, botMsg]);
      setMeta((m) => ({ ...m, [botMsg.id]: { verified: reply.verified, fallback: reply.used_fallback } }));
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) setUnconfigured(true);
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setPending(null);
    }
  };

  return (
    <Panel>
      <PanelHeading
        title="Coach"
        hint="Reads a pre-computed context and explains it. Every number it prints is checked against that context before you see it."
      />

      {unconfigured ? (
        <div className="rounded-xl p-4" style={{ background: "var(--accent-soft)" }}>
          <p className="text-[13px] font-medium" style={{ color: "var(--text-primary)" }}>
            No model provider configured
          </p>
          <p className="mt-1.5 text-[12.5px] leading-relaxed" style={{ color: "var(--text-secondary)" }}>
            Get a free key at{" "}
            <a
              href="https://console.groq.com/keys"
              target="_blank"
              rel="noreferrer"
              style={{ color: "var(--accent)" }}
            >
              console.groq.com/keys
            </a>{" "}
            (no card), put it in <code>.env</code> as <code>COACH_API_KEY</code>, and restart the
            backend.
          </p>
        </div>
      ) : null}

      {history.loading ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-14 w-3/4" radius="1rem" />
          <Skeleton className="ml-auto h-10 w-1/2" radius="1rem" />
        </div>
      ) : messages.length === 0 && !pending ? (
        <div className="flex flex-wrap gap-2">
          {PROMPTS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => send(p)}
              className="rounded-full border px-3.5 py-2 text-[12.5px] transition-transform duration-200 active:scale-[0.98]"
              style={{ borderColor: "var(--border-hairline)", color: "var(--text-secondary)" }}
            >
              {p}
            </button>
          ))}
        </div>
      ) : (
        <ul className="flex max-h-[440px] flex-col gap-4 overflow-y-auto pr-1">
          {messages.map((m) => (
            <motion.li
              key={m.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ type: "spring", stiffness: 120, damping: 20 }}
              className={m.role === "user" ? "self-end" : "self-start"}
              style={{ maxWidth: "88%" }}
            >
              <div
                className="rounded-2xl px-4 py-3 text-[13.5px] leading-relaxed whitespace-pre-wrap"
                style={
                  m.role === "user"
                    ? { background: "var(--accent)", color: "#fff" }
                    : { background: "var(--surface-sunken)", color: "var(--text-primary)" }
                }
              >
                {m.content}
              </div>
              {m.role === "assistant" && meta[m.id] && (
                <VerifyBadge
                  verified={meta[m.id].verified}
                  fallback={meta[m.id].fallback}
                  mode={mode}
                />
              )}
            </motion.li>
          ))}

          {pending && (
            <>
              <li className="self-end" style={{ maxWidth: "88%" }}>
                <div
                  className="rounded-2xl px-4 py-3 text-[13.5px]"
                  style={{ background: "var(--accent)", color: "#fff", opacity: 0.75 }}
                >
                  {pending}
                </div>
              </li>
              <li className="self-start">
                <Skeleton className="h-12 w-56" radius="1rem" />
              </li>
            </>
          )}
          <div ref={endRef} />
        </ul>
      )}

      {error && !unconfigured && (
        <p className="mt-3 text-[12.5px]" style={{ color: c.critical }}>
          {error}
        </p>
      )}

      <form
        className="mt-5 flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send(draft);
        }}
      >
        <label className="sr-only" htmlFor="coach-input">
          Ask the coach
        </label>
        <input
          id="coach-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask about your training…"
          disabled={!!pending}
          className="flex-1 rounded-full border px-4 py-2.5 text-[13.5px] outline-none transition-colors"
          style={{
            background: "var(--surface-card)",
            borderColor: "var(--border-hairline)",
            color: "var(--text-primary)",
          }}
        />
        <button
          type="submit"
          disabled={!draft.trim() || !!pending}
          aria-label="Send"
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-white transition-transform duration-200 active:scale-90 disabled:opacity-40"
          style={{ background: "var(--accent)" }}
        >
          {pending ? <PaperPlaneTilt size={16} weight="fill" /> : <ArrowUp size={17} weight="bold" />}
        </button>
      </form>
    </Panel>
  );
}
