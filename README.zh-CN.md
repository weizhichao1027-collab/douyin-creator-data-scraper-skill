# 抖音创作者数据抓取 Skill

这是一个 Codex/Hermes 风格的 skill，用于把抖音创作者中心的作品数据导出到本地 CSV、JSON manifest 和 Markdown 简报。

这个仓库是公开安全版：保留浏览器登录复用、CDP Cookie 提取、接口版本识别、断点续传、去重、字段校验和简报生成能力；移除了私人飞书知识库 token、固定本机路径、远程覆盖默认逻辑和自动清理用户目录的行为。

## 能做什么

- 打开或复用已登录抖音创作者中心的浏览器会话。
- 通过本地 Chrome DevTools Protocol 读取抖音登录态。
- 自动识别创作者中心作品列表接口的新旧返回结构。
- 自动翻页抓取全部作品数据。
- 支持中断后断点续传。
- 按作品 ID 优先去重。
- 导出：
  - CSV：用于表格和数据分析
  - JSON manifest：记录导出元数据、字段、完整率和警告
  - Markdown brief：生成简要账号数据报告
  - 可选 raw JSON：用于排查接口字段变化

## 安装

复制 skill 到 Codex skills 目录：

```bash
mkdir -p ~/.codex/skills
cp -R douyin-creator-data-scraper ~/.codex/skills/
```

安装 Python 依赖：

```bash
python3 -m pip install -r requirements.txt
```

如果希望脚本自动打开浏览器，可以安装 `agent-browser`：

```bash
npm install -g agent-browser
agent-browser install
```

也可以使用自己启动的 Chrome 调试端口，并通过 `--chrome-debug-port` 传入。

## 使用方式

进入 skill 目录后运行：

```bash
python3 scripts/douyin_creator_pipeline.py --account "账号名"
```

断点续传：

```bash
python3 scripts/douyin_creator_pipeline.py --account "账号名" --resume
```

使用项目内的状态目录和输出目录：

```bash
python3 scripts/douyin_creator_pipeline.py \
  --account "账号名" \
  --workdir ./work/douyin-state \
  --output-dir ./outputs/douyin
```

只做环境预检，不抓取：

```bash
python3 scripts/douyin_creator_pipeline.py --account "账号名" --dry-run
```

保留 raw JSON 便于排查字段变化：

```bash
python3 scripts/douyin_creator_pipeline.py --account "账号名" --export-json
```

## 默认工作流程

1. 确认用户有权访问目标抖音创作者账号。
2. 打开或复用已登录的抖音创作者中心浏览器。
3. 通过本地 CDP 读取 Cookie，并只保存在本机状态目录。
4. 测试作品列表接口，识别新版 `items[].metrics` 或旧版 `aweme_list[].statistics`。
5. 自动翻页抓取数据，每页保存进度。
6. 过滤异常数据、校验完整率和关键字段。
7. 在本地输出 CSV、manifest 和 Markdown 简报。
8. 如果需要飞书、Notion、S3 或其他远程同步，基于生成的 CSV 单独执行显式上传步骤。

## 隐私与安全

- 不要提交 Cookie、生成的 CSV、raw JSON、日志或状态文件。
- 仓库里的 `.gitignore` 已排除常见本地状态和数据产物。
- 脚本运行时会读取本机浏览器登录态，这是抓取创作者中心数据所必需的。
- Cookie 不会打印到终端，不应粘贴到聊天或 issue 中。
- 只应抓取自己拥有或被授权访问的账号数据。
- 请遵守平台条款、访问频率和数据使用边界。

## 远程同步

公开版默认不包含飞书、Notion、S3、GitHub Release 等上传流程，也不会自动覆盖远程数据。

如果需要远程同步，建议先完成本地导出，然后基于 manifest 中的 CSV 路径实现单独的上传脚本，并从用户自己的环境变量或配置文件读取凭据。

更多说明见：

- `douyin-creator-data-scraper/references/public-workflow-notes.md`
- `douyin-creator-data-scraper/references/account-traffic-diagnosis.md`

## 许可证

本项目使用 MIT License。
