# Opal FocusBoard — Prototype 1

## The vision (where this is going)

**"Save 100 hours in 7 days — recruit your friends, scroll less, live more, win rewards."** A student-led pilot wrapped in a fun, shareable challenge: a student recruits friends at their school into a team that races to save 100 hours of screen time in a week, and completing the pilot's form earns rewards. **Teams are schools — schools compete against schools.** The pilot's **real deliverable is pre- and post-install survey data** on students using Opal, to show to schools; **hours saved is the game's currency**. Forms, rewards, the finish-line gate, levels, and school-vs-school rivalry come later (see *The full game*, bottom).

## Linking: gem name → user_id (the key idea)

**The whole system hinges on one link: a student's gem name → their Opal `user_id`.** Students know their **gem** (their Opal username); Opal's data is keyed by **`user_id`**. So we take the gem they give us, look it up in `dim_users` (`lower(gem)` match) to get their `user_id`, and from then on use the stable `user_id` to pull their data. Gems can change or collide; `user_id` can't. The student only ever provides their gem — **no login in Prototype 1**.

## ⛔ Pre-Prototype 1 — Is the daily screen time data reliable?

Before building anything, answer one open-ended question: **is the daily screen time data reliable?** (Forget hours saved and the baseline for now — just validate the raw screen-time number.)

1. **Julien makes accessible in the warehouse** Nate's **daily measured screen time** (`screentime_seconds`, from Firestore `realtimeScreentimeBenchmarks`) for recent days.
2. **Nate checks it against reality** — does each day's number match his actual usage (vs. what his iPhone's Screen Time shows)? Is there a value every day, or are there gaps? Is it **whole-device** screen time or only tracked apps?

**This is the most immediate actionable, and it needs Julien.** If the raw daily screen time isn't trustworthy, nothing downstream is. Only once it checks out do we build Prototype 1.

## Prototype 1 — scope of the build

**Reliably pull daily hours saved — per person and for the whole team — from the real warehouse, and show it as a simple progress bar toward 100 hours.**

- **Teams are schools** in production (schools compete). **The first test is the internal "Opal Team"** — Nate + a couple of coworkers — to prove the pipeline before any school is involved.
- **Pulls from the real source (the Snowflake warehouse)** — no synthetic data.
- UI: a single **progress bar toward 100 hours saved**, framed as how far the team is from the rewards (*"X hours from free merch, free Opal PRO & an IG shoutout"*), + each member's gem, total hours saved, and yesterday's daily savings.
- **No** forms, rewards, level ladder, gate, or login in Prototype 1.
- **Assumption:** all participants are **iOS users** — the screen-time benchmark data we rely on is iOS; Android/macOS is out of scope for now.

## UI mock (what Prototype 1 looks like)

```
╭──────────────────────────────────────────────────────────────────╮
│                🔒   O P A L   F O C U S B O A R D                  │
│                   Save 100 hours in 7 days                         │
│        recruit your friends · scroll less · live more · win        │
╰──────────────────────────────────────────────────────────────────╯

 ┌────────────────────────────────────────────────────────────────┐
 │  OPAL TEAM                                    6 gems locked-in   │
 │   73.5 / 100  hours saved                                        │
 │   ████████████████████████████████████░░░░░░░░░░░░░░   73%       │
 │   🎁 26.5 hrs from free merch · free Opal PRO · an IG shoutout   │
 │   ⏳ 3 days left                                                 │
 └────────────────────────────────────────────────────────────────┘

   #    GEM                       HOURS SAVED         YESTERDAY
   🥇 1  AzureHawk                     18.2 h            +2.5 h
   🥈 2  CrimsonLark                   15.0 h            +1.8 h
   🥉 3  GoldenWren                    13.4 h            +2.1 h
      4  PearlMoon                     11.8 h            +0.0 h
      5  JadeFox                        9.6 h            +1.2 h
      6  OnyxOwl                        5.5 h            +0.7 h
            TEAM TOTAL                  73.5 h     today  +8.3 h
```

*(First test shows "Opal Team"; in production the team name is the school. Colors/styling are illustrative.)*

## The metric: hours saved (the key metric)

**Hours saved is the key metric the FocusBoard runs on.** It's each user's **measured daily screen time subtracted from a fixed baseline that's the same for everyone**:

**Hours saved = baseline − daily screen time.**

- **Baseline** — a **fixed 7 hours (25,200s) for every user**: Gen Z averages **6.5 h/day** of phone screen time ([HarmonyHIT, *Phone Screen Time Statistics*](https://www.harmonyhit.com/phone-screen-time-statistics/)), rounded up to 7 h. Not self-reported and not per-user: there's no number to inflate and nothing to freeze at join. *(Note: the cited figure is phone screen time — a reasonable match for Opal's whole-device total — but still worth re-sourcing against Opal's own cohort average before a public, school-facing launch. A fixed bar also rewards being a light user as much as actively reducing usage; acceptable for a first prototype, revisit personalization later.)*
- **Actual screen time** (iOS-measured, per day): `screentime_benchmarks.screentime_seconds` — **whole-device total** screen time (confirmed in the codebase; see [`SCREENTIME_DATA_GUIDE.md`](SCREENTIME_DATA_GUIDE.md)). **Score completed days only** — the latest day counted is the **previous calendar day**; today is excluded until it closes (today is still accumulating; matches Opal's own benchmark, which records the prior day).
- **A day with 0 / null / missing screen time scores 0 hours saved** — never `baseline − 0`. Absence means "no data," not "saved a full day."

Per day: `dayHoursSaved = max(0, 25200 − screentime_seconds) / 3600` (floored at 0; only for days with a real screentime value).

## How the daily accrual works (counting each day exactly once)

- **Count only from the day they joined.** When a user joins we store their `joined_date`; days before that never count — saved hours only accrue while they're actually on the board.
- **Each user has a `last_counted_date`** = the last day we've already added to their total. Each daily run adds only days **after** that date (and on/after `joined_date`), through **yesterday**, then moves `last_counted_date` forward. *(In plain terms: a bookmark of "how far we've counted," so no day is counted twice.)*
- **Why this is reliable:** re-running the job can't double-count, and a day missed by a failed run gets picked up next time — as long as it's still in the warehouse's recent window.

## What's stored, and where

Stored **only on the FocusBoard** (never read back from Firebase/Snowflake):

- **Per user:** `total_hours_saved` (running total since joining) + `joined_date` + `last_counted_date`. *(No per-user baseline — the 7h baseline is a single global constant.)*
- **Team total** = sum of members' `total_hours_saved`, recomputed each run → drives the progress bar toward 100.

The warehouse only **serves recent daily screen time** (a rolling ~7-day window); the FocusBoard does the accumulating.

## ⛔ Prerequisite — warehouse data Julien must provide

Not in the warehouse today; Julien extracts it daily from Firebase. **No baseline column is needed** — the baseline is a fixed 7h constant in the updater, so `dim_users` is used as-is (`user_id`, `gem`, `school`):

1. **`screentime_benchmarks`** — recent daily screen time per user; grain one row per `(user_id, activity_date)`; columns `user_id`, `activity_date`, `screentime_seconds`, `update_date`. **Only a recent window needed** (≈ last 7 days). Must extract **≥ daily**, and **set `activity_date` from the Firestore doc's `date` field** (not extraction time). The source `realtimeScreentimeBenchmarks` is a **7-slot weekday ring buffer** (doc id `<userID>-<dayOfWeek>`, overwritten weekly), *not* a 7-day log — so a day with no upload leaves **last week's** value sitting in that weekday's slot. Keying on `date` means a stale slot carries an old `activity_date` and is harmlessly skipped (≤ `last_counted_date`); extracting ≥ daily means no real day is overwritten before it's pulled. See [`SCREENTIME_DATA_GUIDE.md`](SCREENTIME_DATA_GUIDE.md).

**Open question for Julien:** easier to pull **all users'** recent screen time, or only the **specific gem names** that opted in? *(All = decoupled/future-proof but more data; opted-in = leaner but couples the extraction to the roster. Julien's call.)*

## The data, concretely (sample rows)

```
DIM_USERS  (exists; no new column needed — baseline is a fixed constant, not stored here)
 user_id   | gem         | school
 fb_8x2k…  | AzureHawk   | Opal

SCREENTIME_BENCHMARKS  (recent ~7 days per user — Julien builds)
 user_id   | activity_date | screentime_seconds | update_date
 fb_8x2k…  | 2026-06-16    | 14400  (4.0h)      | 2026-06-17 08:03Z

BASELINE = 25200  (fixed 7h, same for everyone — lives in the updater, not the warehouse)

OUR STORE  (the only persisted metric — on the FocusBoard)
 user_id  | gem        | total_hours_saved | joined_date | last_counted_date
 fb_8x2k… | AzureHawk  | 8.0               | 2026-06-13  | 2026-06-16
```

On 6/16, AzureHawk's measured 4.0h vs the fixed 7.0h baseline = **+3.0h** added; `last_counted_date` moves to 6/16. Days before 6/13 (join) never count.

## Data-pulling flow

```
ONBOARD  (once per member, to seed the team)
  gem  →  resolve gem → user_id via dim_users (lower(gem); 0/>1 matches → review)
       →  store { user_id, gem,
            total_hours_saved: 0, joined_date: today, last_counted_date: today }

BASELINE = 25200   (fixed 7h, same for everyone)

DAILY PULL  (once/day, every member — daily because it's a daily game)
  for each user_id:
     pull recent days WHERE activity_date > last_counted_date
     for each day on/after joined_date AND ≤ yesterday (oldest→newest):
        if screentime_seconds is a real value > 0:
           total_hours_saved += max(0, BASELINE − screentime_seconds)/3600
        # 0 / null / missing → contributes nothing
        last_counted_date = that day   # advance even on a no-data day so it can't stall
  team_total = Σ members.total_hours_saved
  write leaderboard-data.json  →  website renders the progress bar + rows
```

## Implementation

**0. (Julien, prerequisite — starts with Pre-Prototype 1)** Make the `screentime_benchmarks` table accessible in the warehouse. *(No baseline column needed — the 7h baseline is a constant in the updater, not stored per user.)*

**A. updater (Python)**

1. Roster + running-total store (JSON): `{ user_id, gem, total_hours_saved, joined_date, last_counted_date }`.
2. `build_leaderboard.py` — onboard (resolve gem→user_id, freeze baseline, set join date) + daily pull (query the warehouse, add each not-yet-counted completed day from the join date onward, sum the team total). Writes `leaderboard-data.json`.

**B. website (Next.js)**

1. API route reads `leaderboard-data.json`.
2. Hours-saved model; keep an `isFlagged` sanity check internally.
3. The **"Save 100 hours" progress bar** (team total → 100) + **member rows** (gem · total hours saved · yesterday's savings), per the mock above. No levels/rewards/gate.

### Display data contract (website input)

```json
{ "teamName": "Opal Team", "totalHoursSaved": 0.0, "goalHours": 100, "memberCount": 0,
  "members": [ { "userId": "<uid>", "gemName": "<gem>", "hoursSaved": 0.0, "yesterdayHoursSaved": 0.0 } ] }
```

## Data reliability & handling

- **Screen time only exists for days the user opened Opal** (the upload is a daily on-foreground chore; it's also skipped for brand-new users, users with no age set, and zero-screen-time days). A day with no row is simply not counted.
- **0 / null / missing screen time → 0 hours saved** — never `baseline − 0`. Absence is "no data," not a saved day.
- **~15-minute accuracy floor.** The number is Apple-DeviceActivity-quantized (≈15-min granularity) — fine for a daily hours-saved metric, not a precise per-minute figure. See [`SCREENTIME_DATA_GUIDE.md`](SCREENTIME_DATA_GUIDE.md).
- **Stale-weekday-slot guard:** key on the Firestore doc's `date` field (carried into `activity_date`), not the mere existence of a row — the source is a 7-slot weekday ring buffer (see prerequisite + guide).
- **Each day counted once, from the join date**; re-runs are safe; a missed day backfills while still in the warehouse's recent window.
- **~24–48h latency** (Firebase→warehouse, then the updater) — fine for a daily game.
- **Fixed 7h baseline** — same for everyone, not self-reported (interim figure; see the metric note).
- **iOS-only assumption** for the pilot.
- Keep an `isFlagged` sanity check (≥2 days under 1h).

## User onboarding (how real students join — Prototype 1's Opal Team is hand-seeded)

*(For Prototype 1's Opal Team the roster is hand-seeded by gem name — no form. This is the rollout flow.)*

A **sign-up "starting line" form** (the pre-pilot Typeform) goes to new and existing users, asking for their **school (their team)**, their **gem name** (to match identity to their Opal data), and a couple of **qualitative pilot questions** (the pre-pilot data). Then:

- **Existing Opal user** → redirected straight to the FocusBoard, where they now see themselves populated.
- **New user** → redirected to a **free Opal PRO sign-up (1 month)** → log in, set their gem name → return to the form, enter that gem name → redirected to the leaderboard.

*(Intentionally a bit involved for now; can be refined — Julien, better ideas welcome.)*

**Alternative considered (for discussion):** user copies the FocusBoard link → free 1-month Opal PRO sign-up → opens the link in Safari, where **everyone logs in with their Opal credentials**. Not chosen for now mainly because **web login (especially Apple sign-in) is hard to support** — revisit later.

## The full game (after Prototype 1)

Once the data + progress bar are proven: the **7-day challenge** with a countdown; the **pre-/post-pilot Typeforms** (the post-form is the deliverable); **rewards gated on completing the form** (extended Opal PRO, a raffle entry, an **Opal Instagram repost — form-only**, and more); **school-vs-school rivalry**; the **levels ladder** (🌈 → 🥇 → 🧘 → ✨ → 📵 → 🛡️); **verified sign-in**; **referrer bonuses**; **Opal Campus Leaders**; automation + scheduling; **Android support**.

## Open questions / to verify

1. **(Pre-Prototype 1)** Daily screen-time reliability — *producer-side architecture validated* (whole-device total, ~15-min accuracy, gap/overwrite behavior; see [`SCREENTIME_DATA_GUIDE.md`](SCREENTIME_DATA_GUIDE.md)). Still pending: Nate's empirical spot-check that his own recent daily numbers match his real usage with no gaps.
2. ~~Whether `screentime_seconds` is whole-device or tracked-apps-only.~~ **Resolved: whole-device total** (`AppScreenTimeStore.loadTotalScreenTime`). The fixed 7h baseline uses Gen Z phone screen time (6.5 h → 7 h, [HarmonyHIT](https://www.harmonyhit.com/phone-screen-time-statistics/)), a reasonable match for the whole-device basis — still worth re-sourcing against Opal's own cohort before a school-facing launch.
3. Gem-match review for unmatched/ambiguous typed gems.

## Verification (real data — no synthetic)

1. **Pre-Prototype 1:** pull Nate's recent daily screen time from the warehouse and confirm each day matches his real usage (no gaps, right basis) — answering "is daily screen time data reliable?"
2. **Prototype 1:** seed the Opal Team roster (gems), run the updater against the warehouse, confirm per-person + team totals are correct (Nate checks his own row). Re-run across a couple of days to confirm the daily accrual adds each day once.
3. Render the board data in the website: the progress bar toward 100 and per-member hours look right.

## Notion

A living copy of this plan (for Julien to comment/annotate) lives at: https://app.notion.com/p/382c494896d2819c9214e57666dd0a02
