"""Render monthly GitHub contributions using only Python's standard library."""
import datetime as dt
import html
import json
import math
import os
from pathlib import Path
import urllib.request

UTC = dt.timezone.utc
ROOT = Path(__file__).resolve().parents[1]


def months(now):
    first = now.year * 12 + now.month - 1
    for index in range(first - 11, first + 1):
        year, month = divmod(index, 12)
        start = dt.datetime(year, month + 1, 1, tzinfo=UTC)
        y, m = divmod(index + 1, 12)
        end = min(now, dt.datetime(y, m + 1, 1, tzinfo=UTC) - dt.timedelta(seconds=1))
        yield start, end


def aggregate(collection, allowed):
    result = {}
    for key, field, total in [('commits', 'commitContributionsByRepository', 'totalCommitContributions'), ('prs', 'pullRequestContributionsByRepository', 'totalPullRequestContributions')]:
        groups = collection[field]
        if sum(group['contributions']['totalCount'] for group in groups) != collection[total]:
            raise RuntimeError('Repository breakdown is incomplete; refusing to publish')
        result[key] = sum(group['contributions']['totalCount'] for group in groups if not group['repository']['isPrivate'] and group['repository']['nameWithOwner'].casefold() in allowed)
    return result


def fetch(now):
    approved = json.loads(os.environ['ALLOWED_REPOSITORIES'])
    if not isinstance(approved, list) or not approved or not all(isinstance(item, str) and '/' in item for item in approved):
        raise RuntimeError('ALLOWED_REPOSITORIES must be a nonempty JSON array of owner/repository names')
    allowed = {item.casefold() for item in approved}
    ranges = list(months(now))
    fields = []
    for i, (start, end) in enumerate(ranges):
        fields.append(f'm{i}: contributionsCollection(from: {json.dumps(start.isoformat())}, to: {json.dumps(end.isoformat())}) {{ totalCommitContributions totalPullRequestContributions restrictedContributionsCount commitContributionsByRepository(maxRepositories: 100) {{ repository {{ nameWithOwner isPrivate }} contributions {{ totalCount }} }} pullRequestContributionsByRepository(maxRepositories: 100) {{ repository {{ nameWithOwner isPrivate }} contributions {{ totalCount }} }} }}')
    query = 'query { user(login: "gnuser") { ' + ' '.join(fields) + ' } }'
    request = urllib.request.Request('https://api.github.com/graphql', data=json.dumps({'query': query}).encode(), headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Content-Type': 'application/json', 'User-Agent': 'gnuser-profile-chart'})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    if payload.get('errors'):
        raise RuntimeError('GitHub could not provide the complete contribution breakdown')
    user = payload['data']['user']
    return [{'month': start.strftime('%Y-%m'), **aggregate(user[f'm{i}'], allowed)} for i, (start, _) in enumerate(ranges)]


def render(rows, now):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="960" height="600" viewBox="0 0 960 600" role="img" aria-labelledby="title desc">', '<title id="title">Monthly commits and pull requests for gnuser</title>', '<desc id="desc">' + html.escape('; '.join(f"{r['month']}: {r['commits']} commits, {r['prs']} pull requests" for r in rows)) + '</desc>', '<style>text{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;fill:#c9d1d9}.muted{fill:#8b949e}.value{font-size:12px;font-weight:600}</style>', '<rect width="960" height="600" rx="18" fill="#0d1117"/>', '<rect x=".5" y=".5" width="959" height="599" rx="18" fill="none" stroke="#30363d"/>', '<text x="32" y="41" font-size="24" font-weight="700">Monthly activity</text>', '<text x="32" y="66" font-size="13" class="muted">@gnuser · Last 12 months · Current month in progress</text>']
    for key, title, color, top in [('commits', 'Commits', '#58a6ff', 113), ('prs', 'Pull requests opened', '#bc8cff', 343)]:
        values = [r[key] for r in rows]
        maximum = max(values + [1])
        step = max(1, math.ceil(maximum / 4))
        ceiling = step * 4
        baseline = top + 151
        parts.append(f'<text x="32" y="{top}" font-size="16" font-weight="600">{title}</text>')
        parts.append(f'<text x="928" y="{top}" text-anchor="end" font-size="14" class="muted">{sum(values):,} total</text>')
        for tick in range(5):
            y = baseline - tick * 30
            parts.append(f'<path d="M70 {y} H930" stroke="#21262d"/><text x="59" y="{y+4}" text-anchor="end" font-size="11" class="muted">{tick*step}</text>')
        for i, row in enumerate(rows):
            x = 106 + i * 71
            height = row[key] / ceiling * 120
            parts.append(f'<rect x="{x-20}" y="{baseline-height:.2f}" width="40" height="{height:.2f}" rx="4" fill="{color}" opacity="{0.65 if i == 11 else 1}"/>')
            parts.append(f'<text x="{x}" y="{baseline-height-7:.2f}" text-anchor="middle" class="value">{row[key]}</text>')
            parts.append(f'<text x="{x}" y="{baseline+22}" text-anchor="middle" font-size="11" class="muted">{row["month"]}</text>')
    parts.append(f'<text x="32" y="559" font-size="12" class="muted">GitHub contribution counts · Selected public projects · Months use UTC</text>')
    parts.append(f'<text x="32" y="580" font-size="12" class="muted">Updated {now.strftime("%Y-%m-%d %H:%M UTC")}</text></svg>')
    return '\n'.join(parts) + '\n'


if __name__ == '__main__':
    now = dt.datetime.now(UTC).replace(microsecond=0)
    rows = fetch(now)
    (ROOT / 'assets').mkdir(exist_ok=True)
    (ROOT / 'assets/monthly-activity.svg').write_text(render(rows, now))
    (ROOT / 'assets/monthly-activity.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps(rows))
