# Opal FocusBoard

**"Save 100 hours in 7 days — recruit your friends, scroll less, live more, win rewards."**

A student-led pilot wrapped in a fun, shareable challenge. Students at a school form a team and race to save 100 hours of screen time in a week. The game is the engagement wrapper; the **real deliverable is pre- and post-install survey data** on students using Opal, to show to schools. **Hours saved is the game's currency** (not the deliverable).

## Status

**Planning → Pre-Prototype 1.** No app code yet. The immediate step is a data-reliability check (does the warehouse hold trustworthy daily screen-time?) before any building. See the plan.

## The plan

- Full plan: [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md)
- Screen-time data reliability (how the number is produced, how accurate, known traps): [`docs/SCREENTIME_DATA_GUIDE.md`](docs/SCREENTIME_DATA_GUIDE.md)
- Living Notion copy (for comments/annotations): https://app.notion.com/p/382c494896d2819c9214e57666dd0a02
- Context for Claude Code sessions: [`CLAUDE.md`](CLAUDE.md)

## Who

- **Nate** — building the FocusBoard (this repo: the website + the data updater).
- **Julien** — data scientist; owns getting Opal's screen-time data into the warehouse (the gating prerequisite).

## Planned structure (to be built)

```
/web        Next.js website — the board (progress bar toward 100h + member rows)
/updater    Python job — pulls daily screen time, accrues hours saved, writes the board's data
/docs       Plan + context
```
