# Screen-Time Data Guide — what the number is, how reliable, how to use it

This is the producer-side reference for the one number FocusBoard runs on:
`screentime_benchmarks.screentime_seconds`. It answers the Pre-Prototype 1 gating question —
*"is the daily screen time data reliable?"* — from the iOS codebase, so the answer doesn't
rest on assumptions. (Empirical spot-checking against Nate's own iPhone Screen Time still
stands as the final confirmation; this guide covers the *architecture*.)

Source of truth in the iOS app (`opal-apple-monorepo`):
- Producer: `App/Opal/ScreenTimeBenchmarkChoreProvider.swift` (daily `upload-screen-time-benchmark` chore)
- Writer / wire shape: `App/Packages/StatisticsService/Sources/FirebaseScreentimeBenchmarkService/FirebaseScreenTimeBenchmarkUploader.swift`

## What the number is

- **Whole-device total** daily screen time — `AppScreenTimeStore.loadTotalScreenTime(...)`, summed
  across all apps and websites. **Not** tracked-apps-only. *(This resolves the plan's old Open
  Question 2.)*
- In **seconds** (Firestore field `screentime`, a `Double`).
- It's the **fully-completed previous calendar day** in the **user's device timezone** — the chore
  reports `dayInterval(for: yesterday)`. Today is never reported until it closes.

## How accurate

- **~15-minute quantization floor.** Apple's DeviceActivity framework only surfaces usage in ~15-min
  increments, so the daily total carries ~±15 min of noise. Fine for a daily hours-saved metric;
  not a precise per-minute figure.
- It's the **same number the user sees in the Opal app** — so it's checkable against their own stats.

## How often it updates

- The app uploads **yesterday's** total via a **daily chore that runs on app foreground**. So a fresh
  value appears whenever the user next opens Opal.
- End-to-end to the warehouse: **~24–48h** (on-device → Firebase, then Firebase → Snowflake → updater).
  Acceptable for a once-a-day game; not real-time (Julien's Notion note — confirmed).

## The weekday-overwrite trap (must-read for the extraction)

The Firestore source `realtimeScreentimeBenchmarks` is **not a daily log** — it's a **7-slot weekday
ring buffer**:

- Document id is `"<userID>-<dayOfWeek>"` (Sunday=1 … Saturday=7). **At most 7 docs per user.**
- The same weekday next week **overwrites** the prior week's entry.
- So if a user's upload **doesn't run on a given day, that weekday's slot still holds *last week's*
  value** — the doc isn't empty, it's stale by 7 days.

**Safeguard (already baked into the plan):** the warehouse extraction must set `activity_date` from
the doc's **`date`** field (the day the total is *for*), never from extraction time; and the
FocusBoard accrual counts by `activity_date`. A stale slot then carries an old `activity_date`
(≤ `last_counted_date`) and is harmlessly skipped. Extract **≥ daily** so no real day is overwritten
before it's pulled.

## Coverage gaps (expect missing days, by design)

There's no fresh row when:
- the user didn't open Opal that day (chore didn't fire),
- the user is brand-new,
- the user has no age set, or
- it was a zero-screen-time day (the upload is skipped).

Handling: **a missing day is not counted; a 0 / null `screentime_seconds` scores 0 hours saved** —
never `baseline − 0`. Absence means "no data," not "saved a full day."

## The baseline (why fixed 7h, and the caveat)

FocusBoard uses a **fixed 7-hour (25,200s) baseline for everyone**, not a self-reported one — Julien
flagged that declaratives are weak and logged as ranges, and no durable per-user history exists
off-device to derive a measured personal baseline (Firestore keeps only the 7 weekday slots; the
warehouse extraction is snapshot-based).

**Source:** Gen Z averages **6.5 h/day** of phone screen time
([HarmonyHIT, *Phone Screen Time Statistics*](https://www.harmonyhit.com/phone-screen-time-statistics/)),
rounded up to **7 h (25,200s)**.

**Caveat:** the cited figure is *phone* screen time, which is a reasonable match for Opal's
*whole-device total* (the cohort is phone-centric) — closer than the entertainment-only stats often
quoted. Still, re-source it precisely (ideally against Opal's own whole-device cohort average) before
a public, school-facing launch. A fixed bar also rewards being a light user as much as actively
reducing usage — accepted for the first prototype.

## Fragility / what this source is *not*

`realtimeScreentimeBenchmarks` exists for Opal's **peer-benchmark percentile** feature and emits a
**V3 wire-compatible** shape. It is **not a stable downstream data contract**: a refactor of the
benchmark feature (doc-id scheme, V3 retirement) could change or break it silently. There is also
**no long-term history** available here — only the ~7 weekday slots. Both are fine for the
rolling-window, previous-day-only design, but worth knowing before anything depends on it more
heavily.
