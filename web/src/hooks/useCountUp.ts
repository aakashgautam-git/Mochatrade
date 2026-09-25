import { useEffect, useRef, useState } from "react";

/**
 * Count duration. Deliberately longer than the 150-200ms motion rule: a count
 * that finishes in 200ms reads as a flicker rather than as counting, and the
 * design rule is that numbers transition by counting. Everything else stays
 * inside 150-200ms.
 */
export const COUNT_MS = 400;

const easeOut = (t: number) => 1 - (1 - t) ** 3;

function reducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true
  );
}

/**
 * Animate a number toward `target` by counting. Interrupting mid-count starts
 * from wherever the count had reached, so rapid updates never jump backwards.
 * Under reduced motion the value is set immediately.
 *
 * Returns the value to display and the value the current count started from,
 * which the Stat uses to reserve width so the count cannot shift layout.
 */
export function useCountUp(
  target: number,
  { duration = COUNT_MS, startFrom }: { duration?: number; startFrom?: number } = {},
): { value: number; from: number } {
  const initial = startFrom ?? target;
  const [value, setValue] = useState(initial);
  const current = useRef(initial);
  const from = useRef(initial);

  useEffect(() => {
    if (reducedMotion() || duration <= 0) {
      current.current = target;
      from.current = target;
      setValue(target);
      return;
    }
    const start = current.current;
    from.current = start;
    if (start === target) return;

    let frame = 0;
    const began = performance.now();
    const step = (now: number) => {
      // Clamp both ends. The rAF timestamp is the start of the frame, which can
      // precede the performance.now() taken when the count began; an unclamped
      // negative t makes the cubic ease negative and the number briefly jumps
      // backwards (a count from 0 to 253 showed "-21" for one frame).
      const t = Math.min(1, Math.max(0, (now - began) / duration));
      const next = start + (target - start) * easeOut(t);
      current.current = next;
      setValue(next);
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);

  return { value, from: from.current };
}
