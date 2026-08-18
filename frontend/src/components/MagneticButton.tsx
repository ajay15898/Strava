import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import type { ReactNode } from "react";
import { useRef } from "react";

/** A button that leans toward the cursor.
 *  Pointer position lives in motion values, never in React state — putting it
 *  in state would re-render this subtree on every mousemove and collapse
 *  frame rate on lower-powered devices. */
export function MagneticButton({
  children,
  onClick,
  label,
  strength = 0.28,
}: {
  children: ReactNode;
  onClick?: () => void;
  label: string;
  strength?: number;
}) {
  const ref = useRef<HTMLButtonElement>(null);

  const mx = useMotionValue(0);
  const my = useMotionValue(0);

  const spring = { stiffness: 220, damping: 18, mass: 0.4 };
  const x = useSpring(useTransform(mx, (v) => v * strength), spring);
  const y = useSpring(useTransform(my, (v) => v * strength), spring);

  return (
    <motion.button
      ref={ref}
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      style={{ x, y, borderColor: "var(--border-hairline)", color: "var(--text-secondary)" }}
      onPointerMove={(e) => {
        const el = ref.current;
        if (!el) return;
        const r = el.getBoundingClientRect();
        mx.set(e.clientX - (r.left + r.width / 2));
        my.set(e.clientY - (r.top + r.height / 2));
      }}
      onPointerLeave={() => {
        mx.set(0);
        my.set(0);
      }}
      whileTap={{ scale: 0.94 }}
      className="grid h-9 w-9 place-items-center rounded-full border transition-colors duration-200"
    >
      {children}
    </motion.button>
  );
}
