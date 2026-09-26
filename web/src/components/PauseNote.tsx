/**
 * One plain line wherever trading pauses are drawn. The pauses are the velocity
 * guard and the circuit breaker doing their job; how the velocity guard is
 * calibrated against the liquidation throttle is an open item, recorded in
 * ARCHITECTURE.md and KNOWN_ISSUES.md.
 */
export function PauseNote() {
  return (
    <p className="text-xs leading-relaxed text-text-dim">
      Pauses on the strip are the velocity guard and circuit breaker protecting users. How the
      velocity guard is calibrated against the liquidation throttle is a documented open item.
    </p>
  );
}
