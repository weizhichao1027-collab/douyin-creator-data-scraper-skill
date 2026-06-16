# Public Workflow Notes

This public version intentionally keeps the original scraping capability but removes private operational assumptions.

## What Changed From A Private Hermes Workflow

- Local output is the default. The script writes CSV, manifest JSON, and Markdown brief to `./outputs` unless `--output-dir` is provided.
- State is configurable. The default is `~/.cache/douyin-creator-data-scraper`, or use `--workdir` / `DOUYIN_SCRAPER_HOME`.
- No private Feishu defaults. The script does not include hard-coded `space_id`, `parent_node_token`, wiki URLs, doc tokens, file tokens, or tenant domains.
- No automatic remote overwrite. Uploading, replacing, or deleting remote attachments must be implemented as a separate explicit step.
- No Desktop cleanup. The script does not delete older CSVs from user folders.
- Secrets stay local. Cookie cache files are written with owner-only permissions where the OS allows it and are excluded by the repository `.gitignore`.

## Optional Downstream Sync Pattern

If a user wants to upload the CSV to Feishu, Notion, S3, GitHub Releases, or another destination:

1. Finish the local scrape first.
2. Use the manifest JSON to locate the generated CSV and brief.
3. Load destination-specific credentials from the user's own environment or config file.
4. Upload or replace remote files only after the user explicitly asks for that behavior.
5. Log the remote URL in a separate result file. Do not write secrets into the manifest.

## API Shape Notes

The script currently recognizes two response shapes from `creator.douyin.com/janus/douyin/creator/pc/work_list`:

| Shape | Data path | Metrics path | Page size |
| --- | --- | --- | --- |
| Newer | `items[]` | `items[].metrics` | 12 |
| Older | `aweme_list[]` | `aweme_list[].statistics` | 18 |

Common metric mappings:

| CSV field | Older API | Newer API |
| --- | --- | --- |
| `播放量` | `statistics.play_count` | `metrics.view_count` |
| `点赞量` | `statistics.digg_count` | `metrics.like_count` |
| `评论量` | `statistics.comment_count` | `metrics.comment_count` |
| `分享量` | `statistics.share_count` | `metrics.share_count` |
| `收藏量` | `statistics.collect_count` | `metrics.favorite_count` or `metrics.collect_count` |

When Douyin changes a field, keep the raw response with `--export-json`, update `normalize_item`, and document the new field empirically.
