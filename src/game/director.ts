import { useEffect, useRef } from 'react';
import { useMotionValue, type MotionValue } from 'motion/react';

type TimelineEnvironment = {
  requestFrame: (callback: (now: number) => void) => number;
  cancelFrame: (id: number) => void;
  isHidden: () => boolean;
  subscribeVisibility: (callback: () => void) => () => void;
};

/** The small imperative driver also lets us test pause, resume and cancellation without a browser clock. */
export function startTimeline(durationMs: number, onTick: (elapsed: number) => void, onComplete?: () => void,
  environment: TimelineEnvironment = {
    requestFrame: callback => requestAnimationFrame(callback),
    cancelFrame: id => cancelAnimationFrame(id),
    isHidden: () => document.hidden,
    subscribeVisibility: callback => {
      document.addEventListener('visibilitychange', callback);
      return () => document.removeEventListener('visibilitychange', callback);
    },
  }): () => void {
  let frame = 0;
  let previous: number | undefined;
  let accumulated = 0;
  let cancelled = false;
  let completed = false;
  onTick(0);
  const tick = (now: number) => {
    if (cancelled || completed) return;
    if (environment.isHidden()) { previous = undefined; return; }
    if (previous !== undefined) accumulated += Math.max(0, now - previous);
    previous = now;
    const next = Math.min(accumulated, durationMs);
    onTick(next);
    if (cancelled) return;
    if (next >= durationMs) {
      completed = true;
      onComplete?.();
    } else frame = environment.requestFrame(tick);
  };
  const unsubscribe = environment.subscribeVisibility(() => {
    environment.cancelFrame(frame);
    previous = undefined;
    if (!environment.isHidden() && !cancelled && !completed) frame = environment.requestFrame(tick);
  });
  if (!environment.isHidden()) frame = environment.requestFrame(tick);
  return () => {
    cancelled = true;
    environment.cancelFrame(frame);
    unsubscribe();
  };
}

/** One clock owns a scene. Hidden pages pause playback; unmount cancels both RAF and listeners. */
export function useTimeline(durationMs: number, onComplete?: () => void, enabled = true): MotionValue<number> {
  const elapsed = useMotionValue(0);
  const completion = useRef(onComplete);
  completion.current = onComplete;
  useEffect(() => {
    if (!enabled) return;
    return startTimeline(durationMs, value => elapsed.set(value), () => completion.current?.());
  }, [durationMs, elapsed, enabled]);
  return elapsed;
}
