# CLAUDE.md — Opal FocusBoard context

Context for any Claude Code session working in this repo (Nate's or Julien's). Read [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) for the full plan and [`docs/SCREENTIME_DATA_GUIDE.md`](docs/SCREENTIME_DATA_GUIDE.md) for how the screen-time number is produced and how reliable it is; this is the quick orientation.

## What this is

A **student-pilot engine**: a student who likes Opal recruits friends into a team. The team collectively saves screen-time hours and earns milestone rewards. **No school-vs-school competition** — each team earns rewards independently by hitting thresholds. The **actual deliverable is pre- and post-install survey data** on students using Opal (collected via two Typeforms), to show to school admins. **Hours saved is the game's currency, not the deliverable.**

**Why this exists (the business goal):** the pilot runs at **prospective partner schools**, and the pre-/post-pilot survey data is the evidence we take to **school admins — proof that students actually adopt Opal and would back a school phone policy**. That evidence is how Opal converts a school into a partner.

**Milestone rewards (team-level, cumulative, no time limit):**
- **100 hours** → [Instagram](https://www.instagram.com/opalapp/) Shoutout + [Free Merch Raffle](https://shop.opal.so/)
- **500 hours** → [Free Dumb Phone Raffle](https://dumb.co)
- **1,000 hours** → [Opal Sponsored Party](https://opalapp.com/blog/no-phone-allowed-our-harvard-party)

**Gate:** at 100h, a banner appears on the team card linking to a Typeform reward-claim form (sent via email). Completing the form = prize eligibility.

## Current build state (Prototype 1 — working)

Typeform → `typeform_sync.py` → `teams.json` → Firestore → `build_leaderboard.py` → `leaderboard-data.json` → `index.html` live on Vercel.

**Onboarding is now automated:** new signups via Typeform (`Ph5rIiZ7`) are pulled automatically every time `build_leaderboard.py` runs. No manual `teams.json` edits needed for new members. New school teams are created automatically with fuzzy name matching. Gem emails are stored in gitignored `emails.json` (never sent to the frontend). New members with an email on file are automatically sent a welcome email (see *Welcome emails* below) — **dry-run by default; set `SEND_EMAILS=1` in `.env` to send live.**

**Active teams (as of 2026-06-24):** Opal Academy (5 gems), Stanford University (truittite), UC Berkeley (TalaeTui2154), Dalhousie University (ash2).

## The metric (the key metric)

**Hours saved = a fixed 7h (25,200s) baseline − measured daily screen time.** Per day, floored at 0; the baseline is the same for everyone (not self-reported, not per-user). Score **completed days only** (latest = yesterday; today is still accumulating). A day with 0/null/missing screen time scores 0 saved (never `baseline − 0`).

## Data model (how it works)

- **Linking:** a student gives their **gem** (Opal username) → resolve to their Opal **`user_id`** via the Firestore `users` collection (`gemname_lowercase` field; doc id = user_id). The stable `user_id` keys all data; gems can change. **No login in Prototype 1.**
- **Source:** everything is read **directly from Firestore** — no Snowflake for Prototype 1. `realtimeScreentimeBenchmarks` (≤7 weekday slots/user, overwritten weekly; field `screentime`, seconds, **whole-device total**) for screen time; `users` collection for gem→user_id. Baseline is a **fixed 7h constant** in the updater. (Snowflake landing deferred to the schools rollout.)
- **Accrual:** the FocusBoard stores the **only persisted metric** — a running `total_hours_saved` per user (since they joined) + a `last_counted_date` so each day is added **exactly once** (re-runs safe, missed days backfill). Count only from each user's `joined_date`. **Team total = sum of members' totals.**
- **Baseline:** fixed 7h, same for everyone — not self-reported, nothing to inflate. (Gen Z ≈ 6.5 h/day phone screen time rounded to 7 h — [HarmonyHIT](https://www.harmonyhit.com/phone-screen-time-statistics/); see [`docs/SCREENTIME_DATA_GUIDE.md`](docs/SCREENTIME_DATA_GUIDE.md).)
- **Assumption:** all participants are **iOS users**.
- **Privacy:** the data flow is intermediated — the updater (server-side, holds the service-account key) reads Firestore and writes a derived `leaderboard-data.json`; the **browser never touches Firebase** and never sees the key. The key lives only on the updater's host (git-ignored, never in `/web`); since Firestore IAM has no collection-level scope, treat it as all-of-prod read access. The client payload carries **only gem + hours saved** — never `user_id`. (See *Privacy & data handling* in [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md).)

## Where things live

| Thing | Location | Notes |
|---|---|---|
| **Live UI** | `updater/index.html` | The only UI file that matters. Deployed to Vercel. |
| **Live URL** | https://updater-bice.vercel.app | Production. Any `vercel --prod` from `updater/` updates this. |
| **Data updater** | `updater/build_leaderboard.py` | Calls typeform_sync first, then reads Firestore → writes `leaderboard-data.json`. Run daily. |
| **Typeform sync** | `updater/typeform_sync.py` | Pulls new signups from Typeform, deduplicates, fuzzy-matches schools, updates `teams.json`. Auto-runs inside `build_leaderboard.py`. |
| **Typeform token** | `updater/.env` | `TYPEFORM_TOKEN=...` — gitignored. Typeform form ID: `Ph5rIiZ7`. |
| **Email store** | `updater/emails.json` | gem → email mapping. Gitignored. Backend only, never in frontend payload. |
| **Welcome emails** | `updater/email_notify.py` | Sends a personal welcome from `nate@opalapp.com` (Gmail SMTP) when a new member first appears. Auto-runs inside `build_leaderboard.py`. **Dry-run unless `SEND_EMAILS=1`.** Needs `GMAIL_USER` + `GMAIL_APP_PASSWORD` in `.env`. |
| **Leaderboard data** | `updater/leaderboard-data.json` | Generated by the updater; served statically by Vercel alongside `index.html`. |
| **Team config** | `updater/teams.json` | Source of truth for gems/teams. Edit this to add members or new schools. |
| **State file** | `updater/state.json` | Tracks gem → user_id + joined_date + `welcomed` flag (gates the welcome email). Committed to repo (needed for automation later). |
| **Firestore (prod)** | project `opal-fa413` | Auth via gcloud ADC (`~/.config/gcloud/application_default_credentials.json`). |
| **Obsolete** | `updater/focusboard.html` | Old static artifact. Ignore it — `index.html` is the live UI. |

**Do NOT touch `/web`** — that Next.js scaffold was the old plan and is not used.

## How to make UI changes

1. Edit `updater/index.html`
2. From `updater/` run: `vercel --prod`
3. Changes are live at https://updater-bice.vercel.app immediately

## How to refresh data

From `updater/`:
```bash
python3 build_leaderboard.py
vercel --prod   # re-deploys leaderboard-data.json to Vercel
```

Firestore auth uses gcloud ADC — no service-account key file needed locally.

## Adding a new team member (gem)

Edit `updater/teams.json` — add the gem name to the relevant team's `gems` array. Then run the updater. The script resolves gem → `user_id` on first run and saves it to `state.json`.

## Adding a new school team

Edit `updater/teams.json` — append a new object: `{"teamName": "School Name", "gems": ["gem1", "gem2"]}`. Then run the updater.

## Vercel project info

- **Project name:** `updater`
- **Org:** `2opalfocusboard2`
- **Project ID:** `prj_5xDinCOQiaLJ4ZmzFiDN6EGYjLWz`
- **Config:** `updater/vercel.json` — `outputDirectory: "."`, no framework, no build step
- **Gitignored files served by Vercel:** `index.html`, `leaderboard-data.json` (both gitignored but uploaded on every `vercel --prod`)

## Collaborators

- **Nate** — owns the FocusBoard (this repo).
- **Julien** — data scientist; owns the Firestore access prerequisite (service-account key for prod).
