# Douyin Creator Data Scraper Skill

[中文说明](README.zh-CN.md)

Codex/Hermes-style skill for exporting Douyin Creator Center works data to local CSV, JSON manifest, and Markdown brief.

This is a public-safe version of a private workflow. It keeps the core scraper behavior but removes personal Feishu wiki tokens, hard-coded local paths, remote overwrite defaults, and automatic cleanup of user folders.

## 中文概览

这是一个用于导出抖音创作者中心作品数据的 Codex/Hermes 风格 skill。公开版默认只在本地生成 CSV、JSON manifest 和 Markdown 简报，不包含任何个人飞书知识库配置、固定本机路径、Cookie、账号数据或远程覆盖逻辑。远程同步需要作为用户显式配置的后处理步骤。

## What It Does

- Opens or reuses a browser session logged into Douyin Creator Center.
- Reads Douyin cookies through local Chrome DevTools Protocol.
- Detects the current Creator Center works API response shape.
- Scrapes all pages with resume support and de-duplication.
- Exports:
  - CSV for spreadsheet/data analysis
  - JSON manifest with metadata and warnings
  - Markdown summary brief
  - Optional normalized raw JSON rows

## Install

Copy the skill folder into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
cp -R douyin-creator-data-scraper ~/.codex/skills/
```

Install the Python dependency:

```bash
python3 -m pip install -r requirements.txt
```

Install `agent-browser` if you want the script to open a browser automatically:

```bash
npm install -g agent-browser
agent-browser install
```

You can also use your own Chrome launched with remote debugging and pass `--chrome-debug-port`.

## Usage

From the skill directory:

```bash
python3 scripts/douyin_creator_pipeline.py --account "账号名"
```

Resume:

```bash
python3 scripts/douyin_creator_pipeline.py --account "账号名" --resume
```

Use project-local state and outputs:

```bash
python3 scripts/douyin_creator_pipeline.py \
  --account "账号名" \
  --workdir ./work/douyin-state \
  --output-dir ./outputs/douyin
```

Preflight:

```bash
python3 scripts/douyin_creator_pipeline.py --account "账号名" --dry-run
```

## Privacy

Do not commit cookies, generated CSVs, raw JSON, progress logs, or state files. The included `.gitignore` excludes the common local artifact paths.

Only use this for accounts you control or are authorized to access, and respect the platform's terms and rate limits.

## Optional Uploads

Remote upload is intentionally not included as a default step. If you want Feishu, Notion, S3, or another destination, run the local scrape first and then build an explicit downstream uploader using your own credentials and config.

See `douyin-creator-data-scraper/references/public-workflow-notes.md`.
