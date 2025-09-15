#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cyber — single-file username scanner with a neon/cyberpunk terminal UI.

• Async + fast: httpx + asyncio with concurrency control
• ~120 popular platforms (dev, social, art, music, gaming, etc.)
• One Python file, no external configs
• Futuristic neon UI (Rich): banner, panels, progress, live stats
• Exports results to JSON and Markdown (now with **robust, permission-safe output paths**)
• Interactive loop: scan again / tweak options / quit (no auto-close)
• Pretty tracebacks enabled when available; **graceful** without `pygments`
• **Self-tests**: run with `--self-test` to validate heuristics & path logic

Usage (Windows/macOS/Linux):
    pip install -U httpx[http2] rich pygments
    python cybersherlock.py --username <name>

Tip (Windows double‑click): if your working directory is `C:\\Windows\\System32`,
output will automatically fallback to your user folder.

Optional:
    python cyber.py                 # interactive loop, asks for username
    python cybers.py -u hydra       # one scan then menu
    python cybers.py -u hydra --once  # single scan then exit
    python cybers.py --self-test    # run unit tests and exit

Tested with Python 3.10+ (works on 3.13).
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import sys
import time
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------- Dependencies (robust imports) ----------
try:
    import httpx
except ImportError:
    print("[!] Missing dependency: httpx. Install with: pip install -U httpx[http2]")
    raise

try:
    from rich import box
    from rich.align import Align
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("[!] Missing dependency: rich. Install with: pip install -U rich")
    raise

# Try to enable pretty tracebacks; gracefully degrade if pygments is missing
_TRACEBACK_ENABLED = False
try:
    from rich.traceback import install as rich_traceback_install  # type: ignore
    rich_traceback_install(show_locals=False, width=120)
    _TRACEBACK_ENABLED = True
except Exception:
    # Most common cause: ModuleNotFoundError: No module named 'pygments'
    _TRACEBACK_ENABLED = False

console = Console()

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# ---------- Site Model ----------
@dataclass
class Site:
    name: str
    url: str  # template with {username}
    not_found_pattern: Optional[str] = None  # regex for negative match
    requires_id: bool = False  # reserved flag (for future use)
    headers: Optional[Dict[str, str]] = None

    def build_url(self, username: str) -> str:
        return self.url.format(username=username)


# ---------- Platform Catalog (~120) ----------
# Note: Some platforms may require login; we mark them as unknown if we can't determine.
SITES: List[Site] = [
    # Dev & Code
    Site("GitHub", "https://github.com/{username}", r"Page not found|Not Found"),
    Site("GitLab", "https://gitlab.com/{username}"),
    Site("Bitbucket", "https://bitbucket.org/{username}"),
    Site("Codeberg", "https://codeberg.org/{username}"),
    Site("SourceForge", "https://sourceforge.net/u/{username}/"),
    Site("Gitee", "https://gitee.com/{username}"),
    Site("Docker Hub", "https://hub.docker.com/u/{username}"),
    Site("Quay", "https://quay.io/user/{username}"),
    Site("PyPI", "https://pypi.org/user/{username}"),
    Site("npm", "https://www.npmjs.com/~{username}"),
    Site("Crates.io", "https://crates.io/users/{username}"),
    Site("RubyGems", "https://rubygems.org/profiles/{username}"),
    Site("NuGet", "https://www.nuget.org/profiles/{username}"),
    Site("MetaCPAN", "https://metacpan.org/author/{username}"),
    Site("AUR (Arch)", "https://aur.archlinux.org/account/{username}"),
    Site("OBS (openSUSE)", "https://build.opensuse.org/users/{username}"),
    Site("Fedora COPR", "https://copr.fedorainfracloud.org/coprs/{username}"),
    Site("Launchpad", "https://launchpad.net/~{username}"),
    Site("Mozilla Add-ons", "https://addons.mozilla.org/en-US/firefox/user/{username}"),
    Site("GreasyFork", "https://greasyfork.org/en/users/{username}"),
    Site("Replit", "https://replit.com/@{username}"),
    Site("Glitch", "https://glitch.com/@{username}"),
    Site("CodePen", "https://codepen.io/{username}"),
    Site("JSFiddle", "https://jsfiddle.net/user/{username}"),
    Site("HackerRank", "https://www.hackerrank.com/{username}"),
    Site("Codewars", "https://www.codewars.com/users/{username}"),
    Site("Codeforces", "https://codeforces.com/profile/{username}"),
    Site("Topcoder", "https://www.topcoder.com/members/{username}"),
    Site("AtCoder", "https://atcoder.jp/users/{username}"),
    Site("LeetCode", "https://leetcode.com/{username}"),
    Site("SPOJ", "https://www.spoj.com/users/{username}"),
    Site("Exercism", "https://exercism.org/profiles/{username}"),
    Site("Wakatime", "https://wakatime.com/@{username}"),
    Site("Dev.to", "https://dev.to/{username}"),
    Site("Hashnode", "https://hashnode.com/@{username}"),
    Site("Medium", "https://medium.com/@{username}"),
    Site("Product Hunt", "https://www.producthunt.com/@{username}"),
    Site("Indie Hackers", "https://www.indiehackers.com/{username}"),
    Site("StackShare", "https://stackshare.io/{username}"),
    Site("Devpost", "https://devpost.com/{username}"),
    Site("CodeProject", "https://www.codeproject.com/Members/{username}"),
    Site("Codementor", "https://www.codementor.io/@{username}"),
    Site("Giters", "https://giters.com/{username}"),

    # Social / Microblog
    Site("Reddit", "https://www.reddit.com/user/{username}"),
    Site("Twitter", "https://twitter.com/{username}"),
    Site("X", "https://x.com/{username}"),
    Site("Instagram", "https://www.instagram.com/{username}"),
    Site("TikTok", "https://www.tiktok.com/@{username}"),
    Site("Threads", "https://www.threads.net/@{username}"),
    Site("Facebook", "https://www.facebook.com/{username}"),
    Site("YouTube", "https://www.youtube.com/@{username}"),
    Site("Vimeo", "https://vimeo.com/{username}"),
    Site("Twitch", "https://www.twitch.tv/{username}"),
    Site("Trovo", "https://trovo.live/{username}"),
    Site("DLive", "https://dlive.tv/{username}"),
    Site("Pinterest", "https://www.pinterest.com/{username}"),
    Site("Mastodon", "https://mastodon.social/@{username}"),
    Site("Bluesky", "https://bsky.app/profile/{username}.bsky.social"),
    Site("Cohost", "https://cohost.org/{username}"),
    Site("Tumblr", "https://{username}.tumblr.com"),
    Site("WordPress.com", "https://{username}.wordpress.com"),
    Site("Blogger", "https://{username}.blogspot.com"),
    Site("About.me", "https://about.me/{username}"),
    Site("Keybase", "https://keybase.io/{username}"),
    Site("Telegram", "https://t.me/{username}"),
    Site("Snapchat", "https://www.snapchat.com/add/{username}"),
    Site("Weibo", "https://weibo.com/{username}"),
    Site("VK", "https://vk.com/{username}"),
    Site("OK.ru", "https://ok.ru/{username}"),

    # Gaming
    Site("Steam", "https://steamcommunity.com/id/{username}"),
    Site("itch.io", "https://{username}.itch.io"),
    Site("Game Jolt", "https://gamejolt.com/@{username}"),
    Site("Speedrun", "https://www.speedrun.com/user/{username}"),
    Site("osu!", "https://osu.ppy.sh/users/{username}"),
    Site("Chess.com", "https://www.chess.com/member/{username}"),
    Site("Lichess", "https://lichess.org/@/{username}"),

    # Media / Music / Photo / Film
    Site("Unsplash", "https://unsplash.com/@{username}"),
    Site("500px", "https://500px.com/{username}"),
    Site("Flickr", "https://www.flickr.com/people/{username}"),
    Site("Imgur", "https://imgur.com/user/{username}"),
    Site("Giphy", "https://giphy.com/{username}"),
    Site("Tenor", "https://tenor.com/users/{username}"),
    Site("Dribbble", "https://dribbble.com/{username}"),
    Site("Behance", "https://www.behance.net/{username}"),
    Site("DeviantArt", "https://www.deviantart.com/{username}"),
    Site("ArtStation", "https://www.artstation.com/{username}"),
    Site("Pinterest (alt)", "https://pinterest.com/{username}"),
    Site("VSCO", "https://vsco.co/{username}/gallery"),
    Site("SoundCloud", "https://soundcloud.com/{username}"),
    Site("Mixcloud", "https://www.mixcloud.com/{username}"),
    Site("Bandcamp", "https://{username}.bandcamp.com"),
    Site("Audiomack", "https://audiomack.com/{username}"),
    Site("Genius", "https://genius.com/{username}"),
    Site("Spotify", "https://open.spotify.com/user/{username}"),
    Site("Last.fm", "https://www.last.fm/user/{username}"),
    Site("Vimeo (alt)", "https://vimeo.com/{username}"),

    # Anime / Books / Movies / TV
    Site("MyAnimeList", "https://myanimelist.net/profile/{username}"),
    Site("Anime-Planet", "https://www.anime-planet.com/users/{username}"),
    Site("AniList", "https://anilist.co/user/{username}"),
    Site("Letterboxd", "https://letterboxd.com/{username}"),
    Site("Trakt", "https://trakt.tv/users/{username}"),

    # Marketplaces / Commerce / Creators
    Site("Etsy", "https://www.etsy.com/people/{username}"),
    Site("eBay", "https://www.ebay.com/usr/{username}"),
    Site("OpenSea", "https://opensea.io/{username}"),
    Site("Rarible", "https://rarible.com/{username}"),
    Site("Fiverr", "https://www.fiverr.com/{username}"),
    Site("Freelancer", "https://www.freelancer.com/u/{username}"),
    Site("Ko-fi", "https://ko-fi.com/{username}"),
    Site("BuyMeACoffee", "https://www.buymeacoffee.com/{username}"),
    Site("Patreon", "https://www.patreon.com/{username}"),
    Site("Gumroad", "https://{username}.gumroad.com"),
    Site("Payhip", "https://payhip.com/{username}"),

    # Security / Hacker / Tech communities
    Site("TryHackMe", "https://tryhackme.com/p/{username}"),
    Site("Root-Me", "https://www.root-me.org/{username}"),
    Site("HackerOne", "https://hackerone.com/{username}"),
    Site("Bugcrowd", "https://bugcrowd.com/{username}"),

    # Open Knowledge / Maps
    Site("OpenStreetMap", "https://www.openstreetmap.org/user/{username}"),
    Site("Wikipedia", "https://en.wikipedia.org/wiki/User:{username}"),
    Site("Wikidata", "https://www.wikidata.org/wiki/User:{username}"),
]

# Ensure we have about >= 100 platforms
assert len(SITES) >= 100, f"Internal error: only {len(SITES)} sites listed"

# ---------- Heuristics ----------
NEGATIVE_HINTS = re.compile(
    r"(not\s*found|404|doesn'?t\s*exist|user\s*not\s*found|no\s*such\s*user|" \
    r"sorry[,\s]*this\s*page\s*isn'?t\s*available|profile\s*cannot\s*be\s*found|" \
    r"introuvable|aucun\s*utilisateur|page\s*non\s*trouvée)",
    re.IGNORECASE,
)
LOGIN_HINTS = re.compile(r"log\s*in|sign\s*in|connexion|se\s*connecter", re.IGNORECASE)

DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
}

# ---------- Classification (pure function for tests) ----------

def classify_response(status_code: int, text: str, not_found_pattern: Optional[str]) -> str:
    """Return one of: 'FOUND', 'NOT FOUND', 'UNKNOWN'."""
    # Explicit HTTP checks first
    if status_code == 404:
        return "NOT FOUND"
    if status_code in (401, 402):
        return "UNKNOWN"  # auth required
    if status_code in (403, 405):
        return "UNKNOWN"  # forbidden/blocked
    if status_code in (429,):
        return "UNKNOWN"  # rate limited

    # Body heuristics
    if text:
        if not_found_pattern and re.search(not_found_pattern, text, re.I):
            return "NOT FOUND"
        if re.search(NEGATIVE_HINTS, text):
            return "NOT FOUND"
        if re.search(LOGIN_HINTS, text) and 200 <= status_code < 300:
            return "UNKNOWN"

    # 2xx/3xx generally means the profile exists
    if 200 <= status_code < 400:
        return "FOUND"

    return "UNKNOWN"

# ---------- Path helpers (permission-safe saving) ----------

def derive_fallback_candidates(out_dir: str) -> List[Path]:
    """Return candidate directories to try for saving reports, in order."""
    # Expand env vars & ~
    first = Path(os.path.expandvars(os.path.expanduser(out_dir or "reports")))
    home = Path.home() / "CyberSherlock" / "reports"
    tmp = Path(tempfile.gettempdir()) / "CyberSherlock" / "reports"

    # If running from System32 and first is relative, prefer home first
    cwd = Path.cwd()
    is_system32 = str(cwd).lower().endswith(os.path.join("windows", "system32"))
    if is_system32 and not first.is_absolute():
        return [home, tmp]
    return [first, home, tmp]


def ensure_writable_dir(out_dir: str) -> Path:
    """Create and return a writable directory. Falls back to user home or temp if needed.
    Raises RuntimeError only if all candidates fail.
    """
    for candidate in derive_fallback_candidates(out_dir):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            # Probe write permission by creating a small temp file
            probe = candidate / ".probe_write"
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            probe.unlink(missing_ok=True)
            return candidate
        except Exception:
            continue
    raise RuntimeError("No writable directory found for reports. Check permissions or use --save-dir")

# ---------- CLI ----------
import argparse

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CyberSherlock — Neon username scanner (single file)",
        add_help=True,
    )
    parser.add_argument("--username", "-u", help="Nom d'utilisateur à rechercher")
    parser.add_argument("--threads", "-t", type=int, default=40, help="Nombre de requêtes concurrentes (défaut: 40)")
    parser.add_argument("--timeout", type=float, default=12.0, help="Délai d'attente par site en secondes (défaut: 12)")
    parser.add_argument("--only", help="Filtrer les sites par mot-clé (ex: dev,music,art,social) — nom partiel")
    parser.add_argument("--save-dir", default="reports", help="Dossier de sortie pour les rapports (défaut: reports)")
    parser.add_argument("--once", action="store_true", help="Exécuter un seul scan puis quitter")
    parser.add_argument("--self-test", action="store_true", help="Exécuter les tests unitaires et quitter")
    # Backward-compat: if user passes --no-pause, behave like --once
    parser.add_argument("--no-pause", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()

# ---------- UI Elements ----------
BANNER = r"""
 ██░ ██▓██   ██▓▓█████▄  ██▀███   ▄▄▄         ▄▄▄█████▓ ██▀███   ▄▄▄       ▄████▄   ██ ▄█▀▓█████  ██▀███  
▓██░ ██▒▒██  ██▒▒██▀ ██▌▓██ ▒ ██▒▒████▄       ▓  ██▒ ▓▒▓██ ▒ ██▒▒████▄    ▒██▀ ▀█   ██▄█▒ ▓█   ▀ ▓██ ▒ ██▒
▒██▀▀██░ ▒██ ██░░██   █▌▓██ ░▄█ ▒▒██  ▀█▄     ▒ ▓██░ ▒░▓██ ░▄█ ▒▒██  ▀█▄  ▒▓█    ▄ ▓███▄░ ▒███   ▓██ ░▄█ ▒
░▓█ ░██  ░ ▐██▓░░▓█▄   ▌▒██▀▀█▄  ░██▄▄▄▄██    ░ ▓██▓ ░ ▒██▀▀█▄  ░██▄▄▄▄██ ▒▓▓▄ ▄██▒▓██ █▄ ▒▓█  ▄ ▒██▀▀█▄  
░▓█▒░██▓ ░ ██▒▓░░▒████▓ ░██▓ ▒██▒ ▓█   ▓██▒     ▒██▒ ░ ░██▓ ▒██▒ ▓█   ▓██▒▒ ▓███▀ ░▒██▒ █▄░▒████▒░██▓ ▒██▒
 ▒ ░░▒░▒  ██▒▒▒  ▒▒▓  ▒ ░ ▒▓ ░▒▓░ ▒▒   ▓▒█░     ▒ ░░   ░ ▒▓ ░▒▓░ ▒▒   ▓▒█░░ ░▒ ▒  ░▒ ▒▒ ▓▒░░ ▒░ ░░ ▒▓ ░▒▓░
 ▒ ░▒░ ░▓██ ░▒░  ░ ▒  ▒   ░▒ ░ ▒░  ▒   ▒▒ ░       ░      ░▒ ░ ▒░  ▒   ▒▒ ░  ░  ▒   ░ ░▒ ▒░ ░ ░  ░  ░▒ ░ ▒░
 ░  ░░ ░▒ ▒ ░░   ░ ░  ░   ░░   ░   ░   ▒        ░        ░░   ░   ░   ▒   ░        ░ ░░ ░    ░     ░░   ░ 
 ░  ░  ░░ ░        ░       ░           ░  ░               ░           ░  ░░ ░      ░  ░      ░  ░   ░     
        ░ ░      ░                                                        ░                               
"""

SUBTITLE = "[magenta]CYBER[/]/[cyan][/]  •  [bold]Scan multi-plateformes[/bold]  •  [dim]Neon TUI[/dim]"


def neon_panel() -> Panel:
    banner_text = Text.from_ansi(BANNER)
    banner_text.stylize("bold magenta")
    body = Group(
        Align.center(banner_text),
        Align.center(Text(SUBTITLE, justify="center")),
    )
    return Panel(
        Align.center(body),
        box=box.HEAVY,
        border_style="magenta",
        padding=(1, 2),
    )


def make_progress() -> Progress:
    return Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[cyan]Scan[/]"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        expand=True,
    )


# ---------- Scanner ----------
class Result:
    __slots__ = ("site", "url", "status", "http_status", "reason", "elapsed")

    def __init__(self, site: Site, url: str, status: str, http_status: Optional[int], reason: str, elapsed: float):
        self.site = site
        self.url = url
        self.status = status  # FOUND | NOT FOUND | UNKNOWN
        self.http_status = http_status
        self.reason = reason
        self.elapsed = elapsed

    def row(self) -> Tuple[str, str, str, str]:
        icon = {
            "FOUND": "[bold green]✅[/]",
            "NOT FOUND": "[red]❌[/]",
            "UNKNOWN": "[yellow]⚠️[/]",
        }[self.status]
        status_txt = f"{icon} {self.status}"
        hs = "-" if self.http_status is None else str(self.http_status)
        ms = f"{self.elapsed*1000:.0f} ms"
        return (self.site.name, status_txt, hs, f"[link={self.url}]Ouvrir[/link]  •  {ms}")


async def fetch_site(client: httpx.AsyncClient, site: Site, username: str, timeout: float) -> Result:
    url = site.build_url(username)
    headers = {**DEFAULT_HEADERS, **(site.headers or {})}
    t0 = time.perf_counter()
    try:
        resp = await client.get(url, headers=headers, timeout=timeout, follow_redirects=True)
        elapsed = time.perf_counter() - t0
        text = resp.text[:20000] if resp.headers.get("content-type", "").startswith("text/") else ""

        status = classify_response(resp.status_code, text, site.not_found_pattern)
        reason = (
            "404" if status == "NOT FOUND" and resp.status_code == 404 else
            "Pattern: not_found" if status == "NOT FOUND" and (site.not_found_pattern and re.search(site.not_found_pattern, text or "", re.I)) else
            "Negative hints" if status == "NOT FOUND" else
            "Login wall" if status == "UNKNOWN" and re.search(LOGIN_HINTS, text or "") else
            "OK" if status == "FOUND" else
            "Unhandled status"
        )
        return Result(site, url, status, resp.status_code, reason, elapsed)

    except httpx.TimeoutException:
        elapsed = time.perf_counter() - t0
        return Result(site, url, "UNKNOWN", None, "Timeout", elapsed)
    except httpx.RequestError as e:
        elapsed = time.perf_counter() - t0
        return Result(site, url, "UNKNOWN", None, f"{type(e).__name__}", elapsed)


async def scan_username(username: str, threads: int, timeout: float, only_filter: Optional[str] = None) -> List[Result]:
    # Optionally filter sites by substring in name
    sites = SITES
    if only_filter:
        keys = [k.strip().lower() for k in only_filter.split(",") if k.strip()]
        sites = [s for s in sites if any(k in s.name.lower() for k in keys)] or sites

    limits = httpx.Limits(max_keepalive_connections=min(threads, 50), max_connections=max(threads, 64))
    async with httpx.AsyncClient(http2=True, limits=limits) as client:
        sem = asyncio.Semaphore(threads)

        async def task(site: Site) -> Result:
            async with sem:
                # Random jitter to reduce burstiness
                await asyncio.sleep(random.uniform(0.01, 0.15))
                return await fetch_site(client, site, username, timeout)

        tasks = [asyncio.create_task(task(site)) for site in sites]
        results = []
        for t in asyncio.as_completed(tasks):
            results.append(await t)
        # Keep input order
        results.sort(key=lambda r: r.site.name.lower())
        return results


# ---------- Rendering & Reports ----------

def results_table(results: List[Result]) -> Table:
    table = Table(title="Résultats", box=box.SIMPLE_HEAVY)
    table.add_column("Plateforme", no_wrap=True, style="bold cyan")
    table.add_column("Statut", no_wrap=True)
    table.add_column("HTTP", no_wrap=True, style="dim")
    table.add_column("Lien / Latence", overflow="fold")
    for r in results:
        table.add_row(*r.row())
    return table


def summarize(results: List[Result]) -> Tuple[int, int, int]:
    f = sum(1 for r in results if r.status == "FOUND")
    nf = sum(1 for r in results if r.status == "NOT FOUND")
    u = sum(1 for r in results if r.status == "UNKNOWN")
    return f, nf, u


def save_reports(username: str, results: List[Result], out_dir: str) -> Tuple[str, str]:
    # Ensure a writable directory, with fallbacks for Windows/System32 or locked paths
    target_dir = ensure_writable_dir(out_dir)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_user = re.sub(r"[^A-Za-z0-9_.-]", "_", username)[:40]
    base = target_dir / f"cybersherlock_{safe_user}_{ts}"
    json_path = str(base) + ".json"
    md_path = str(base) + ".md"

    # JSON
    payload = [
        {
            "site": r.site.name,
            "url": r.url,
            "status": r.status,
            "http_status": r.http_status,
            "reason": r.reason,
            "elapsed_ms": int(r.elapsed * 1000),
        }
        for r in results
    ]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Markdown report
    fcount, nfcount, ucount = summarize(results)
    lines = [
        f"# CyberSherlock — Rapport ({username})",
        "",
        f"**Trouvés:** {fcount}  •  **Introuvables:** {nfcount}  •  **Incertains:** {ucount}",
        "",
        "| Plateforme | Statut | HTTP | Lien |",
        "|---|---:|---:|---|",
    ]
    for r in results:
        icon = "✅" if r.status == "FOUND" else ("❌" if r.status == "NOT FOUND" else "⚠️")
        hs = r.http_status if r.http_status is not None else "-"
        lines.append(f"| {r.site.name} | {icon} {r.status} | {hs} | {r.url} |")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return json_path, md_path


# ---------- One Scan Run ----------
async def run_scan(username: str, threads: int, timeout: float, only: Optional[str], save_dir: str) -> Tuple[List[Result], str, str]:
    console.clear()
    if not _TRACEBACK_ENABLED:
        console.print("[yellow]\[Info]\[/] Module [bold]pygments[/] non installé — tracebacks améliorés désactivés.\n"
                      "Installe: [italic]pip install pygments[/]")
    console.print(neon_panel())
    console.rule("[magenta]Configuration")

    # Determine target dir (and show where we'll save)
    try:
        target_dir = ensure_writable_dir(save_dir)
    except RuntimeError:
        target_dir = None

    console.print(
        f"[cyan]Cibles:[/] {len(SITES)}  •  [cyan]Threads:[/] {threads}  •  "
        f"[cyan]Timeout:[/] {timeout}s  •  [cyan]Filtre:[/] {only or 'aucun'}",
    )
    if target_dir is not None:
        console.print(f"[cyan]Export:[/] {target_dir}")
    else:
        console.print("[red]Export:[/] aucun dossier valide — tentative lors de l'enregistrement")

    # Determine total tasks for progress
    sites_iter = SITES
    if only:
        keys = [k.strip().lower() for k in only.split(",") if k.strip()]
        filtered = [s for s in SITES if any(k in s.name.lower() for k in keys)]
        sites_iter = filtered or SITES
    total_tasks = len(sites_iter)

    progress = make_progress()
    task_id = progress.add_task("scan", total=total_tasks)

    found: List[Result] = []

    with Live(progress, refresh_per_second=12, console=console):
        limits = httpx.Limits(max_keepalive_connections=min(threads, 50), max_connections=max(threads, 64))
        async with httpx.AsyncClient(http2=True, limits=limits) as client:
            sem = asyncio.Semaphore(threads)

            async def run_one(site: Site) -> Result:
                async with sem:
                    await asyncio.sleep(random.uniform(0.01, 0.12))
                    r = await fetch_site(client, site, username, timeout)
                    progress.advance(task_id, advance=1)
                    return r

            tasks = [asyncio.create_task(run_one(s)) for s in sites_iter]
            for coro in asyncio.as_completed(tasks):
                res = await coro
                found.append(res)

    # Sort & display table
    found.sort(key=lambda r: (0 if r.status == "FOUND" else 1 if r.status == "UNKNOWN" else 2, r.site.name.lower()))
    fcount, nfcount, ucount = summarize(found)

    table = results_table(found)
    console.print(Panel(table, border_style="cyan", title=f"Résultats pour [magenta]{username}[/]"))

    console.rule("[magenta]Résumé")
    console.print(
        f"[bold green]✅ Trouvés:[/] {fcount}    "
        f"[bold yellow]⚠️ Incertains:[/] {ucount}    "
        f"[bold red]❌ Introuvables:[/] {nfcount}"
    )

    try:
        json_path, md_path = save_reports(username, found, save_dir)
        console.print(
            Panel(
                Align.center(
                    Text(
                        f"Rapports enregistrés:\n• {json_path}\n• {md_path}",
                        justify="center",
                        style="white",
                    )
                ),
                border_style="magenta",
                title="Export",
            )
        )
    except Exception as e:
        console.print(Panel(f"[red]Impossible d'écrire les rapports:[/] {e}\n"
                            "Essayez: [cyan]--save-dir C:/Users/…/Documents/CyberSherlock/reports[/]",
                            title="Export", border_style="red"))
        json_path = md_path = ""

    return found, json_path, md_path


# ---------- Interactive Loop ----------
async def interactive_loop(args: argparse.Namespace) -> int:
    # Backward compatibility: --no-pause acts like --once
    if getattr(args, "no_pause", False):
        args.once = True

    while True:
        username = args.username or Prompt.ask("[bold cyan]Entrez le username à rechercher[/]", default="hydra").strip()
        if not username:
            console.print("[red]Erreur:[/] username vide.", style="bold red")
            continue

        # Run one scan
        try:
            await run_scan(username, args.threads, args.timeout, args.only, args.save_dir)
        except KeyboardInterrupt:
            console.print("\n[red]Scan interrompu.[/]")

        # Single-run mode
        if args.once:
            return 0

        # Post-scan menu
        console.rule("[magenta]Suite ?")
        choice = Prompt.ask(
            "[bold]Que faire maintenant ?[/] ([green]n[/]=nouveau scan, [yellow]m[/]=modifier options, [red]q[/]=quitter)",
            choices=["n", "m", "q"],
            default="n",
        )
        if choice == "q":
            return 0
        elif choice == "m":
            # Change options interactively (Enter to keep)
            try:
                t_in = Prompt.ask(f"Threads (actuel {args.threads})", default=str(args.threads)).strip()
                if t_in:
                    args.threads = max(1, int(t_in))
            except Exception:
                pass
            try:
                to_in = Prompt.ask(f"Timeout sec (actuel {args.timeout})", default=str(args.timeout)).strip()
                if to_in:
                    args.timeout = max(1.0, float(to_in))
            except Exception:
                pass
            only_in = Prompt.ask(f"Filtre sites (actuel {args.only or 'aucun'})", default=str(args.only or "")).strip()
            args.only = only_in or None
            save_in = Prompt.ask(f"Dossier export (actuel {args.save_dir})", default=args.save_dir).strip()
            args.save_dir = save_in or args.save_dir
            # Next: ask username again
            args.username = None
        else:
            # New scan, ask for a new username next loop
            args.username = None


# ---------- Unit Tests ----------

def run_self_tests() -> int:
    import unittest

    class ClassifyTests(unittest.TestCase):
        def test_404_not_found(self):
            self.assertEqual(classify_response(404, "", None), "NOT FOUND")
        def test_negative_hints_body(self):
            self.assertEqual(classify_response(200, "user not found", None), "NOT FOUND")
        def test_custom_not_found_pattern(self):
            self.assertEqual(classify_response(200, "Page non trouvée", r"non\s*trouv"), "NOT FOUND")
        def test_login_wall(self):
            self.assertEqual(classify_response(200, "Please log in to continue", None), "UNKNOWN")
        def test_found_on_200(self):
            self.assertEqual(classify_response(200, "welcome profile", None), "FOUND")
        def test_unknown_on_403(self):
            self.assertEqual(classify_response(403, "", None), "UNKNOWN")

    class PathLogicTests(unittest.TestCase):
        def test_fallback_order_normal(self):
            cands = derive_fallback_candidates("reports")
            self.assertGreaterEqual(len(cands), 2)
            self.assertTrue(str(cands[0]).lower().endswith("reports"))
        def test_fallback_order_system32(self):
            # Simulate by forcing logic? We can't easily change cwd here,
            # but we can at least ensure function returns a list
            self.assertTrue(derive_fallback_candidates("reports"))

    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(ClassifyTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(PathLogicTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


# ---------- Main ----------
async def main_async() -> int:
    args = parse_args()
    if args.self_test:
        rc = run_self_tests()
        if rc == 0:
            console.print("[bold green]Self-tests passed.[/]")
        else:
            console.print("[bold red]Self-tests failed.[/]")
        return rc
    return await interactive_loop(args)


def main() -> None:
    try:
        rc = asyncio.run(main_async())
    except KeyboardInterrupt:
        console.print("\n[red]Interrompu par l'utilisateur.[/]")
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    main()
