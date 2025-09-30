I want to spend some time on designing a smart algorithm to estimate time spent on an exercise. On the HTML pages, there should be a way to see if the student is facing the page. There should be a way to see if the student is actively using the page or if they are just leaving it idle for a long time (e.g. they went to get a snack and didn't come back). Let's first think conceptually: What is the best way to estimate the time spent on a question? Knowing that we have the traces, each with a timestamp, and we are on the client, on the front-end. We are on a browser. We can see if the page is in focus, we can see if the mouse is moving, we can see if the student is typing. Things like that. So think conceptually and devise me a good approximation of the time spent on a question.

### Concept: “Active learning time” via hybrid client signals + trace anchoring

- **Definition**
  - Count time as “active” when the exercise page is both (a) foregrounded and (b) the student shows recent interaction or plausible reading behavior.
  - Use a simple state machine with decay windows, plus “anchor” windows around important trace events (messages, runs).

### Signals to use (client-side)
- **Visibility/focus**: `document.visibilityState`, `window focus/blur`.
- **Interaction**: `keydown`, `pointer/mouse/touch move`, `click`, `wheel`, `scroll`, `selectionchange`.
- **Editor activity**: cursor moves, selection changes, content edits, run/submit clicks.
- **Network actions**: “Run code”, “Execute SQL”, “Send message to tutor”, “Receive tutor reply”.
- **Multi-tab guard**: BroadcastChannel/localStorage lock to ensure only one tab for an attempt accumulates time.
- Optional: **Copy/paste**, **Resize**, **Audio** (if ever used).

### State model (lightweight and robust)
- **States**
  - Interacting: Recent explicit input (typing, click, editor change). Full credit.
  - Reading: Foreground + no explicit input, but still likely engaged (recent scroll/mouse micro-movement or fresh content to read). Reduced but still full credit, or configurable (e.g., 1.0x).
  - Idle: No signals long enough or tab is hidden/unfocused. No credit.
- **Transitions (with decay/grace windows)**
  - On input event: Interacting for G_interact seconds (e.g., 15s) since last event.
  - If no input but page focused + recent light activity (scroll/move) or new content: Reading for up to G_read seconds (e.g., 90s) after last signal.
  - If page blurred/hidden: transition to Idle after a short grace (e.g., 5–10s).
  - Hard idle cutoff: if nothing for T_idle_max (e.g., 5 min), force Idle.

### Trace-anchored windows
- Around key events in traces:
  - Student message sent: add [−10s, +40s] window.
  - Tutor reply received: add [+10s per 500 chars, capped at 90s] reading window.
  - Code/SQL execution: add [−5s, +20s] exploration window.
- Merge these “anchor” intervals with client activity intervals; only count intervals that also satisfy foreground/focus.

### Time aggregation logic
- Maintain a rolling “lastSignalAt” and “lastLightSignalAt”.
- Every second (or at event edges), compute an **activity score**:
  - 1.0 if within G_interact of an input event and page focused/visible.
  - 1.0 if within G_read of light activity or within a trace-anchored window and page focused/visible.
  - 0 otherwise.
- **Active time** = measure of the union of seconds where score ≥ 1.0. Prefer interval merging to per-second ticks to save battery.

### Multi-tab and navigation
- Use a BroadcastChannel “attempt-activity-<attemptId>” to elect a single “active tab”. Others pause accumulation.
- On navigation within the same attempt, carry the lock; on window unload, release with `sendBeacon`.

### Reporting/storage strategy
- Client builds compact intervals: `[start_ms, end_ms, reason_flags]`.
- Flush diffs every 15–30s or on blur/unload via `sendBeacon`.
- Server stores intervals under the `Attempt` (new table or JSON column) and can recompute aggregates; keep raw intervals for audits.

### Defaults (tunable)
- G_interact: 15s
- G_read: 90s
- Blur/hidden grace: 10s
- Hard idle cutoff: 5 min
- Trace anchor windows:
  - Student->Tutor: [−10s, +40s]
  - Tutor reply: +10–90s based on length
  - Code/SQL run: [−5s, +20s]
- Only count when `visibilityState === 'visible'` AND window is focused AND this tab is “active”.

### Edge cases and safeguards
- Sleep/wake or clock jumps: cap single gap additions to 2 min unless anchored by traces.
- Mobile touch: include `touchstart/move` as input; treat kinetic scrolling as reading.
- Prevent false positives from background animation: require visibility+focus and recent event.
- Long passive reading: allowed up to G_read; beyond that, require a new light signal to extend.
- Off-page research: page unfocused → do not count.

### Quality checks and tuning
- Compare estimated active time vs attempt start-to-submit duration; monitor ratio distributions.
- Correlate with number of edits/runs/messages; outliers suggest threshold tuning.
- Provide UI diagnostics (teacher view): “Active time”, “Focus ratio”, “Anchored time” (from traces), “Idle”.

### Why this works
- Event-driven decay windows are efficient and robust in browsers.
- Foreground gating prevents counting off-tab time.
- Trace anchors capture meaningful, low-frequency but high-signal moments (reading AI replies, running code).
- Interval union avoids double counting and remains explainable.

If you want, I can draft the minimal frontend scaffold (activity tracker with intervals and anchors) and the backend shape to persist and display these metrics.