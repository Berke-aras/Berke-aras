#!/usr/bin/env python3
"""Render assets/stats.svg from the GitHub API.

The public github-readme-stats / activity-graph / streak-stats deployments all
went offline, which made those cards render as broken images. This script draws
the same numbers ourselves and commits the result, so the profile only ever
depends on files in this repository.

Run with a token in GITHUB_TOKEN (or STATS_TOKEN). A classic/fine-grained token
with `repo` scope also counts private repositories; the default Actions token
sees public ones only.

    python scripts/gen_stats.py                 # fetch live, write assets/stats.svg
    python scripts/gen_stats.py --data x.json   # render from a saved snapshot
    python scripts/gen_stats.py --dump x.json   # save the fetched snapshot
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import random
import sys
import urllib.error
import urllib.request

USER = os.environ.get("STATS_USER", "Berke-aras")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "stats.svg")
API = "https://api.github.com"

# palette shared with assets/hero.svg
INK = "#14100D"
ASPHALT = "#17130F"
PAPER = "#EFE4CC"
MUTED = "#6B5A45"
VERMILION = "#E04A22"
TEAL = "#2E9E8F"
ACID = "#C3D24A"
PURPLE = "#6E52A6"
OCHRE = "#C98A3A"
GREY = "#8E7C63"

LANG_COLOURS = [VERMILION, TEAL, ACID, PURPLE, OCHRE]
MAX_LANGS = 5


# --------------------------------------------------------------------------- data


def get(path: str, token: str):
    req = urllib.request.Request(
        API + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "profile-stats",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch(token: str) -> dict:
    user = get(f"/users/{USER}", token)

    repos, page = [], 1
    while True:
        # /user/repos includes private repos when the token allows it
        try:
            batch = get(f"/user/repos?per_page=100&affiliation=owner&page={page}", token)
        except urllib.error.HTTPError:
            batch = get(f"/users/{USER}/repos?per_page=100&type=owner&page={page}", token)
        repos += batch
        if len(batch) < 100:
            break
        page += 1

    owned = [r for r in repos if not r.get("fork") and r["owner"]["login"].lower() == USER.lower()]

    langs: dict[str, int] = {}
    for r in owned:
        try:
            for name, size in get(f"/repos/{r['full_name']}/languages", token).items():
                langs[name] = langs.get(name, 0) + size
        except urllib.error.HTTPError:
            # fall back to the repo's primary language when /languages is denied
            if r.get("language"):
                langs[r["language"]] = langs.get(r["language"], 0) + 1

    return {
        "repos": len(owned),
        "stars": sum(r.get("stargazers_count", 0) for r in owned),
        "followers": user.get("followers", 0),
        "since": user["created_at"][:4],
        "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
        "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
    }


def top_languages(langs: dict[str, int]):
    """Top languages as (name, share, colour), with the tail folded into 'Other'."""
    total = sum(langs.values()) or 1
    items = list(langs.items())[:MAX_LANGS]
    out = [(n, v / total, LANG_COLOURS[i]) for i, (n, v) in enumerate(items)]
    rest = total - sum(v for _, v in items)
    if rest > 0:
        out.append(("Other", rest / total, GREY))
    return out


# ------------------------------------------------------------------------ drawing


def torn(x0, y0, x1, y1, jitter=3.2, step=17):
    """Rough, hand-torn rectangle outline — matches the banner's collage edges."""
    pts = []

    def walk(ax, ay, bx, by):
        d = math.hypot(bx - ax, by - ay)
        n = max(2, int(d // step))
        for i in range(n):
            t = i / n
            ux, uy = (by - ay) / d, -(bx - ax) / d
            k = random.uniform(-jitter, jitter)
            pts.append((ax + (bx - ax) * t + ux * k, ay + (by - ay) * t + uy * k))

    walk(x0, y0, x1, y0)
    walk(x1, y0, x1, y1)
    walk(x1, y1, x0, y1)
    walk(x0, y1, x0, y0)
    return "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"


def splatter(cx, cy, n, spread, rmax, colour):
    out = []
    for _ in range(n):
        a = random.uniform(0, math.tau)
        d = abs(random.gauss(0, spread))
        r = random.uniform(0.7, rmax) * (1 - min(d / (spread * 3), 0.8))
        if r < 0.5:
            continue
        out.append(
            f'<circle cx="{cx + math.cos(a) * d:.1f}" cy="{cy + math.sin(a) * d * 0.6:.1f}" '
            f'r="{r:.1f}" fill="{colour}" opacity="{random.uniform(0.15, 0.7):.2f}"/>'
        )
    return "\n      ".join(out)


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tile(x, y, value, label):
    return (
        f'<text x="{x}" y="{y}" fill="{INK}" font-size="42" font-weight="900" '
        f'font-family="\'Arial Black\', \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif">{esc(value)}</text>'
        f'<text x="{x}" y="{y + 22}" fill="{MUTED}" font-size="12" font-weight="700" letter-spacing="3" '
        f'font-family="\'Segoe UI\', Roboto, Helvetica, Arial, sans-serif">{esc(label)}</text>'
    )


def render(d: dict) -> str:
    random.seed(3)
    langs = top_languages(d["languages"])

    # stacked language bar
    bar_x, bar_w, bar_y, bar_h = 520, 600, 96, 26
    segments, cursor = [], bar_x
    for i, (_, share, colour) in enumerate(langs):
        w = bar_w - (cursor - bar_x) if i == len(langs) - 1 else bar_w * share
        segments.append(f'<rect x="{cursor:.1f}" y="{bar_y}" width="{max(w, 0):.1f}" height="{bar_h}" fill="{colour}"/>')
        cursor += w

    # legend, two columns
    legend = []
    for i, (name, share, colour) in enumerate(langs):
        col, row = divmod(i, 3)
        lx = 520 + col * 300
        ly = 158 + row * 30
        legend.append(
            f'<rect x="{lx}" y="{ly - 11}" width="13" height="13" fill="{colour}"/>'
            f'<text x="{lx + 22}" y="{ly}" fill="{INK}" font-size="15" font-weight="700" '
            f'font-family="\'Segoe UI\', Roboto, Helvetica, Arial, sans-serif">{esc(name)}</text>'
            f'<text x="{lx + 268}" y="{ly}" fill="{MUTED}" font-size="14" text-anchor="end" '
            f'font-family="ui-monospace, Menlo, Consolas, monospace">{share * 100:.1f}%</text>'
        )

    card = torn(36, 26, 1164, 274, jitter=3.4)
    tiles = "".join(
        [
            tile(84, 164, str(d["repos"]), "REPOSITORIES"),
            tile(292, 164, str(d["followers"]), "FOLLOWERS"),
            tile(84, 238, str(len(d["languages"])), "LANGUAGES"),
            tile(292, 238, str(d["since"]), "SINCE"),
        ]
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="300" viewBox="0 0 1200 300" role="img" aria-label="GitHub stats for {esc(USER)}">
  <title>GitHub stats — {esc(USER)}</title>
  <desc>{d['repos']} repositories, {d['followers']} followers, {len(d['languages'])} languages. Updated {d['updated']}.</desc>
  <defs>
    <linearGradient id="sground" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#171310"/>
      <stop offset="55%" stop-color="#1E1813"/>
      <stop offset="100%" stop-color="#12100E"/>
    </linearGradient>
    <pattern id="shalf" width="10" height="10" patternUnits="userSpaceOnUse">
      <circle cx="2.5" cy="2.5" r="1.9" fill="#3a2e22"/>
      <circle cx="7.5" cy="7.5" r="1.1" fill="#312619"/>
    </pattern>
    <pattern id="sdots" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(-18)">
      <circle cx="1.8" cy="1.8" r="1.5" fill="#0d0a08"/>
    </pattern>
    <clipPath id="sclip"><rect width="1200" height="300"/></clipPath>
  </defs>

  <g clip-path="url(#sclip)">
    <rect width="1200" height="300" fill="url(#sground)"/>
    <rect width="1200" height="300" fill="url(#shalf)" opacity=".5"/>
    <g>
      {splatter(600, 150, 70, 260, 2.6, VERMILION)}
    </g>

    <g transform="rotate(-0.7 600 150)">
      <path d="{card}" fill="{PAPER}"/>
      <path d="{card}" fill="url(#sdots)" opacity=".09"/>

      <text x="84" y="92" fill="{INK}" font-size="30" font-weight="900" letter-spacing="1"
            font-family="'Arial Black', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif">STATS</text>
      <rect x="86" y="104" width="104" height="7" fill="{VERMILION}"/>
      <rect x="196" y="104" width="34" height="7" fill="{TEAL}"/>
      {tiles}

      <text x="520" y="76" fill="{MUTED}" font-size="13" font-weight="700" letter-spacing="4"
            font-family="'Segoe UI', Roboto, Helvetica, Arial, sans-serif">TOP LANGUAGES</text>
      {"".join(segments)}
      {"".join(legend)}

      <text x="1128" y="252" fill="{MUTED}" font-size="11" text-anchor="end" letter-spacing="1"
            font-family="ui-monospace, Menlo, Consolas, monospace">updated {d['updated']}</text>
    </g>

    <g opacity=".72">
      <rect x="18" y="16" width="84" height="24" fill="{PAPER}" transform="rotate(-22 60 28)"/>
      <rect x="1104" y="262" width="88" height="24" fill="{PAPER}" transform="rotate(-17 1148 274)"/>
    </g>

    <g stroke="{VERMILION}" stroke-width="4" fill="none">
      <path d="M12 12 L12 40 M12 12 L40 12"/>
      <path d="M1188 288 L1188 260 M1188 288 L1160 288"/>
    </g>
    <rect x="1" y="1" width="1198" height="298" fill="none" stroke="{VERMILION}" stroke-opacity=".35" stroke-width="2"/>
  </g>
</svg>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="render from this JSON snapshot instead of calling the API")
    ap.add_argument("--dump", help="write the fetched snapshot here")
    args = ap.parse_args()

    if args.data:
        data = json.load(open(args.data))
    else:
        token = os.environ.get("STATS_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            print("no STATS_TOKEN/GITHUB_TOKEN in the environment", file=sys.stderr)
            return 1
        data = fetch(token)
        if args.dump:
            json.dump(data, open(args.dump, "w"), indent=2)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        fh.write(render(data))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
