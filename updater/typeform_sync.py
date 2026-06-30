import difflib
import json
import os
import urllib.request
import urllib.error

FORM_ID = "Ph5rIiZ7"
BASE_URL = "https://api.typeform.com"

TEAMS_FILE      = os.path.join(os.path.dirname(__file__), "teams.json")
STATE_FILE      = os.path.join(os.path.dirname(__file__), "state.json")
EMAILS_FILE     = os.path.join(os.path.dirname(__file__), "emails.json")
PROCESSED_FILE  = os.path.join(os.path.dirname(__file__), "processed_responses.json")
ENV_FILE        = os.path.join(os.path.dirname(__file__), ".env")


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_env_token():
    """Read TYPEFORM_TOKEN from .env or environment."""
    token = os.environ.get("TYPEFORM_TOKEN")
    if token:
        return token
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("TYPEFORM_TOKEN="):
                    return line.split("=", 1)[1].strip()
    return None


def _api_get(path, token, params=None):
    url = BASE_URL + path
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def _normalize_school(name):
    n = name.lower().strip()
    for prefix in ["the ", "university of ", "univ. of ", "univ of "]:
        if n.startswith(prefix):
            n = n[len(prefix):]
    return n.rstrip(", the")


def _find_matching_team(school_input, teams, threshold=0.82):
    norm = _normalize_school(school_input)
    best, best_score = None, 0.0
    for t in teams:
        score = difflib.SequenceMatcher(None, norm, _normalize_school(t["teamName"])).ratio()
        if score > best_score:
            best_score, best = score, t
    return best if best_score >= threshold else None


def _extract_text(answer):
    """Pull a string value from a Typeform answer object regardless of type."""
    atype = answer.get("type")
    if atype == "text":
        return answer.get("text", "").strip()
    if atype == "email":
        return answer.get("email", "").strip()
    if atype == "choice":
        return answer.get("choice", {}).get("label", "").strip()
    if atype == "choices":
        labels = answer.get("choices", {}).get("labels", [])
        return ", ".join(labels)
    return ""


def _discover_fields(token):
    """Return (gem_field_ids, school_field_id, email_field_id).
    gem_field_ids is a list because the form has two gem questions
    (one for existing Opal users, one for new users)."""
    form = _api_get(f"/forms/{FORM_ID}", token)

    def _walk(fields):
        for f in fields:
            yield f
            # group / statement fields can nest
            for sub in f.get("properties", {}).get("fields", []):
                yield sub

    gem_ids   = []
    school_id = None
    email_id  = None

    for field in _walk(form.get("fields", [])):
        label = field.get("title", "").lower()
        fid   = field.get("id")
        ftype = field.get("type", "")
        if "gem" in label and ftype in ("short_text", "long_text"):
            gem_ids.append(fid)
        elif ("email" in label or ftype == "email") and ftype in ("short_text", "long_text", "email"):
            if email_id is None:
                email_id = fid
        elif any(kw in label for kw in ("school", "university", "college", "institution")) and ftype in ("short_text", "long_text"):
            if school_id is None:
                school_id = fid

    return gem_ids, school_id, email_id


# ── main entry point ──────────────────────────────────────────────────────────

def run():
    token = _load_env_token()
    if not token:
        print("Typeform sync: no TYPEFORM_TOKEN found in .env — skipping.")
        return

    # Load existing data
    with open(TEAMS_FILE) as f:
        teams = json.load(f)

    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)

    emails = {}
    if os.path.exists(EMAILS_FILE):
        with open(EMAILS_FILE) as f:
            emails = json.load(f)

    processed = {}
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE) as f:
            processed = json.load(f)

    # Build a set of all gems already in teams.json
    existing_gems = {
        gem.lower()
        for team in teams
        for gem in team.get("gems", [])
    }

    # Discover field IDs
    try:
        gem_ids, school_id, email_id = _discover_fields(token)
    except urllib.error.HTTPError as e:
        print(f"Typeform sync: API error fetching form definition ({e.code}) — skipping.")
        return

    if not gem_ids:
        print("Typeform sync: could not find gem field(s) in form — skipping.")
        return
    if not school_id:
        print("Typeform sync: could not find school field in form — skipping.")
        return
    if not email_id:
        print("Typeform sync: could not find email field in form — skipping.")
        return

    # Fetch all responses (paginate)
    all_responses = []
    params = {"page_size": "1000", "sort": "submitted_at,asc"}
    while True:
        try:
            page = _api_get(f"/forms/{FORM_ID}/responses", token, params)
        except urllib.error.HTTPError as e:
            print(f"Typeform sync: API error fetching responses ({e.code}) — skipping.")
            return
        items = page.get("items", [])
        all_responses.extend(items)
        if len(items) < int(params["page_size"]):
            break
        # cursor-based pagination: use last response token
        last_token = items[-1].get("token")
        if not last_token:
            break
        params["before"] = last_token

    added = 0
    for response in all_responses:
        rid = response.get("response_id") or response.get("token")
        if not rid or rid in processed:
            continue

        answers_by_field = {a["field"]["id"]: a for a in response.get("answers", [])}

        # Extract gem (try all gem fields, take first non-empty)
        gem_raw = ""
        for gid in gem_ids:
            if gid in answers_by_field:
                val = _extract_text(answers_by_field[gid])
                if val:
                    gem_raw = val
                    break

        school_raw = _extract_text(answers_by_field[school_id]) if school_id in answers_by_field else ""
        email_raw  = _extract_text(answers_by_field[email_id])  if email_id  in answers_by_field else ""

        # Always mark processed so we don't re-evaluate
        processed[rid] = True

        if not gem_raw or not school_raw:
            continue

        gem_key = gem_raw.lower()

        # Dedup: skip if gem already on a team
        if gem_key in existing_gems or gem_key in state:
            if email_raw and gem_key not in emails:
                emails[gem_key] = email_raw
            continue

        # Find or create team
        team = _find_matching_team(school_raw, teams)
        if team is None:
            team = {"teamName": school_raw.strip(), "gems": []}
            teams.append(team)
            print(f"Typeform sync: new school '{team['teamName']}'")

        team["gems"].append(gem_raw)
        existing_gems.add(gem_key)
        if email_raw:
            emails[gem_key] = email_raw

        print(f"Typeform sync: added '{gem_raw}' → {team['teamName']}")
        added += 1

    # Persist
    with open(TEAMS_FILE, "w") as f:
        json.dump(teams, f, indent=2)
    with open(EMAILS_FILE, "w") as f:
        json.dump(emails, f, indent=2)
    with open(PROCESSED_FILE, "w") as f:
        json.dump(processed, f, indent=2)

    print(f"Typeform sync: {added} new gem(s) added. {len(processed)} total responses processed.")
