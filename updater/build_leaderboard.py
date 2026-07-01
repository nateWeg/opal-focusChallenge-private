import datetime
import json
import os
from google.cloud import firestore
import typeform_sync
import email_notify
typeform_sync.run()

PROJECT_ID = "opal-fa413"
BASELINE_SECONDS = 25200  # fixed 7h
MAX_SCREENTIME = 39600   # 11h cap — above this treated as outlier/neutral

MILESTONES = [
    {"hours": 100,  "reward": "Instagram Shoutout"},
    {"hours": 500,  "reward": "Free Merch Raffle"},
    {"hours": 1000, "reward": "Opal Sponsored Party"},
]
REWARD_FORM_URL = "https://opal.so"  # replace with real Typeform URL when ready

TEAMS_FILE  = os.path.join(os.path.dirname(__file__), "teams.json")
STATE_FILE  = os.path.join(os.path.dirname(__file__), "state.json")
EMAILS_FILE = os.path.join(os.path.dirname(__file__), "emails.json")
OUT_FILE    = os.path.join(os.path.dirname(__file__), "leaderboard-data.json")

db = firestore.Client(project=PROJECT_ID)

today      = datetime.date.today()
yesterday  = today - datetime.timedelta(days=1)
two_days_ago = today - datetime.timedelta(days=2)

with open(TEAMS_FILE) as f:
    teams_config = json.load(f)

if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        state = json.load(f)
else:
    state = {}

if os.path.exists(EMAILS_FILE):
    with open(EMAILS_FILE) as f:
        emails = json.load(f)
else:
    emails = {}

pending_welcomes = []   # (gem_key, gem_display, email, team_name) for new members not yet welcomed

def process_gems(gems, team_name):
    members = []
    for gem in gems:
        print(f"Looking up '{gem}'...")
        users = db.collection("users").where(filter=firestore.FieldFilter("gemname_lowercase", "==", gem.lower())).get()
        if not users:
            print(f"  WARNING: not found, skipping")
            continue

        user_id     = users[0].id
        gem_display = users[0].to_dict().get("gemname", gem)
        key         = gem.lower()

        if key not in state:
            state[key] = {
                "user_id":     user_id,
                "gem_display": gem_display,
                "joined_date": two_days_ago.isoformat(),
                "welcomed":    False,
            }
            print(f"  New gem — joined_date set to {two_days_ago}")

        # Queue a welcome email for anyone not yet welcomed who has an email on file
        if not state[key].get("welcomed") and key in emails:
            pending_welcomes.append((key, gem_display, emails[key], team_name))

        joined_date = datetime.date.fromisoformat(state[key]["joined_date"])
        print(f"  {gem_display} | joined: {joined_date} | user_id: {user_id}")

        days = []
        for slot in range(1, 8):
            doc = db.collection("realtimeScreentimeBenchmarks").document(f"{user_id}-{slot}").get()
            if not doc.exists:
                continue
            data       = doc.to_dict()
            raw_date   = data.get("date")
            screentime = data.get("screentime")

            if hasattr(raw_date, "date"):
                day = raw_date.date()
            elif isinstance(raw_date, datetime.datetime):
                day = raw_date.date()
            else:
                continue

            if day < joined_date or day > two_days_ago:
                continue

            if not screentime or screentime <= 0:
                hours_saved = 0
                missing     = True
            elif screentime > MAX_SCREENTIME:                 # >11h — outlier/corrupted, neutral
                hours_saved = 0
                missing     = True
            else:
                hours_saved = (BASELINE_SECONDS - screentime) / 3600   # negative for 7–11h = lost hours
                missing     = False

            days.append({
                "date":        day,
                "screentime_h": round((screentime or 0) / 3600, 2),
                "hours_saved": round(hours_saved, 2),
                "missing":     missing,
            })

        data_by_date = {d["date"]: d for d in days}
        all_days = []
        cur = joined_date
        while cur <= two_days_ago:
            if cur in data_by_date:
                all_days.append(data_by_date[cur])
            else:
                all_days.append({"date": cur, "screentime_h": 0, "hours_saved": 0, "missing": True})
            cur += datetime.timedelta(days=1)

        total_saved  = round(sum(d["hours_saved"] for d in all_days), 2)
        latest_saved = all_days[-1]["hours_saved"] if all_days else 0.0

        streak = 0
        for d in all_days:
            if d["missing"]:
                continue                      # NA — neutral
            if d["hours_saved"] > 0:
                streak += 1
            elif d["hours_saved"] < 0:
                streak = 0                    # only a loss ends it
            # hours_saved == 0 → neutral

        print(f"  {len(all_days)} days in window → {total_saved}h saved, streak {streak}")

        members.append({
            "gem":         gem_display,
            "joined_date": joined_date,
            "days":        all_days,
            "total_saved": total_saved,
            "latest_saved": latest_saved,
            "streak":      streak,
        })
    return members

def members_to_json(members):
    return [
        {
            "gemName":          m["gem"],
            "hoursSaved":       m["total_saved"],
            "latestHoursSaved": m["latest_saved"],
            "streak":           m["streak"],
            "days": [
                {
                    "date":        d["date"].isoformat(),
                    "screentimeH": d["screentime_h"],
                    "hoursSaved":  d["hours_saved"],
                    "missing":     d["missing"],
                }
                for d in m["days"]
            ],
        }
        for m in members
    ]

all_teams = []
for team_cfg in teams_config:
    members = process_gems(team_cfg["gems"], team_cfg["teamName"])
    members.sort(key=lambda m: m["total_saved"], reverse=True)
    team_total = round(sum(m["total_saved"] for m in members), 2)
    team_daily = round(sum(m["latest_saved"] for m in members), 2)
    all_teams.append({
        "teamName":        team_cfg["teamName"],
        "totalHoursSaved": team_total,
        "dailyHoursSaved": team_daily,
        "goalHours":       MILESTONES[0]["hours"],
        "memberCount":     len(members),
        "members":         members_to_json(members),
    })
    print(f"\n{team_cfg['teamName']}: {team_total}h total, +{team_daily}h yesterday")

# Welcome emails for new members — rank teams by total hours saved (1-indexed)
if pending_welcomes:
    ranked = sorted(all_teams, key=lambda t: t["totalHoursSaved"], reverse=True)
    place_by_team = {t["teamName"]: i + 1 for i, t in enumerate(ranked)}
    leading_team = ranked[0]["teamName"] if ranked else ""
    print(f"\nWelcome emails ({len(pending_welcomes)} pending):")
    for gem_key, gem_display, to_email, team_name in pending_welcomes:
        place = place_by_team.get(team_name, len(ranked))
        if email_notify.send_welcome(to_email, gem_display, team_name, place, leading_team):
            state[gem_key]["welcomed"] = True

with open(STATE_FILE, "w") as f:
    json.dump(state, f, indent=2)

# ── Mock demo team (Harvard) — synthetic, NOT from Firestore ──────────────────
# For demos. Total is ~25h today and grows +1h each calendar day. Remove this
# block (set MOCK_TEAMS = False) to drop the fake team.
MOCK_TEAMS = True

def build_mock_harvard():
    anchor = datetime.date(2026, 6, 30)          # ~25h as of this date
    total  = 25 + max(0, (today - anchor).days)  # +1h/day thereafter
    ndays  = 8
    start  = two_days_ago - datetime.timedelta(days=ndays - 1)
    specs  = [("pixelgoblin", 0.40), ("noodlebandit", 0.34), ("ferret_lord99", 0.26)]
    weights = list(range(1, ndays + 1))          # increasing daily ramp
    wsum = sum(weights)

    members = []
    for name, share in specs:
        target, running, days, cur = round(total * share, 2), 0.0, [], start
        for i, w in enumerate(weights):
            hs = round(target - running, 2) if i == ndays - 1 else round(target * w / wsum, 2)
            hs = max(0.0, hs); running += hs
            days.append({
                "date":        cur.isoformat(),
                "screentimeH": round(max(0.0, 7 - hs), 2),
                "hoursSaved":  hs,
                "missing":     False,
            })
            cur += datetime.timedelta(days=1)
        members.append({
            "gemName":          name,
            "hoursSaved":       round(sum(d["hoursSaved"] for d in days), 2),
            "latestHoursSaved": days[-1]["hoursSaved"],
            "streak":           ndays,
            "days":             days,
        })
    members.sort(key=lambda m: m["hoursSaved"], reverse=True)
    return {
        "teamName":        "Harvard University",
        "totalHoursSaved": round(sum(m["hoursSaved"] for m in members), 2),
        "dailyHoursSaved": round(sum(m["latestHoursSaved"] for m in members), 2),
        "goalHours":       MILESTONES[0]["hours"],
        "memberCount":     len(members),
        "members":         members,
    }

if MOCK_TEAMS:
    harvard = build_mock_harvard()
    all_teams.append(harvard)
    print(f"\n[mock] {harvard['teamName']}: {harvard['totalHoursSaved']}h total ({harvard['memberCount']} mock gems)")

leaderboard = {
    "milestones":  MILESTONES,
    "generatedAt": today.isoformat(),
    "teams":       all_teams,
}

with open(OUT_FILE, "w") as f:
    json.dump(leaderboard, f, indent=2)

print(f"Wrote: {OUT_FILE}")
