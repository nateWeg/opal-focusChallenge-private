# CLAUDE.md — Opal FocusBoard context

Context for any Claude Code session working in this repo (Nate's or Julien's). Read [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) for the full plan and [`docs/SCREENTIME_DATA_GUIDE.md`](docs/SCREENTIME_DATA_GUIDE.md) for how the screen-time number is produced and how reliable it is; this is the quick orientation.

## What this is

A **student-led pilot** wrapped in a game: **"Save 100 hours in 7 days."** A student recruits friends at their school into a team that races to collectively save 100 hours of screen time in a week. **Teams are schools** (schools compete). The game exists to drive participation; the **actual deliverable is pre- and post-install survey data** on students using Opal (collected via two Typeforms), to show to schools. **Hours saved is the game's currency, not the deliverable.**

## Prototype 1 (the current build target — kept deliberately small)

Reliably pull **daily hours saved — per person and for the whole team — from the real Snowflake warehouse**, and show it as a simple **progress bar toward 100 hours**. First test is the internal **"Opal Team"** (Nate + a couple coworkers). No forms, rewards, levels, gate, or login yet.

## The metric (the key metric)

**Hours saved = a fixed 7h (25,200s) baseline − measured daily screen time.** Per day, floored at 0; the baseline is the same for everyone (not self-reported, not per-user). Score **completed days only** (latest = yesterday; today is still accumulating). A day with 0/null/missing screen time scores 0 saved (never `baseline − 0`).

## Data model (how it works)

- **Linking:** a student gives their **gem** (Opal username) → resolve to their Opal **`user_id`** via `dim_users` (`lower(gem)` match). The stable `user_id` keys all data; gems can change. **No login in Prototype 1.**
- **Source:** screen time is read **directly from Firestore** for Prototype 1 — `realtimeScreentimeBenchmarks` (≤7 weekday slots/user, overwritten weekly; field `screentime`, seconds, **whole-device total**). The warehouse is used **only** for the gem→user_id lookup (`dim_users`). Baseline is a **fixed 7h constant** in the updater. (Landing screen time in Snowflake is deferred to the schools rollout.)
- **Accrual:** the FocusBoard stores the **only persisted metric** — a running `total_hours_saved` per user (since they joined) + a `last_counted_date` so each day is added **exactly once** (re-runs safe, missed days backfill). Count only from each user's `joined_date`. **Team total = sum of members' totals.**
- **Baseline:** fixed 7h, same for everyone — not self-reported, nothing to inflate. (Gen Z ≈ 6.5 h/day phone screen time rounded to 7 h — [HarmonyHIT](https://www.harmonyhit.com/phone-screen-time-statistics/); see [`docs/SCREENTIME_DATA_GUIDE.md`](docs/SCREENTIME_DATA_GUIDE.md).)
- **Assumption:** all participants are **iOS users**.

## Where things live

- **This repo (`opal-focusboard`):** the FocusBoard website (`/web`, Next.js) + the data updater (`/updater`, Python). *(Not built yet.)*
- **`opal-data`** (separate repo, Julien's domain): the Snowflake warehouse, used here **only** for the gem→user_id lookup (via that repo's Snowflake client pattern, `streamlit_app/database/snowflake_client.py`). Screen time is read **directly from Firestore**; landing it in Snowflake is deferred to the schools rollout.

## Immediate next step (gating everything)

**Pre-Prototype 1 — "Is the daily screen time data reliable?"** Producer-side is answered: it's **whole-device total**, ~15-min accurate, with known gap/overwrite behavior (see [`docs/SCREENTIME_DATA_GUIDE.md`](docs/SCREENTIME_DATA_GUIDE.md)). Still gating: pull Nate's recent daily screen time from Firestore (`realtimeScreentimeBenchmarks`) and confirm it matches his real usage (no gaps). Nothing downstream is built until that empirical check passes.

## Collaborators

- **Nate** — owns the FocusBoard (this repo).
- **Julien** — data scientist; owns the warehouse prerequisite (the screen-time data).
