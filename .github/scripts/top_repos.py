"""Build a "Top Contributed Repos" SVG card from a user's commit history.

Runs inside GitHub Actions. Reads GITHUB_TOKEN and USERNAME from the
environment, counts the commits you authored in each public repo you own or
have contributed to, and writes the top N to an SVG file.

Usage: python top_repos.py OUTPUT.svg [LIMIT]
       python top_repos.py OUTPUT.svg [LIMIT] --sample   (render demo data, no network)
"""
import datetime as dt
import html
import json
import os
import sys
import urllib.request

API = "https://api.github.com/graphql"

USER_QUERY = "query($login:String!){ user(login:$login){ createdAt } }"
YEAR_QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) {
      commitContributionsByRepository(maxRepositories:100) {
        repository { nameWithOwner isPrivate primaryLanguage { name color } }
        contributions { totalCount }
      }
    }
  }
}
"""

# Matches github-readme-stats' "dark" theme so it sits well next to your other cards.
BG, BORDER, TITLE, TEXT, MUTED, BAR_BG = "#151515", "#e4e2e2", "#ffffff", "#c9d1d9", "#9f9f9f", "#2b2b2b"
ACCENT = "#1cadfb"


def http(url, token, data=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data else None,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def gql(query, variables, token):
    body = http(API, token, {"query": query, "variables": variables})
    if body.get("errors"):
        raise SystemExit(f"GitHub API error: {body['errors']}")
    return body["data"]


LANG_QUERY = "query($o:String!,$n:String!){ repository(owner:$o, name:$n){ primaryLanguage{ name color } } }"


def collect(login, token):
    """Rank public repos by the number of default-branch commits you authored.

    Candidates are your own public non-fork repos plus any other repo GitHub
    credits you with commits in. Counts come from each repo's contributor list,
    which also includes commits GitHub's contribution graph leaves out.
    """
    candidates = {}
    page = 1
    while True:
        batch = http(f"https://api.github.com/users/{login}/repos?per_page=100&page={page}&type=all", token)
        if not batch:
            break
        for r in batch:
            if not r["fork"] and not r["private"]:
                candidates[r["full_name"]] = r
        page += 1

    created = dt.datetime.fromisoformat(gql(USER_QUERY, {"login": login}, token)["user"]["createdAt"].replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    start = created
    while start < now:
        end = min(start + dt.timedelta(days=365), now)
        data = gql(YEAR_QUERY, {"login": login, "from": start.isoformat(), "to": end.isoformat()}, token)
        for item in data["user"]["contributionsCollection"]["commitContributionsByRepository"]:
            repo = item["repository"]
            if not repo["isPrivate"]:
                candidates.setdefault(repo["nameWithOwner"], None)
        start = end

    profile_repo = f"{login}/{login}".lower()
    totals = []
    for full_name in candidates:
        if full_name.lower() == profile_repo:
            continue
        try:
            people = http(f"https://api.github.com/repos/{full_name}/contributors?per_page=100", token)
        except Exception:
            continue  # empty or unavailable repo
        count = next((p["contributions"] for p in people or [] if p.get("login", "").lower() == login.lower()), 0)
        if count:
            owner, name = full_name.split("/", 1)
            lang = gql(LANG_QUERY, {"o": owner, "n": name}, token)["repository"]["primaryLanguage"]
            totals.append({"name": full_name, "count": count, "lang": lang})
    return sorted(totals, key=lambda r: r["count"], reverse=True)


def render(repos, login):
    width, row_h, top = 495, 34, 62
    height = top + max(len(repos), 1) * row_h + 14
    max_count = max((r["count"] for r in repos), default=1) or 1
    bar_x, bar_w = 238, 162

    rows = []
    if not repos:
        rows.append(f'<text x="25" y="{top + 16}" fill="{MUTED}" font-size="13">No public commits found yet.</text>')
    for i, r in enumerate(repos):
        y = top + i * row_h
        owner, _, name = r["name"].partition("/")
        label = name if owner.lower() == login.lower() else r["name"]
        if len(label) > 22:
            label = label[:21] + "…"
        color = (r["lang"] or {}).get("color") or MUTED
        lang = (r["lang"] or {}).get("name") or ""
        fill_w = max(4, round(bar_w * r["count"] / max_count))
        delay = 150 * i
        rows.append(f"""
  <g class="row" style="animation-delay:{delay}ms">
    <circle cx="31" cy="{y + 11}" r="5" fill="{html.escape(color)}"><title>{html.escape(lang)}</title></circle>
    <text x="44" y="{y + 15}" fill="{TEXT}" font-size="13" font-weight="600">{html.escape(label)}</text>
    <rect x="{bar_x}" y="{y + 5}" width="{bar_w}" height="11" rx="5.5" fill="{BAR_BG}"/>
    <rect class="bar" x="{bar_x}" y="{y + 5}" width="{fill_w}" height="11" rx="5.5" fill="{ACCENT}" style="animation-delay:{delay + 200}ms"/>
    <text x="{width - 25}" y="{y + 15}" fill="{MUTED}" font-size="12" text-anchor="end">{r["count"]} commits</text>
  </g>""")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Top contributed repositories">
  <style>
    text {{ font-family: 'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif; }}
    .row {{ opacity: 0; animation: fade 0.5s ease-out forwards; }}
    .bar {{ transform-box: fill-box; transform-origin: left; transform: scaleX(0); animation: grow 0.8s ease-out forwards; }}
    @keyframes fade {{ to {{ opacity: 1; }} }}
    @keyframes grow {{ to {{ transform: scaleX(1); }} }}
  </style>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="4.5" fill="{BG}" stroke="{BORDER}" stroke-opacity="0.2"/>
  <text x="25" y="35" fill="{TITLE}" font-size="18" font-weight="600">Top Contributed Repos</text>{''.join(rows)}
</svg>
"""


def main():
    out = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 5
    login = os.environ.get("USERNAME", "Gaurav-py-Ghosh")
    if "--sample" in sys.argv:
        repos = [
            {"name": f"{login}/Un-Dec-the-Study-Partner", "count": 48, "lang": {"name": "Dart", "color": "#00B4AB"}},
            {"name": f"{login}/T.i.e.s", "count": 31, "lang": {"name": "HTML", "color": "#e34c26"}},
            {"name": "someone-else/hackathon-project-with-a-long-name", "count": 17, "lang": None},
            {"name": f"{login}/emj_exp", "count": 9, "lang": {"name": "Dart", "color": "#00B4AB"}},
            {"name": f"{login}/Web", "count": 3, "lang": {"name": "HTML", "color": "#e34c26"}},
        ]
    else:
        repos = collect(login, os.environ["GITHUB_TOKEN"])
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(repos[:limit], login))
    print(f"Wrote {out} with {len(repos[:limit])} repos")


if __name__ == "__main__":
    main()
