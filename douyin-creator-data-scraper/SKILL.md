---
name: douyin-creator-data-scraper
description: Export Douyin Creator Center works/video metrics to local CSV, JSON, and Markdown summaries through an authenticated browser session. Use when the user asks to scrape, export, resume, validate, analyze, or prepare Douyin creator account/video performance data, including traffic diagnosis from an existing CSV.
---

# Douyin Creator Data Scraper

## Overview

Use this skill to export works data from Douyin Creator Center for accounts the user controls or is authorized to access. The public workflow is local-first: scrape to CSV/JSON/Markdown, keep cookies out of chat and Git, and leave any Feishu/Notion/S3/GitHub upload as an explicit downstream step outside the core scraper.

The bundled script keeps the original Hermes workflow's core behavior: browser-based login reuse, CDP cookie extraction, interface version detection, resume, de-duplication, field validation, and a concise report.

## Public Workflow Rules

- Default to local files. Do not upload or overwrite remote knowledge bases unless the user explicitly asks and provides their own integration.
- Do not print, paste, commit, or summarize cookies, `sessionid`, `ttwid`, file tokens, private wiki tokens, or other secrets.
- Store scraper state under `~/.cache/douyin-creator-data-scraper` by default, or use `--workdir` / `DOUYIN_SCRAPER_HOME` when the user wants an isolated project directory.
- Write final artifacts to `./outputs` by default, or use `--output-dir`.
- Preserve user files. Do not delete old Desktop files or remote attachments as part of the public workflow.
- Treat Douyin endpoint fields as empirical. If a field is absent in the API response, mark it missing instead of inventing support.

## Quick Start

Run a local export:

```bash
python3 scripts/douyin_creator_pipeline.py --account "账号名"
```

Resume an interrupted scrape:

```bash
python3 scripts/douyin_creator_pipeline.py --account "账号名" --resume
```

Reuse a cached cookie without reopening the browser:

```bash
python3 scripts/douyin_creator_pipeline.py --account "账号名" --skip-browser-cookie
```

Use project-local state and output directories:

```bash
python3 scripts/douyin_creator_pipeline.py \
  --account "账号名" \
  --workdir ./work/douyin-state \
  --output-dir ./outputs/douyin
```

Preflight without scraping:

```bash
python3 scripts/douyin_creator_pipeline.py --account "账号名" --dry-run
```

## Dependencies

- Python 3.9+
- `websocket-client` for CDP cookie extraction:

```bash
python3 -m pip install websocket-client
```

- One of these browser options:
  - `agent-browser` installed and logged into Douyin Creator Center through the opened browser, or
  - an existing Chrome instance started with remote debugging and `--chrome-debug-port <port>`.

## Workflow

1. Identify the task.
   - For "抓取/导出/更新数据", run the bundled scraper.
   - For "分析流量/低迷月份/账号诊断", use an existing CSV when available; read `references/account-traffic-diagnosis.md` for the diagnostic checklist.
2. Confirm authorization. Only proceed for accounts the user controls or has permission to access.
3. Run a preflight when the environment is new:

```bash
python3 scripts/douyin_creator_pipeline.py --account "账号名" --dry-run
```

4. Open or reuse the browser session. If login is required, ask the user to finish login in the visible browser, then rerun the command.
5. Let the script detect the Creator Center API shape:
   - `items[].metrics` means the newer response shape.
   - `aweme_list[].statistics` means the older response shape.
6. Scrape all pages with resume enabled by state files, de-duplicate by item id when present, and validate row counts.
7. Deliver the local artifacts:
   - CSV: analysis-ready table with UTF-8 BOM for spreadsheet compatibility.
   - JSON manifest: scrape metadata, row count, completeness, warnings.
   - Markdown brief: top works, totals, yearly trend, and warnings.
   - Optional raw JSON: only when `--export-json` is set.
8. If the user asks to upload somewhere, treat the generated CSV as the source artifact and implement a separate explicit upload step using their own credentials/configuration.

## Output Contract

The CSV should include all fields actually observed in the API response. Common fields:

- `作品ID`
- `标题`
- `发布日期`
- `发布时间`
- `播放量`
- `点赞量`
- `评论量`
- `分享量`
- `收藏量`
- Optional newer metrics such as `平均观看秒数`, `完播率`, `5秒完播率`, `粉丝播放占比`, `主页访问量`, `新增关注数`, and rate fields when present.

When key fields are missing for many rows, report that Douyin may have changed the endpoint shape and keep the raw JSON for debugging with `--export-json`.

## Analysis Modes

For account traffic diagnosis, seasonal/monthly review, or content handoff analysis, prefer the latest CSV over a fresh scrape unless the user clearly asks for fresh data. Read `references/account-traffic-diagnosis.md` before writing recommendations.

Monthly low-period analysis should compare `发布条数`, `总播放`, `均播`, `中位数`, and `最高播放`. Do not rank months only by total plays because low publishing volume can distort totals.

## Troubleshooting

| Problem | Action |
| --- | --- |
| Cookie expired | Rerun without `--skip-browser-cookie`, log in through the browser, then retry. |
| Browser cannot be found | Install `agent-browser` or pass `--chrome-debug-port` for an existing debugging Chrome. |
| `websocket` import fails | Run `python3 -m pip install websocket-client`. |
| Completeness below 90% | Retry with `--resume`; if still low, rerun with `--force-restart --export-json` and inspect warnings. |
| No items returned | Check account access, login state, Creator Center page availability, and possible Douyin endpoint changes. |
| Need Feishu/Notion upload | Keep the scrape local first; add a separate opt-in upload workflow using user-provided configuration. |
