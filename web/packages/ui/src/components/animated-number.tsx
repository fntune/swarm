"use client";

import { motion, useReducedMotion, useSpring, useTransform } from "motion/react";
import * as React from "react";

/**
 * Smooth value transitions for live-updating metrics. Renders statically when
 * the user prefers reduced motion.
 */
export function AnimatedNumber({
  value,
  format = (current: number) => current.toLocaleString(),
  className,
}: {
  value: number;
  format?: (current: number) => string;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();
  const spring = useSpring(value, { stiffness: 120, damping: 24 });
  const text = useTransform(spring, (current) => format(current));

  React.useEffect(() => {
    spring.set(value);
  }, [spring, value]);

  if (reduceMotion) {
    return <span className={className}>{format(value)}</span>;
  }
  return <motion.span className={className}>{text}</motion.span>;
}
