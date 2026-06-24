import datetime
import json
import os
from google.cloud import firestore
import typeform_sync
typeform_sync.run()

PROJECT_ID = "opal-fa413"
BASELINE_SECONDS = 25200  # fixed 7h
MAX_SCREENTIME = 43200   # 12h cap — above this treated as missing/corrupted

MILESTONES = [
    {"hours": 100,  "reward": "Instagram Shoutout + Free Merch Raffle"},
    {"hours": 500,  "reward": "Free Dumb Phone Raffle"},
    {"hours": 1000, "reward": "Opal Sponsored Party"},
]
REWARD_FORM_URL = "https://opal.so"  # replace with real Typeform URL when ready

TEAMS_FILE = os.path.join(os.path.dirname(__file__), "teams.json")
STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")
OUT_FILE   = os.path.join(os.path.dirname(__file__), "leaderboard-data.json")

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

def process_gems(gems):
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
            }
            print(f"  New gem — joined_date set to {two_days_ago}")

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

            if not screentime or screentime <= 0 or screentime > MAX_SCREENTIME:
                hours_saved = 0
                missing     = True
            else:
                hours_saved = max(0, BASELINE_SECONDS - screentime) / 3600
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
        print(f"  {len(all_days)} days in window → {total_saved}h saved")

        members.append({
            "gem":         gem_display,
            "joined_date": joined_date,
            "days":        all_days,
            "total_saved": total_saved,
            "latest_saved": latest_saved,
        })
    return members

def members_to_json(members):
    return [
        {
            "gemName":          m["gem"],
            "hoursSaved":       m["total_saved"],
            "latestHoursSaved": m["latest_saved"],
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
    members = process_gems(team_cfg["gems"])
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

with open(STATE_FILE, "w") as f:
    json.dump(state, f, indent=2)

leaderboard = {
    "milestones":  MILESTONES,
    "generatedAt": today.isoformat(),
    "teams":       all_teams,
}

with open(OUT_FILE, "w") as f:
    json.dump(leaderboard, f, indent=2)

print(f"Wrote: {OUT_FILE}")
