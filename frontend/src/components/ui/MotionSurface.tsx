"use client";
import { motion, useReducedMotion } from "framer-motion";
export const uiEase = [0.23, 1, 0.32, 1] as const;
export function MotionSurface({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, transform: reduced ? "none" : "translateY(6px)" }}
      animate={{ opacity: 1, transform: reduced ? "none" : "translateY(0px)" }}
      transition={{ duration: 0.16, ease: uiEase }}
    >
      {children}
    </motion.div>
  );
}
