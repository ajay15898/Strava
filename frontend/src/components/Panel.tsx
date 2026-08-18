import { motion } from "framer-motion";
import type { ReactNode } from "react";

interface PanelProps {
  children: ReactNode;
  className?: string;
  /** Stagger index for the entrance cascade. */
  index?: number;
}

export const panelVariants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 100, damping: 20 } },
};

export function Panel({ children, className = "", index = 0 }: PanelProps) {
  return (
    <motion.section
      variants={panelVariants}
      custom={index}
      className={`rounded-[2rem] border p-7 sm:p-8 ${className}`}
      style={{
        background: "var(--surface-card)",
        borderColor: "var(--border-hairline)",
        boxShadow: "var(--shadow-diffuse)",
      }}
    >
      {children}
    </motion.section>
  );
}

export function PanelHeading({
  title,
  hint,
  aside,
}: {
  title: string;
  hint?: string;
  aside?: ReactNode;
}) {
  return (
    <header className="mb-6 flex items-start justify-between gap-6">
      <div className="min-w-0">
        <h2
          className="text-[15px] font-medium tracking-tight"
          style={{ color: "var(--text-primary)" }}
        >
          {title}
        </h2>
        {hint && (
          <p className="mt-1 text-[13px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
            {hint}
          </p>
        )}
      </div>
      {aside}
    </header>
  );
}
