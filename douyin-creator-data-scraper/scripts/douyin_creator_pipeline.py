#!/usr/bin/env python3
"""
Public Douyin Creator Center data scraper.

Exports account works data to local CSV, a JSON manifest, and a Markdown brief.
Remote upload is intentionally excluded from this public script; treat the CSV
as the source artifact for any downstream sync the user explicitly configures.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import re
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

UA = "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36"
CREATOR_HOME = "https://creator.douyin.com/creator/micro/home"
API_PREFIX = "https://creator.douyin.com/janus/douyin/creator/pc/work_list"
COUNT_NEW = 12
COUNT_OLD = 18
MAX_RETRIES = 3
SCRIPT_VERSION = "public-2026-06-16"


class PipelineError(RuntimeError):
    pass


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def resolve_workdir(value: Optional[str]) -> pathlib.Path:
    raw = value or os.environ.get("DOUYIN_SCRAPER_HOME") or "~/.cache/douyin-creator-data-scraper"
    path = pathlib.Path(raw).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_output_dir() -> pathlib.Path:
    return (pathlib.Path.cwd() / "outputs").resolve()


def safe_account_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name).strip("_")
    return cleaned or "douyin_account"


def num(value: Any) -> int:
    try:
        s = str(value if value is not None else "").replace(",", "").strip()
        if not s:
            return 0
        return int(float(s))
    except Exception:
        return 0


def fmt(n: Any) -> str:
    value = num(n)
    if value >= 100_000_000:
        return f"{value / 100_000_000:.2f}亿"
    if value >= 10_000:
        return f"{value / 10_000:.1f}万"
    return str(value)


def extract_account_from_message(message: str) -> Optional[str]:
    msg = (message or "").strip()
    patterns = [
        r"抓[一一下]?(.*?)的?数据",
        r"抓取?(.*?)数据",
        r"导出(.*?)的?(?:作品|视频|账号)?数据",
        r"(.*?)的?(?:账号|作品|视频)数据",
    ]
    for pattern in patterns:
        match = re.search(pattern, msg)
        if not match:
            continue
        account = re.sub(r"^(抖音|账号|一下|一下子)", "", match.group(1).strip()).strip()
        if account:
            return account
    return None


class Runtime:
    def __init__(self, workdir: pathlib.Path, output_dir: pathlib.Path, quiet: bool = False) -> None:
        self.workdir = workdir
        self.output_dir = output_dir
        self.quiet = quiet
        self.cookie_path = workdir / "douyin_cookie.json"
        self.state_path = workdir / "state.json"
        self.progress_log = workdir / "progress.log"
        self.raw_path: Optional[pathlib.Path] = None
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def log(self, stage: str, message: str, percent: Optional[int] = None) -> None:
        prefix = f"[{now()}]"
        pct = f" {percent}%" if percent is not None else ""
        line = f"{prefix}{pct} {stage}: {message}"
        if not self.quiet:
            print(line, flush=True)
        with self.progress_log.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def raw_file_for(self, account_name: str) -> pathlib.Path:
        self.raw_path = self.workdir / f"{safe_account_name(account_name)}_current_run.json"
        return self.raw_path


def read_json(path: pathlib.Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: pathlib.Path, data: Any, mode: Optional[int] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    if mode is not None:
        try:
            os.chmod(path, mode)
        except OSError:
            pass


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(cmd: List[str], timeout: int = 60, allow_fail: bool = False) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    if proc.returncode != 0 and not allow_fail:
        raise PipelineError(
            "Command failed: " + " ".join(cmd) + f"\nSTDOUT={proc.stdout[-1000:]}\nSTDERR={proc.stderr[-1000:]}"
        )
    return proc


def open_creator_home(runtime: Runtime, no_open_browser: bool) -> None:
    if no_open_browser:
        runtime.log("browser", "Skipping browser launch by request", 8)
        return
    if command_exists("agent-browser"):
        runtime.log("browser", "Opening Douyin Creator Center with agent-browser", 8)
        run_command(["agent-browser", "--headed", "open", CREATOR_HOME], timeout=45, allow_fail=True)
        return
    if sys.platform == "darwin" and command_exists("open"):
        runtime.log("browser", "agent-browser not found; opening Creator Center with system browser", 8)
        run_command(["open", CREATOR_HOME], timeout=15, allow_fail=True)
        return
    runtime.log("browser", "No browser launcher found; pass --chrome-debug-port for an existing debugging browser", 8)


def find_debug_port(explicit_port: Optional[str]) -> str:
    if explicit_port:
        return explicit_port
    env_port = os.environ.get("DOUYIN_CDP_PORT")
    if env_port:
        return env_port

    candidates: List[pathlib.Path] = []
    roots = [pathlib.Path("/var/folders"), pathlib.Path("/tmp"), pathlib.Path.home() / "Library" / "Application Support"]
    for root in roots:
        if not root.exists():
            continue
        try:
            candidates.extend(root.glob("**/agent-browser-chrome-*/DevToolsActivePort"))
            candidates.extend(root.glob("**/DevToolsActivePort"))
        except (OSError, RuntimeError):
            continue
    candidates = sorted(set(candidates), key=lambda item: item.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            port = path.read_text(encoding="utf-8").splitlines()[0].strip()
            if port:
                return port
        except Exception:
            continue
    return "9222"


def cdp_request(ws: Any, req_id: int, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"id": req_id, "method": method}
    if params:
        payload["params"] = params
    ws.send(json.dumps(payload))
    deadline = time.time() + 10
    while time.time() < deadline:
        message = json.loads(ws.recv())
        if message.get("id") == req_id:
            return message
    raise TimeoutError(method)


def get_cookie_via_cdp(runtime: Runtime, chrome_debug_port: Optional[str]) -> Dict[str, Any]:
    try:
        import websocket  # type: ignore
    except Exception as exc:
        raise PipelineError("Missing dependency websocket-client. Install with: python3 -m pip install websocket-client") from exc

    port = find_debug_port(chrome_debug_port)
    runtime.log("cookie", f"Connecting to local Chrome CDP port {port}", 12)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=8) as response:
            pages = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise PipelineError(
            "Could not connect to Chrome CDP. Open Douyin Creator Center in a debugging browser, "
            "or pass --chrome-debug-port."
        ) from exc

    page = next((p for p in pages if "creator.douyin.com" in p.get("url", "").lower()), None)
    if page is None:
        page = pages[0] if pages else None
    if page is None:
        raise PipelineError("No Chrome tab found through CDP")

    ws_url = page.get("webSocketDebuggerUrl") or f"ws://127.0.0.1:{port}/devtools/page/{page['id']}"
    ws = websocket.create_connection(ws_url, timeout=8, suppress_origin=True, origin=f"http://localhost:{port}")
    try:
        response = cdp_request(ws, 1, "Network.getAllCookies")
    finally:
        try:
            ws.close()
        except Exception:
            pass

    cookies = response.get("result", {}).get("cookies", [])
    dy_cookies = [
        cookie for cookie in cookies
        if any(domain in cookie.get("domain", "") for domain in ["douyin.com", "bytedance", "bytegoofy", "amemv.com"])
    ]
    cookie_str = "; ".join(f"{cookie.get('name')}={cookie.get('value')}" for cookie in dy_cookies if cookie.get("name"))
    payload = {
        "cookie": cookie_str,
        "cookie_count": len(dy_cookies),
        "has_sessionid": "sessionid=" in cookie_str,
        "has_ttwid": "ttwid=" in cookie_str,
        "saved_at": now(),
        "source": "Chrome CDP Network.getAllCookies",
        "note": "Sensitive local cookie cache. Do not commit or paste.",
    }
    write_json(runtime.cookie_path, payload, mode=0o600)
    runtime.log("cookie", f"Cookie cache saved locally: count={len(dy_cookies)} sessionid={payload['has_sessionid']}", 15)
    if not payload["has_sessionid"]:
        raise PipelineError("No sessionid detected. Log into Douyin Creator Center in the browser and retry.")
    return payload


def load_cookie(
    runtime: Runtime,
    skip_browser_cookie: bool,
    cookie_file: Optional[str],
    chrome_debug_port: Optional[str],
    no_open_browser: bool,
) -> Dict[str, Any]:
    if cookie_file:
        path = pathlib.Path(cookie_file).expanduser().resolve()
        payload = read_json(path, default={})
        if payload.get("cookie"):
            runtime.log("cookie", f"Using explicit cookie file: {path}", 10)
            return payload
        raise PipelineError(f"Cookie file does not contain a cookie field: {path}")
    if skip_browser_cookie:
        payload = read_json(runtime.cookie_path, default={})
        if payload.get("cookie"):
            runtime.log("cookie", "Reusing local cookie cache", 10)
            return payload
        raise PipelineError(f"No local cookie cache found at {runtime.cookie_path}")
    open_creator_home(runtime, no_open_browser=no_open_browser)
    return get_cookie_via_cdp(runtime, chrome_debug_port=chrome_debug_port)


def request_api(cookie: str, url: str, timeout: int = 25) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Cookie": cookie,
            "Referer": "https://creator.douyin.com/",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise PipelineError(f"HTTP {exc.code} from Douyin API: {body[:500]}") from exc
    except Exception as exc:
        raise PipelineError(f"Request failed: {exc}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"API returned non-JSON content: {body[:500]}") from exc


def init_or_resume_state(runtime: Runtime, account_name: str, resume: bool) -> Dict[str, Any]:
    existing = read_json(runtime.state_path, default=None)
    if existing and existing.get("account_name") == account_name and (resume or existing.get("fetched_count")):
        runtime.log("state", f"Resuming state: fetched={existing.get('fetched_count', 0)} cursor={existing.get('cursor')}", 5)
        return existing
    if existing and existing.get("account_name") != account_name:
        backup = runtime.workdir / f"state_backup_{safe_account_name(existing.get('account_name', 'unknown'))}_{int(time.time())}.json"
        write_json(backup, existing)
        runtime.log("state", f"Backed up previous account state to {backup.name}", 5)
    state = {
        "account_name": account_name,
        "interface_type": None,
        "total": 0,
        "fetched_count": 0,
        "cursor": 0,
        "max_cursor": 0,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "script_version": SCRIPT_VERSION,
    }
    write_json(runtime.state_path, state)
    runtime.log("state", f"Initialized state for {account_name}", 5)
    return state


def test_interface(runtime: Runtime, cookie_payload: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    cookie = cookie_payload.get("cookie") or ""
    if not cookie:
        raise PipelineError("Cookie payload is empty")
    url = (
        f"{API_PREFIX}?scene=star_atlas&device_platform=android&status=0&count={COUNT_NEW}"
        "&cookie_enabled=true&screen_width=1920&screen_height=1080&cursor=0"
    )
    data = request_api(cookie, url, timeout=25)
    items = data.get("items") or []
    aweme = data.get("aweme_list") or []
    total = num(data.get("total"))
    status_code = data.get("status_code")
    runtime.log("api", f"Interface test: status_code={status_code} total={total} items={len(items)} aweme_list={len(aweme)}", 20)
    if items:
        interface_type = "new"
    elif aweme:
        interface_type = "old"
    else:
        snippet = json.dumps(data, ensure_ascii=False)[:700]
        raise PipelineError(f"No works data returned. Login may be expired or the endpoint changed: {snippet}")
    state.update(
        {
            "interface_type": interface_type,
            "total": total,
            "cursor": state.get("max_cursor") or state.get("cursor") or 0,
            "max_cursor": state.get("max_cursor") or 0,
            "last_api_test_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    write_json(runtime.state_path, state)
    return state


def build_url(interface_type: str, cursor_value: Any) -> str:
    count = COUNT_OLD if interface_type == "old" else COUNT_NEW
    common = "scene=star_atlas&device_platform=android&status=0&cookie_enabled=true&screen_width=1920&screen_height=1080"
    if interface_type == "old":
        return f"{API_PREFIX}?max_cursor={cursor_value}&count={count}" if cursor_value else f"{API_PREFIX}?cursor=0&count={count}"
    return f"{API_PREFIX}?{common}&max_cursor={cursor_value}&count={count}" if cursor_value else f"{API_PREFIX}?{common}&cursor=0&count={count}"


def dedupe_key(video: Dict[str, Any]) -> Tuple[Any, ...]:
    video_id = video.get("作品ID") or video.get("aweme_id") or video.get("item_id") or video.get("id")
    if video_id:
        return ("id", str(video_id))
    return ("fallback", str(video.get("标题", ""))[:50], video.get("发布时间", ""), num(video.get("播放量")))


def normalize_item(item: Dict[str, Any], interface_type: str) -> Dict[str, Any]:
    if interface_type == "old":
        stats = item.get("statistics", {}) or {}
        return {
            "作品ID": item.get("aweme_id") or item.get("item_id") or item.get("id"),
            "标题": item.get("desc", ""),
            "发布时间": item.get("create_time", 0),
            "播放量": num(stats.get("play_count")),
            "点赞量": num(stats.get("digg_count")),
            "评论量": num(stats.get("comment_count")),
            "分享量": num(stats.get("share_count")),
            "收藏量": num(stats.get("collect_count")),
        }

    metrics = item.get("metrics", {}) or {}
    video_info = item.get("video_info", {}) or {}
    cover = item.get("cover", {}) or {}
    review = item.get("review", {}) or {}
    cover_urls = cover.get("url_list") if isinstance(cover, dict) else []
    duration_ms = num(video_info.get("duration"))
    return {
        "作品ID": item.get("aweme_id") or item.get("item_id") or item.get("id"),
        "标题": item.get("description", ""),
        "发布时间": item.get("create_time", 0),
        "用户ID": item.get("user_id", ""),
        "作品类型": item.get("type", ""),
        "可下载": item.get("downloadable", ""),
        "协作作品": item.get("collaborative", ""),
        "可见性": json.dumps(item.get("visibility", {}), ensure_ascii=False),
        "审核状态": review.get("status", ""),
        "视频时长毫秒": duration_ms,
        "视频时长秒": round(duration_ms / 1000, 3) if duration_ms else 0,
        "封面URL": cover_urls[0] if isinstance(cover_urls, list) and cover_urls else "",
        "播放量": num(metrics.get("view_count")),
        "点赞量": num(metrics.get("like_count")),
        "评论量": num(metrics.get("comment_count")),
        "分享量": num(metrics.get("share_count")),
        "收藏量": num(metrics.get("favorite_count") or metrics.get("collect_count")),
        "弹幕量": num(metrics.get("danmaku_count")),
        "下载量": num(metrics.get("download_count")),
        "不喜欢数": num(metrics.get("dislike_count")),
        "主页访问量": num(metrics.get("homepage_visit_count")),
        "新增关注数": num(metrics.get("subscribe_count")),
        "取关数": num(metrics.get("unsubscribe_count")),
        "封面曝光": num(metrics.get("cover_show")),
        "平均观看秒数": metrics.get("avg_view_second", ""),
        "平均观看占比": metrics.get("avg_view_proportion", ""),
        "2秒跳出率": metrics.get("bounce_rate_2s", ""),
        "5秒完播率": metrics.get("completion_rate_5s", ""),
        "完播率": metrics.get("completion_rate", ""),
        "粉丝播放占比": metrics.get("fan_view_proportion", ""),
        "点赞率": metrics.get("like_rate", ""),
        "评论率": metrics.get("comment_rate", ""),
        "分享率": metrics.get("share_rate", ""),
        "收藏率": metrics.get("favorite_rate", ""),
        "不喜欢率": metrics.get("dislike_rate", ""),
        "关注率": metrics.get("subscribe_rate", ""),
        "取关率": metrics.get("unsubscribe_rate", ""),
    }


def fetch_all(
    runtime: Runtime,
    cookie_payload: Dict[str, Any],
    state: Dict[str, Any],
    force_restart: bool,
    rate_limit_seconds: float,
) -> List[Dict[str, Any]]:
    account_name = state["account_name"]
    interface_type = state.get("interface_type")
    total = num(state.get("total"))
    if interface_type not in {"old", "new"}:
        raise PipelineError("State does not include a detected interface_type")

    raw_file = runtime.raw_file_for(account_name)
    cursor = state.get("max_cursor") or state.get("cursor") or 0
    if force_restart and raw_file.exists():
        raw_file.unlink()
        cursor = 0
        state.update({"cursor": 0, "max_cursor": 0, "fetched_count": 0})
        write_json(runtime.state_path, state)

    all_videos: List[Dict[str, Any]] = read_json(raw_file, default=[]) or []
    seen = {dedupe_key(video) for video in all_videos}
    runtime.log("fetch", f"Start/resume: existing={len(all_videos)} cursor={cursor} total={total or '?'}", 25)

    cookie = cookie_payload.get("cookie") or ""
    page_number = 0
    started = time.time()
    while True:
        url = build_url(interface_type, cursor)
        data: Optional[Dict[str, Any]] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                data = request_api(cookie, url, timeout=25)
                break
            except Exception as exc:
                if attempt >= MAX_RETRIES:
                    raise PipelineError(f"Request failed {MAX_RETRIES} times; progress has been saved: {exc}") from exc
                runtime.log("fetch", f"Request failed, retrying {attempt}/{MAX_RETRIES}")
                time.sleep(2)

        assert data is not None
        key = "aweme_list" if interface_type == "old" else "items"
        page_items = data.get(key) or []
        has_more = data.get("has_more", 0)
        if not page_items and data.get("status_code"):
            raise PipelineError(f"API status_code={data.get('status_code')}; cookie may be expired or endpoint changed")

        new_count = 0
        for item in page_items:
            video = normalize_item(item, interface_type)
            key_value = dedupe_key(video)
            if key_value not in seen:
                seen.add(key_value)
                all_videos.append(video)
                new_count += 1

        page_number += 1
        progress = min(75, 25 + int(len(all_videos) / max(total, 1) * 50)) if total else 40
        runtime.log("fetch", f"Page {page_number}: +{new_count}; total={len(all_videos)}/{total or '?'}; cursor={cursor}", progress)

        next_cursor = data.get("max_cursor")
        if next_cursor is None:
            next_cursor = num(cursor) + (COUNT_OLD if interface_type == "old" else COUNT_NEW)
        state.update(
            {
                "cursor": next_cursor,
                "max_cursor": next_cursor,
                "fetched_count": len(all_videos),
                "last_page_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        write_json(runtime.state_path, state)
        write_json(raw_file, all_videos)

        if total and len(all_videos) >= total:
            runtime.log("fetch", "Reached API total; stopping", 76)
            break
        if not has_more:
            runtime.log("fetch", "has_more=false; stopping", 76)
            break
        if str(next_cursor) == str(cursor) and new_count == 0:
            runtime.log("fetch", "Cursor did not advance and no new rows were added; stopping to avoid a loop", 76)
            break
        cursor = next_cursor
        time.sleep(max(rate_limit_seconds, 0))

    runtime.log("fetch", f"Completed {len(all_videos)} rows in {time.time() - started:.0f}s", 78)
    return all_videos


def observed_fields(rows: Iterable[Dict[str, Any]]) -> List[str]:
    preferred = [
        "作品ID", "标题", "发布日期", "发布时间", "用户ID", "作品类型", "可下载", "协作作品", "可见性", "审核状态",
        "视频时长毫秒", "视频时长秒", "封面URL", "播放量", "点赞量", "评论量", "分享量", "收藏量",
        "弹幕量", "下载量", "不喜欢数", "主页访问量", "新增关注数", "取关数", "封面曝光",
        "平均观看秒数", "平均观看占比", "2秒跳出率", "5秒完播率", "完播率", "粉丝播放占比",
        "点赞率", "评论率", "分享率", "收藏率", "不喜欢率", "关注率", "取关率",
    ]
    keys = set()
    rows_list = list(rows)
    for row in rows_list:
        keys.update(row.keys())
    fields = [field for field in preferred if field in keys]
    fields.extend(sorted(keys - set(fields)))
    return fields


def validate_rows(videos: List[Dict[str, Any]], total: int) -> Tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    if not videos:
        raise PipelineError("No data was scraped")
    filtered = [video for video in videos if num(video.get("播放量")) > 0]
    if not filtered:
        raise PipelineError("All rows have zero play count; cookie or endpoint may be wrong")
    if total:
        completeness = len(videos) / total * 100
        if completeness < 90:
            warnings.append(f"Completeness is {completeness:.1f}% against API total {total}; consider --resume or --force-restart.")
    for column in ["作品ID", "标题", "播放量"]:
        missing = sum(1 for video in filtered if not str(video.get(column, "")).strip() and num(video.get(column)) == 0)
        if missing / max(len(filtered), 1) > 0.5:
            warnings.append(f"Field {column} is missing for more than half of rows; endpoint shape may have changed.")
    return filtered, warnings


def write_csv(runtime: Runtime, account_name: str, videos: List[Dict[str, Any]]) -> Tuple[pathlib.Path, List[str]]:
    safe = safe_account_name(account_name)
    csv_path = runtime.output_dir / f"{safe}_douyin_creator_works_latest.csv"
    fields = observed_fields(videos)
    if "发布日期" not in fields:
        fields.insert(fields.index("发布时间") + 1 if "发布时间" in fields else 0, "发布日期")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for video in videos:
            row = dict(video)
            timestamp = num(row.get("发布时间"))
            row["发布日期"] = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d") if timestamp else ""
            writer.writerow(row)
    return csv_path, fields


def summarize_by_year(rows: List[Dict[str, Any]]) -> List[Tuple[str, int, int, int]]:
    grouped: Dict[str, List[int]] = {}
    for row in rows:
        timestamp = num(row.get("发布时间"))
        year = datetime.fromtimestamp(timestamp).strftime("%Y") if timestamp else ""
        if not year:
            continue
        grouped.setdefault(year, []).append(num(row.get("播放量")))
    summary = []
    for year, plays in grouped.items():
        total_play = sum(plays)
        summary.append((year, len(plays), total_play, total_play // max(len(plays), 1)))
    return sorted(summary, key=lambda item: item[0], reverse=True)


def write_brief(runtime: Runtime, account_name: str, videos: List[Dict[str, Any]], warnings: List[str]) -> pathlib.Path:
    safe = safe_account_name(account_name)
    path = runtime.output_dir / f"{safe}_douyin_creator_brief.md"
    total_play = sum(num(video.get("播放量")) for video in videos)
    plays = [num(video.get("播放量")) for video in videos]
    avg_play = total_play // max(len(videos), 1)
    median_play = int(statistics.median(plays)) if plays else 0
    top5 = sorted(videos, key=lambda item: num(item.get("播放量")), reverse=True)[:5]

    lines = [
        f"# {account_name} Douyin Creator Data Brief",
        "",
        f"- Generated at: {now()}",
        f"- Rows: {len(videos)}",
        f"- Total plays: {fmt(total_play)}",
        f"- Average plays: {fmt(avg_play)}",
        f"- Median plays: {fmt(median_play)}",
        "",
        "## Top Works",
        "",
    ]
    for index, row in enumerate(top5, 1):
        title = str(row.get("标题", "")).replace("\n", " ")[:120]
        lines.append(f"{index}. {title} | plays {fmt(row.get('播放量'))} | likes {fmt(row.get('点赞量'))}")

    yearly = summarize_by_year(videos)
    if yearly:
        lines.extend(["", "## Yearly Trend", ""])
        for year, count, total, avg in yearly[:8]:
            lines.append(f"- {year}: {count} works | total {fmt(total)} | avg {fmt(avg)}")

    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_manifest(
    runtime: Runtime,
    state: Dict[str, Any],
    csv_path: pathlib.Path,
    brief_path: pathlib.Path,
    fields: List[str],
    row_count: int,
    warnings: List[str],
    exported_json_path: Optional[pathlib.Path],
) -> pathlib.Path:
    account_name = state["account_name"]
    safe = safe_account_name(account_name)
    total = num(state.get("total"))
    manifest = {
        "script_version": SCRIPT_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "account_name": account_name,
        "interface_type": state.get("interface_type"),
        "api_total": total,
        "row_count": row_count,
        "completeness_percent": round(row_count / total * 100, 2) if total else None,
        "fields": fields,
        "artifacts": {
            "csv": str(csv_path),
            "brief": str(brief_path),
            "raw_json": str(exported_json_path) if exported_json_path else None,
        },
        "warnings": warnings,
        "notes": [
            "Cookie values are stored only in the configured local workdir.",
            "Remote upload is intentionally not part of the public default workflow.",
        ],
    }
    path = runtime.output_dir / f"{safe}_douyin_creator_manifest.json"
    write_json(path, manifest)
    return path


def export_raw_json(runtime: Runtime, account_name: str, videos: List[Dict[str, Any]], enabled: bool) -> Optional[pathlib.Path]:
    if not enabled:
        return None
    path = runtime.output_dir / f"{safe_account_name(account_name)}_douyin_creator_raw.json"
    write_json(path, videos)
    return path


def cleanup_after_success(runtime: Runtime, keep_state: bool) -> None:
    if keep_state:
        runtime.log("cleanup", "Keeping state files by request", 98)
        return
    for path in [runtime.state_path]:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
    runtime.log("cleanup", "Removed transient state; cookie cache retained for future authorized runs", 98)


def dry_run_checks(runtime: Runtime, account_name: str, skip_browser_cookie: bool, chrome_debug_port: Optional[str]) -> int:
    runtime.log("dry-run", f"Account: {account_name}", 5)
    runtime.log("dry-run", f"Python: {sys.version.split()[0]}", 10)
    runtime.log("dry-run", f"Workdir: {runtime.workdir}", 15)
    runtime.log("dry-run", f"Output dir: {runtime.output_dir}", 20)
    runtime.log("dry-run", f"agent-browser: {command_exists('agent-browser')}", 25)
    try:
        import websocket  # noqa: F401
        runtime.log("dry-run", "websocket-client: available", 30)
    except Exception:
        runtime.log("dry-run", "websocket-client: missing; install with python3 -m pip install websocket-client", 30)
    if runtime.cookie_path.exists():
        payload = read_json(runtime.cookie_path, default={})
        runtime.log(
            "dry-run",
            f"Cookie cache: exists count={payload.get('cookie_count')} sessionid={payload.get('has_sessionid')} saved_at={payload.get('saved_at')}",
            40,
        )
    elif skip_browser_cookie:
        runtime.log("dry-run", "Cookie cache missing and --skip-browser-cookie was requested", 40)
    else:
        runtime.log("dry-run", "Cookie cache missing; a normal run will open/read a browser session", 40)
    if chrome_debug_port:
        runtime.log("dry-run", f"Explicit CDP port: {chrome_debug_port}", 45)
    runtime.log("dry-run", "Preflight complete", 100)
    return 0


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Douyin Creator Center works data to local CSV/JSON/Markdown")
    parser.add_argument("--account", help="Douyin account/display name")
    parser.add_argument("--message", help="Original user request; used to infer account when --account is omitted")
    parser.add_argument("--workdir", help="Local state/cache directory. Defaults to DOUYIN_SCRAPER_HOME or ~/.cache/douyin-creator-data-scraper")
    parser.add_argument("--output-dir", help="Artifact directory. Defaults to ./outputs")
    parser.add_argument("--resume", action="store_true", help="Resume from saved state/current_run JSON")
    parser.add_argument("--force-restart", action="store_true", help="Ignore current_run JSON and scrape from the first page")
    parser.add_argument("--skip-browser-cookie", action="store_true", help="Reuse local cookie cache instead of opening/reading browser CDP")
    parser.add_argument("--cookie-file", help="Explicit JSON cookie file with a 'cookie' field")
    parser.add_argument("--chrome-debug-port", help="Existing Chrome DevTools Protocol port")
    parser.add_argument("--no-open-browser", action="store_true", help="Do not try to open a browser before CDP cookie extraction")
    parser.add_argument("--export-json", action="store_true", help="Write normalized raw JSON rows to the output directory")
    parser.add_argument("--keep-state", action="store_true", help="Keep state.json after success")
    parser.add_argument("--dry-run", action="store_true", help="Run local environment checks without scraping")
    parser.add_argument("--rate-limit-seconds", type=float, default=0.4, help="Delay between paginated API requests")
    parser.add_argument("--quiet", action="store_true", help="Only write logs to progress.log")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    account_name = args.account or extract_account_from_message(args.message or "")
    if not account_name:
        print("Provide --account, or pass --message like '抓一下xxx的数据'.", file=sys.stderr)
        return 2

    workdir = resolve_workdir(args.workdir)
    output_dir = pathlib.Path(args.output_dir).expanduser().resolve() if args.output_dir else default_output_dir()
    runtime = Runtime(workdir=workdir, output_dir=output_dir, quiet=args.quiet)
    runtime.log(
        "start",
        f"account={account_name} resume={args.resume} force_restart={args.force_restart} dry_run={args.dry_run}",
        0,
    )

    try:
        if args.dry_run:
            return dry_run_checks(runtime, account_name, args.skip_browser_cookie, args.chrome_debug_port)

        state = init_or_resume_state(runtime, account_name, resume=args.resume)
        cookie_payload = load_cookie(
            runtime,
            skip_browser_cookie=args.skip_browser_cookie,
            cookie_file=args.cookie_file,
            chrome_debug_port=args.chrome_debug_port,
            no_open_browser=args.no_open_browser,
        )
        state = test_interface(runtime, cookie_payload, state)
        videos = fetch_all(
            runtime,
            cookie_payload,
            state,
            force_restart=args.force_restart,
            rate_limit_seconds=args.rate_limit_seconds,
        )
        filtered, warnings = validate_rows(videos, total=num(state.get("total")))
        csv_path, fields = write_csv(runtime, account_name, filtered)
        brief_path = write_brief(runtime, account_name, filtered, warnings)
        raw_json_path = export_raw_json(runtime, account_name, filtered, enabled=args.export_json)
        manifest_path = write_manifest(
            runtime,
            state,
            csv_path=csv_path,
            brief_path=brief_path,
            fields=fields,
            row_count=len(filtered),
            warnings=warnings,
            exported_json_path=raw_json_path,
        )
        cleanup_after_success(runtime, keep_state=args.keep_state)
        runtime.log("done", f"CSV={csv_path}", 100)
        print("\nCompleted Douyin Creator export")
        print(f"CSV: {csv_path}")
        print(f"Brief: {brief_path}")
        print(f"Manifest: {manifest_path}")
        if raw_json_path:
            print(f"Raw JSON: {raw_json_path}")
        if warnings:
            print("Warnings:")
            for warning in warnings:
                print(f"- {warning}")
        return 0
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        runtime.log("interrupt", "Interrupted by user; rerun with --resume", None)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
