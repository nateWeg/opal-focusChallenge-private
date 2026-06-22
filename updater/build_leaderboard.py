import datetime
import json
import os
from google.cloud import firestore

PROJECT_ID = "opal-fa413"
GEMS = ["BisqueStoneNate", "Marjolaineeeee", "adelaidesky", "alorunc", "lilpit"]
BASELINE_SECONDS = 25200  # fixed 7h
MAX_SCREENTIME = 43200   # 12h cap — above this treated as missing/corrupted

STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")
OUT_FILE = os.path.join(os.path.dirname(__file__), "leaderboard-data.json")
HTML_FILE = os.path.join(os.path.dirname(__file__), "focusboard.html")

db = firestore.Client(project=PROJECT_ID)
today = datetime.date.today()
yesterday = today - datetime.timedelta(days=1)
two_days_ago = today - datetime.timedelta(days=2)

# load existing state
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        state = json.load(f)
else:
    state = {}

members = []

for gem in GEMS:
    print(f"Looking up '{gem}'...")
    users = db.collection("users").where(filter=firestore.FieldFilter("gemname_lowercase", "==", gem.lower())).get()
    if not users:
        print(f"  WARNING: not found, skipping")
        continue

    user_id = users[0].id
    gem_display = users[0].to_dict().get("gemname", gem)

    # new gem: joined_date = two days ago
    key = gem.lower()
    if key not in state:
        state[key] = {
            "user_id": user_id,
            "gem_display": gem_display,
            "joined_date": two_days_ago.isoformat(),
        }
        print(f"  New gem — joined_date set to {two_days_ago}")

    joined_date = datetime.date.fromisoformat(state[key]["joined_date"])
    print(f"  {gem_display} | joined: {joined_date} | user_id: {user_id}")

    # fetch all 7 weekday slots from Firestore
    days = []
    for slot in range(1, 8):
        doc = db.collection("realtimeScreentimeBenchmarks").document(f"{user_id}-{slot}").get()
        if not doc.exists:
            continue
        data = doc.to_dict()
        raw_date = data.get("date")
        screentime = data.get("screentime")

        if hasattr(raw_date, "date"):
            day = raw_date.date()
        elif isinstance(raw_date, datetime.datetime):
            day = raw_date.date()
        else:
            continue

        # only count days from joined_date through two_days_ago
        if day < joined_date or day > two_days_ago:
            continue

        # >12h treated as missing — no contribution, no penalty
        if not screentime or screentime <= 0 or screentime > MAX_SCREENTIME:
            hours_saved = 0
            missing = True
        else:
            hours_saved = max(0, BASELINE_SECONDS - screentime) / 3600
            missing = False

        days.append({
            "date": day,
            "screentime_h": round((screentime or 0) / 3600, 2),
            "hours_saved": round(hours_saved, 2),
            "missing": missing,
        })

    # build lookup and fill every date in window (missing days → "not read")
    data_by_date = {d["date"]: d for d in days}
    all_days = []
    cur = joined_date
    while cur <= two_days_ago:
        if cur in data_by_date:
            all_days.append(data_by_date[cur])
        else:
            all_days.append({
                "date": cur,
                "screentime_h": 0,
                "hours_saved": 0,
                "missing": True,
            })
        cur += datetime.timedelta(days=1)

    total_saved = round(sum(d["hours_saved"] for d in all_days), 2)
    latest_saved = all_days[-1]["hours_saved"] if all_days else None
    print(f"  {len(all_days)} days in window → {total_saved}h saved")

    members.append({
        "gem": gem_display,
        "joined_date": joined_date,
        "days": all_days,
        "total_saved": total_saved,
        "latest_saved": latest_saved,
    })

# save updated state
with open(STATE_FILE, "w") as f:
    json.dump(state, f, indent=2)

members.sort(key=lambda m: m["total_saved"], reverse=True)
team_total = round(sum(m["total_saved"] for m in members), 2)
goal = 100
pct = min(100, round(team_total / goal * 100))

# write leaderboard-data.json (website input — no user_ids)
leaderboard = {
    "teamName": "Opal Team",
    "totalHoursSaved": team_total,
    "goalHours": goal,
    "memberCount": len(members),
    "generatedAt": today.isoformat(),
    "members": [
        {
            "gemName": m["gem"],
            "hoursSaved": m["total_saved"],
            "latestHoursSaved": m["latest_saved"],
            "days": [
                {
                    "date": d["date"].isoformat(),
                    "screentimeH": d["screentime_h"],
                    "hoursSaved": d["hours_saved"],
                    "missing": d["missing"],
                }
                for d in m["days"]
            ],
        }
        for m in members
    ],
}
with open(OUT_FILE, "w") as f:
    json.dump(leaderboard, f, indent=2)

# build HTML preview
member_sections = ""
for i, m in enumerate(members):
    medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"

    rows = ""
    for d in m["days"]:
        if d["missing"]:
            saved_class, saved_str, screen_str = "zero", "0h", "not read"
        elif d["hours_saved"] > 0:
            saved_class = "pos"
            saved_str = f"+{d['hours_saved']}h"
            screen_str = f"{d['screentime_h']}h"
        elif d["hours_saved"] < 0:
            saved_class = "neg"
            saved_str = f"{d['hours_saved']}h"
            screen_str = f"{d['screentime_h']}h"
        else:
            saved_class, saved_str, screen_str = "zero", "0h", f"{d['screentime_h']}h"
        rows += f"""
        <tr>
          <td class="date">{d['date'].strftime('%b %-d')}</td>
          <td class="screen">{screen_str}</td>
          <td class="saved {saved_class}">{saved_str}</td>
        </tr>"""

    latest = m["latest_saved"]
    if latest is not None and not m["days"][-1]["missing"]:
        yest_str = f'<span class="yest">{("+" if latest > 0 else "")}{latest}h on {two_days_ago.strftime("%b %-d")}</span>'
    else:
        yest_str = f'<span class="no-data">not read on {two_days_ago.strftime("%b %-d")}</span>'

    member_sections += f"""
  <div class="member-card">
    <div class="member-header">
      <span class="medal">{medal}</span>
      <span class="member-gem">{m['gem']}</span>
      <span class="member-total">{m['total_saved']}h saved</span>
    </div>
    <div class="member-sub">{yest_str} · joined {m['joined_date'].strftime('%b %-d')}</div>
    <table class="day-table">
      <thead><tr><th>Date</th><th>Screen time</th><th>Hours saved</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>"""

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Opal FocusBoard</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f0f0f; color: #eee; padding: 32px 20px; }}
  .wrap {{ max-width: 600px; margin: 0 auto; }}
  .header {{ margin-bottom: 28px; }}
  .header h1 {{ color: #f5c842; font-size: 20px; letter-spacing: 0.08em; font-weight: 800; }}
  .header .tagline {{ color: #555; font-size: 13px; margin-top: 2px; }}
  .hero {{ background: #181818; border: 1px solid #2a2a2a; border-radius: 14px; padding: 24px; margin-bottom: 28px; }}
  .team-total {{ font-size: 52px; font-weight: 800; color: #f5c842; line-height: 1; }}
  .team-label {{ color: #666; font-size: 13px; margin: 4px 0 20px; }}
  .bar-track {{ background: #252525; border-radius: 99px; height: 10px; overflow: hidden; }}
  .bar-fill {{ background: linear-gradient(90deg, #d4a017, #f5c842); height: 100%; border-radius: 99px; width: {pct}%; }}
  .bar-meta {{ display: flex; justify-content: space-between; margin-top: 8px; font-size: 12px; color: #555; }}
  .member-card {{ background: #141414; border: 1px solid #222; border-radius: 12px; padding: 20px; margin-bottom: 16px; }}
  .member-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }}
  .medal {{ font-size: 18px; width: 28px; }}
  .member-gem {{ font-weight: 700; font-size: 17px; flex: 1; }}
  .member-total {{ color: #f5c842; font-weight: 700; font-size: 17px; }}
  .member-sub {{ font-size: 12px; margin-bottom: 14px; padding-left: 38px; color: #555; }}
  .yest {{ color: #4ade80; }}
  .no-data {{ color: #444; }}
  .day-table {{ width: 100%; border-collapse: collapse; }}
  .day-table th {{ text-align: left; color: #444; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; padding: 6px 0; border-bottom: 1px solid #222; }}
  .day-table td {{ padding: 9px 0; border-bottom: 1px solid #1c1c1c; font-size: 14px; }}
  .day-table tr:last-child td {{ border-bottom: none; }}
  .date {{ color: #888; width: 80px; }}
  .screen {{ color: #aaa; width: 100px; }}
  .saved.pos {{ color: #4ade80; font-weight: 600; }}
  .saved.neg {{ color: #f87171; font-weight: 600; }}
  .saved.zero {{ color: #444; }}
  .footer {{ margin-top: 24px; font-size: 11px; color: #333; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>🔒 OPAL FOCUSBOARD</h1>
    <div class="tagline">Save 100 hours · {len(members)} gems locked in</div>
  </div>
  <div class="hero">
    <div class="team-total">{team_total}h</div>
    <div class="team-label">saved by the team</div>
    <div class="bar-track"><div class="bar-fill"></div></div>
    <div class="bar-meta"><span>{pct}% of 100h goal</span><span>{round(goal - team_total, 1)}h to go</span></div>
  </div>
  {member_sections}
  <div class="footer">Baseline: 7h/day · Scores through {two_days_ago} · Generated {today}</div>
</div>
</body>
</html>"""

with open(HTML_FILE, "w") as f:
    f.write(html)

print(f"\nTeam: {team_total}h / {goal}h ({pct}%)")
print(f"Wrote: {OUT_FILE}")
print(f"Wrote: {HTML_FILE}")
