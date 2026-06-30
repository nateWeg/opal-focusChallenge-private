# Opal FocusBoard — Prototype 1

## The vision (where this is going)

**"Save 100 hours in 7 days — recruit your friends, scroll less, live more, win rewards."** A student-led pilot wrapped in a fun, shareable challenge: a student recruits friends at their school into a team that races to save 100 hours of screen time in a week, and completing the pilot's form earns rewards. **Teams are schools — schools compete against schools.** The pilot's **real deliverable is pre- and post-install survey data** on students using Opal, to show to schools; **hours saved is the game's currency**. Forms, rewards, the finish-line gate, levels, and school-vs-school rivalry come later (see *The full game*, bottom).

## Linking: gem name → user_id (the key idea)

**The whole system hinges on one link: a student's gem name → their Opal `user_id`.** Students know their **gem** (their Opal username); Opal's data is keyed by **`user_id`**. So we take the gem they give us, look it up in `dim_users` (`lower(gem)` match) to get their `user_id`, and from then on use the stable `user_id` to pull their data. Gems can change or collide; `user_id` can't. The student only ever provides their gem — **no login in Prototype 1**.

## ⛔ Pre-Prototype 1 — Is the daily screen time data reliable?

Before building anything, answer one open-ended question: **is the daily screen time data reliable?** (Forget hours saved and the baseline for now — just validate the raw screen-time number.)

1. **Pull Nate's daily measured screen time** directly from Firestore `realtimeScreentimeBenchmarks` (Julien will show how) for recent days.
2. **Nate checks it against reality** — does each day's number match his actual usage (vs. what his iPhone's Screen Time shows)? Is there a value every day, or are there gaps? Is it **whole-device** screen time or only tracked apps?

**This is the most immediate actionable, and it needs Julien.** If the raw daily screen time isn't trustworthy, nothing downstream is. Only once it checks out do we build Prototype 1.

## Prototype 1 — scope of the build

**Reliably pull daily hours saved — per person and for the whole team — reading screen time straight from Firestore (the warehouse is used only for gem→user_id), and show it as a simple progress bar toward 100 hours.**

- **Teams are schools** in production (schools compete). **The first test is the internal "Opal Team"** — Nate + a couple of coworkers — to prove the pipeline before any school is involved.
- **Real data only** — screen time read directly from Firestore (`realtimeScreentimeBenchmarks`); the Snowflake warehouse is used only for the gem→user_id lookup. No synthetic data.
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
- **Actual screen time** (iOS-measured, per day): the `screentime` field (seconds) from Firestore `realtimeScreentimeBenchmarks`, read directly — **whole-device total** screen time (confirmed in the codebase and independently by Julien; see [`SCREENTIME_DATA_GUIDE.md`](SCREENTIME_DATA_GUIDE.md)). **Score completed days only** — the latest day counted is the **previous calendar day**; today is excluded until it closes (today is still accumulating; matches Opal's own benchmark, which records the prior day).
- **A day with 0 / null / missing screen time scores 0 hours saved** — never `baseline − 0`. Absence means "no data," not "saved a full day."

Per day: `dayHoursSaved = max(0, 25200 − screentime_seconds) / 3600` (floored at 0; only for days with a real screentime value).

## How the daily accrual works (counting each day exactly once)

- **Count only from the day they joined.** When a user joins we store their `joined_date`; days before that never count — saved hours only accrue while they're actually on the board.
- **Each user has a `last_counted_date`** = the last day we've already added to their total. Each daily run adds only days **after** that date (and on/after `joined_date`), through **yesterday**, then moves `last_counted_date` forward. *(In plain terms: a bookmark of "how far we've counted," so no day is counted twice.)*
- **Why this is reliable:** re-running the job can't double-count, and a day missed by a failed run gets picked up next time — as long as its weekday slot still holds it in Firestore (before next week overwrites it).

## What's stored, and where

Stored **only on the FocusBoard** (never read back from Firebase/Snowflake):

- **Per user:** `total_hours_saved` (running total since joining) + `joined_date` + `last_counted_date`. *(No per-user baseline — the 7h baseline is a single global constant.)*
- **Team total** = sum of members' `total_hours_saved`, recomputed each run → drives the progress bar toward 100.

Screen time is read **directly from Firestore** (`realtimeScreentimeBenchmarks`, ≤7 weekday slots/user); the warehouse is used only for the gem→user_id lookup. The FocusBoard does the accumulating.

## ⛔ Prerequisite — data access Julien must provide

For Prototype 1 we read screen time **straight from Firestore** — it's tiny (≤7 docs/user), fresher than the warehouse (which lags ~24–48h), and avoids building a pipeline for a pilot. Snowflake landing comes later, for the schools rollout (durable history + joining to survey data).

1. **Firestore read access to `realtimeScreentimeBenchmarks`.** Docs are keyed `<userID>-<dayOfWeek>` (Sun=1 … Sat=7) — **7 slots per user, each overwritten the next week**, so **no daily history is stored anywhere**. The updater must pull **daily** and persist each day's value before its slot is overwritten. Fields: `screentime` (seconds, whole-device), `date` (the day it's for), `updateDate`. Julien will show how to query Firestore. See [`SCREENTIME_DATA_GUIDE.md`](SCREENTIME_DATA_GUIDE.md).
2. **`dim_users` (warehouse) — already exists.** Used only for the gem→user_id lookup (`lower(gem)`). No new warehouse columns and no screentime table for the prototype.

**Open question for Julien:** easier to read **all opted-in users'** docs each day, or only the **specific gem names** on the roster? *(Both are cheap from Firestore — just a matter of how the read is scoped.)*

## The data, concretely (sample rows)

```
DIM_USERS  (exists; no new column needed — baseline is a fixed constant, not stored here)
 user_id   | gem         | school
 fb_8x2k…  | AzureHawk   | Opal

FIRESTORE realtimeScreentimeBenchmarks/<user_id>-<dayOfWeek>  (read directly — 7 slots/user, overwritten weekly)
 docId       | screentime     | date         | updateDate
 fb_8x2k…-1  | 14400  (4.0h)  | 2026-06-16   | 2026-06-17 08:03Z

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
     read realtimeScreentimeBenchmarks docs from Firestore (≤7 weekday slots)
     for each doc whose `date` is after last_counted_date, on/after joined_date, AND ≤ yesterday (oldest→newest):
        if `screentime` is a real value > 0:
           total_hours_saved += max(0, BASELINE − screentime)/3600
        # 0 / null / missing → contributes nothing
        last_counted_date = that day   # advance even on a no-data day so it can't stall
  team_total = Σ members.total_hours_saved
  write leaderboard-data.json  →  website renders the progress bar + rows
```

## Implementation

**0. (Julien, prerequisite — starts with Pre-Prototype 1)** Grant **Firestore read access to `realtimeScreentimeBenchmarks`** (the prototype reads screen time straight from Firestore; the warehouse is used only for gem→user_id). No screentime table or baseline column in the warehouse — Snowflake landing is deferred to the schools rollout.

**A. updater (Python)**

1. Roster + running-total store (JSON): `{ user_id, gem, total_hours_saved, joined_date, last_counted_date }`.
2. `build_leaderboard.py` — onboard (resolve gem→user_id via the warehouse, set join date) + daily pull (read each user's `realtimeScreentimeBenchmarks` docs from Firestore, add each not-yet-counted completed day from the join date onward against the fixed 7h baseline, sum the team total). Writes `leaderboard-data.json`.

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
- **Stale-weekday-slot guard:** trust each doc's `date` field, not the slot's existence — a weekday slot with no fresh upload still holds last week's value. Pull daily and persist before it's overwritten (see prerequisite + guide).
- **Each day counted once, from the join date**; re-runs are safe; a missed day backfills while its weekday slot still holds it in Firestore (before next week overwrites it).
- **Fresh reads** — pulling Firestore directly avoids the warehouse's ~24–48h lag; the updater runs once a day, which is all a daily game needs.
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

1. **Pre-Prototype 1:** pull Nate's own `realtimeScreentimeBenchmarks` docs from Firestore (user_id `yLFQBR59RbgmIivEDmigkdV0DB92`) and confirm each day matches his iPhone's Screen Time (no gaps, right basis) — answering "is daily screen time data reliable?"
2. **Prototype 1:** seed the Opal Team roster (gems), run the updater (Firestore for screen time, warehouse for gem→user_id), confirm per-person + team totals are correct (Nate checks his own row). Re-run across a couple of days to confirm the daily accrual adds each day once.
3. Render the board data in the website: the progress bar toward 100 and per-member hours look right.

## Notion

A living copy of this plan (for Julien to comment/annotate) lives at: https://app.notion.com/p/382c494896d2819c9214e57666dd0a02
