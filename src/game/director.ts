import { useEffect, useRef } from 'react';
import { useMotionValue, type MotionValue } from 'motion/react';

/** One clock owns a complete scene. StrictMode, replay and unmount all cancel it. */
export function useTimeline(durationMs: number, onComplete?: () => void): MotionValue<number> {
  const elapsed = useMotionValue(0);
  const completion = useRef(onComplete);
  completion.current = onComplete;

  useEffect(() => {
    let frame = 0;
    let start: number | undefined;
    let cancelled = false;
    let completed = false;
    elapsed.set(0);
    const tick = (now: number) => {
      if (cancelled) return;
      start ??= now;
      const next = Math.min(now - start, durationMs);
      elapsed.set(next);
      if (next >= durationMs) {
        if (!completed) {
          completed = true;
          completion.current?.();
        }
      } else frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => { cancelled = true; cancelAnimationFrame(frame); };
  }, [durationMs, elapsed]);

  return elapsed;
}
