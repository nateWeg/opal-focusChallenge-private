"""Welcome-email automation for new leaderboard members.

Sends a personal note from nate@opalapp.com when a new gem first appears on the
leaderboard. Dry-run by default — set SEND_EMAILS=1 (env or .env) to send for real.
"""

import os
import smtplib
from email.message import EmailMessage

ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
FROM_ADDR = "nate@opal.so"
LEADERBOARD_URL = "https://updater-bice.vercel.app/"


def _load_env():
    """Return a dict of vars from .env, falling back to os.environ."""
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "SEND_EMAILS"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def _ordinal(n):
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _build_message(gem, team_name, place, leading_team):
    place_ord = _ordinal(place)
    subject = f"{team_name} is in {place_ord} place, stay locked-in to rise up"

    if team_name == leading_team:
        middle = (
            "Your school is currently in the lead — keep it up! Recruit more "
            "classmates to stay ahead and win rewards."
        )
    else:
        middle = (
            f"{leading_team} is in the lead. Your school is in {place_ord} place. "
            "By recruiting some classmates you can easily take the lead and win rewards."
        )

    body = (
        f"Hey {gem}, I am reaching out to confirm that you have been added to the "
        f"leaderboard, and are now competing for your school. {middle}\n\n"
        f"Click this link to view the leaderboard-> {LEADERBOARD_URL}\n\n"
        "Wishing you luck,\n"
        "Nate"
    )
    return subject, body


def send_welcome(to_email, gem, team_name, place, leading_team):
    """Send (or dry-run) the welcome email. Returns True only on a real send."""
    env = _load_env()
    subject, body = _build_message(gem, team_name, place, leading_team)
    live = str(env.get("SEND_EMAILS", "")).lower() in ("1", "true", "yes")

    if not live:
        print(f"  [dry-run] would email {gem} <{to_email}> — {team_name} in {_ordinal(place)}")
        return False

    user = env.get("GMAIL_USER")
    pw = env.get("GMAIL_APP_PASSWORD")
    if not user or not pw:
        print(f"  [email] SEND_EMAILS set but GMAIL_USER/GMAIL_APP_PASSWORD missing — skipping {gem}")
        return False

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = FROM_ADDR
        msg["To"] = to_email
        msg.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        print(f"  [email] sent welcome to {gem} <{to_email}>")
        return True
    except Exception as e:
        print(f"  [email] FAILED for {gem} <{to_email}>: {e}")
        return False
