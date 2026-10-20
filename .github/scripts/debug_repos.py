"""Print what GitHub reports about the user's contributions (diagnostics only)."""
import datetime as dt, json, os, urllib.request

TOKEN, LOGIN = os.environ["GITHUB_TOKEN"], os.environ["USERNAME"]

def call(url, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json",
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r), r.headers

created = call("https://api.github.com/graphql", {"query": "query($l:String!){user(login:$l){createdAt}}", "variables": {"l": LOGIN}})[0]["data"]["user"]["createdAt"]
start = dt.datetime.fromisoformat(created.replace("Z", "+00:00")); now = dt.datetime.now(dt.timezone.utc)
Q = """query($l:String!,$f:DateTime!,$t:DateTime!){user(login:$l){contributionsCollection(from:$f,to:$t){
 totalCommitContributions restrictedContributionsCount
 commitContributionsByRepository(maxRepositories:100){repository{nameWithOwner isPrivate isFork} contributions{totalCount}}
 pullRequestContributionsByRepository(maxRepositories:100){repository{nameWithOwner} contributions{totalCount}}}}}"""
commits, prs = {}, {}
while start < now:
    end = min(start + dt.timedelta(days=365), now)
    c = call("https://api.github.com/graphql", {"query": Q, "variables": {"l": LOGIN, "f": start.isoformat(), "t": end.isoformat()}})[0]["data"]["user"]["contributionsCollection"]
    print(f"{start.date()}..{end.date()}: commits={c['totalCommitContributions']} private/hidden={c['restrictedContributionsCount']}")
    for i in c["commitContributionsByRepository"]:
        r = i["repository"]; k = r["nameWithOwner"]
        commits[k] = commits.get(k, 0) + i["contributions"]["totalCount"]
    for i in c["pullRequestContributionsByRepository"]:
        k = i["repository"]["nameWithOwner"]; prs[k] = prs.get(k, 0) + i["contributions"]["totalCount"]
    start = end

print("\n== Commits credited by GitHub, per repo ==")
for k, v in sorted(commits.items(), key=lambda x: -x[1]): print(f"{v:5}  {k}")
print("\n== PRs opened, per repo ==")
for k, v in sorted(prs.items(), key=lambda x: -x[1]): print(f"{v:5}  {k}")

print("\n== Your public repos (owner) with commit count by you on default branch ==")
repos, page = [], 1
while True:
    batch = call(f"https://api.github.com/users/{LOGIN}/repos?per_page=100&page={page}&type=all")[0]
    if not batch: break
    repos += batch; page += 1
for r in repos:
    try:
        _, h = call(f"https://api.github.com/repos/{r['full_name']}/commits?author={LOGIN}&per_page=1")
        link = h.get("Link", ""); n = int(link.split("page=")[-1].split(">")[0]) if 'rel="last"' in link else None
        if n is None:
            n = len(call(f"https://api.github.com/repos/{r['full_name']}/commits?author={LOGIN}&per_page=1")[0])
        allc = call(f"https://api.github.com/repos/{r['full_name']}/contributors?per_page=100&anon=1")[0]
        mine = next((c["contributions"] for c in allc if c.get("login", "").lower() == LOGIN.lower()), 0)
        total = sum(c["contributions"] for c in allc)
    except Exception as e:
        n, mine, total = "?", "?", "?"
    print(f"{r['full_name']:50} fork={r['fork']!s:5} by_author={n!s:4} contributor_stat={mine!s:4} all_commits={total!s:5} pushed={r['pushed_at'][:10]}")
