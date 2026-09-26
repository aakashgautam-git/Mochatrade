# Progress log

Three lines per phase: done / deviations / issues.

## Circuit-breaker bounds fix
- Done: DCB bounds anchored to the opposite extreme; look-back restarts on resume; fires in 5/6 scenarios; controls-on still beats off everywhere; reopen wick 413 -> 223 bps.
- Deviations: none. FRAME_SCHEMA bumped to 6 so cached runs re-warm.
- Issues: none.
