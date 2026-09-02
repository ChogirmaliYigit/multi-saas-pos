"use client";

import { motion } from "framer-motion";
import { usePathname } from "next/navigation";

/**
 * A short, small movement. Anything longer than ~200ms or further than a few
 * pixels starts to feel like latency rather than polish -- especially on a
 * till, where staff navigate the same screens hundreds of times a day.
 */
export function PageTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <motion.div
      key={pathname}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className="flex-1"
    >
      {children}
    </motion.div>
  );
}
