# CLAUDE.md — Opal FocusBoard context

Context for any Claude Code session working in this repo (Nate's or Julien's). Read [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) for the full plan; this is the quick orientation.

## What this is

A **student-led pilot** wrapped in a game: **"Save 100 hours in 7 days."** A student recruits friends at their school into a team that races to collectively save 100 hours of screen time in a week. **Teams are schools** (schools compete). The game exists to drive participation; the **actual deliverable is pre- and post-install survey data** on students using Opal (collected via two Typeforms), to show to schools. **Hours saved is the game's currency, not the deliverable.**

## Prototype 1 (the current build target — kept deliberately small)

Reliably pull **daily hours saved — per person and for the whole team — from the real Snowflake warehouse**, and show it as a simple **progress bar toward 100 hours**. First test is the internal **"Opal Team"** (Nate + a couple coworkers). No forms, rewards, levels, gate, or login yet.

## The metric (the key metric)

**Hours saved = self-reported baseline screen time (entered at onboarding) − measured daily screen time.** Per day, floored at 0. Score **completed days only** (latest = yesterday; today is still accumulating).

## Data model (how it works)

- **Linking:** a student gives their **gem** (Opal username) → resolve to their Opal **`user_id`** via `dim_users` (`lower(gem)` match). The stable `user_id` keys all data; gems can change. **No login in Prototype 1.**
- **Source:** the warehouse only serves **recent daily screen time** (a rolling ~7-day window) — `screentime_benchmarks(user_id, activity_date, screentime_seconds, update_date)` — plus the baseline `dim_users.stated_screentime_seconds`.
- **Accrual:** the FocusBoard stores the **only persisted metric** — a running `total_hours_saved` per user (since they joined) + a `last_counted_date` so each day is added **exactly once** (re-runs safe, missed days backfill). Count only from each user's `joined_date`. **Team total = sum of members' totals.**
- **Baseline is frozen at join** (anti-gaming — a student can't inflate it later).
- **Assumption:** all participants are **iOS users**.

## Where things live

- **This repo (`opal-focusboard`):** the FocusBoard website (`/web`, Next.js) + the data updater (`/updater`, Python). *(Not built yet.)*
- **`opal-data`** (separate repo, Julien's domain): the Snowflake warehouse + the Firebase→warehouse extraction Julien must build. The updater reads from the warehouse via that repo's Snowflake client pattern (`streamlit_app/database/snowflake_client.py`).

## Immediate next step (gating everything)

**Pre-Prototype 1 — "Is the daily screen time data reliable?"** Julien exposes Nate's recent daily screen time in the warehouse; Nate checks it matches his real usage (no gaps, right basis: whole-device vs tracked-apps). Nothing downstream is built until this checks out.

## Collaborators

- **Nate** — owns the FocusBoard (this repo).
- **Julien** — data scientist; owns the warehouse prerequisite (the screen-time data).
