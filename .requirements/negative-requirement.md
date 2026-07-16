---
id: NEG-REQ-001
title: CodeToWiki 负向需求（错误使用 / 状态异常场景）
type: negative-requirement
created: 2026-07-16
status: draft
related_positive:
  - REQ-01  # build-index
  - REQ-02  # detect
  - REQ-03  # lookup
  - REQ-04  # wiki-format
  - REQ-05  # init
  - REQ-06  # 增量更新
  - REQ-07  # 一键安装
---

# 负向需求设计报告（CodeToWiki）

## 1. 正向需求清单（推导基线）

| ID | 描述 | 预期效果 |
|----|------|----------|
| REQ-01 | `build-index` 从 wiki markdown 生成 metadata 索引 | 产出 `source_to_wiki`/`wiki_to_source` |
| REQ-02 | `detect` 按 commit 区间检测受影响 wiki 页 | 列出精确/目录/父目录级命中 |
| REQ-03 | `lookup` 按文件/commit 排名查 wiki | 命中页面按文件数降序 |
| REQ-04 | `wiki-format` 校验 R1–R6，可 `--fix` | 错误退出码非 0，可机械修复 |
| REQ-05 | `init` 生成 metadata 骨架 | 可二次 build-index 补全 |
| REQ-06 | 增量更新 metadata（仅受影响的 wiki） | 索引与 wiki 同步 |
| REQ-07 | 一键安装（`curl`/uv/pip） | `codetowiki` 全局可用 |

## 2. 风险概览

| 等级 | 数量 | 说明 |
|------|------|------|
| P0 | 1 | 必须处理 |
| P1 | 4 | 应该处理 |
| P2 | 6 | 建议处理 |
| P3 | 1 | 可选 |

## 3. 负向场景清单

| ID | 类型 | 场景描述 | 等级 | 程序行为概述 |
|----|------|----------|------|--------------|
| NEG-01 | 数据异常 | metadata.json 缺失/损坏/非 JSON | P0 | 友好报错 + 提示先 build-index/init |
| NEG-02 | 状态异常 | 在非 git 仓库目录运行 build-index/detect | P1 | 捕获非 git，提示切到仓库根 |
| NEG-03 | 参数输入错误 | `--new-commit` 提交哈希拼写错/不存在 | P1 | 校验 commit 存在，给出 git 报错 |
| NEG-05 | 用户误操作 | `wiki-format --fix` 直接改文件无预览/无备份 | P1 | 增加 `--dry-run`/备份后再写 |
| NEG-07 | 数据异常 | wiki 引用的源码路径已不存在（幽灵引用） | P1 | 校验引用路径存在，告警 |
| NEG-10 | 状态异常 | 增量更新后 wiki 被删但 source_to_wiki 仍残留 | P1 | 清理指向已删 wiki 的条目 |
| NEG-04 | 参数输入错误 | detect/lookup 缺 `--old-commit` 静默用 `HEAD~1` | P2 | 显式提示回退来源 |
| NEG-06 | 数据异常 | wiki-format 递归扫到 vendored/*.md | P2 | 支持 `--exclude` |
| NEG-08 | 状态异常 | 模糊匹配（dirname/parent）误报/漏报 | P2 | 标注启发式置信，避免误信 |
| NEG-09 | 参数输入错误 | `repo_prefix` 配错导致推断前缀错位 | P2 | 校验前缀，给出样本核对 |
| NEG-15 | 外部依赖 | 浅克隆下 `new_commit~1` 失败 | P2 | 检测浅克隆，提示用 `--old-commit` |
| NEG-17 | 中途放弃 | 安装后 `~/.local/bin` 不在 PATH | P2 | 检测 PATH，输出导出提示 |
| NEG-13 | 参数输入错误 | 必填参数缺失，argparse 提示晦涩 | P3 | 优化 usage 文案 |

## 4. 详细场景分析

### 4.1 NEG-01：metadata.json 缺失 / 损坏 / 非 JSON — P0

**场景**：用户直接跑 `detect`/`lookup`/`wiki-format`（部分链路）但 metadata 不存在，或文件被手改坏、编码错乱。

**代码依据**：`load_json`（`json_utils.py:18`）无任何 JSON 解析容错；`detect_changes` 在 `source_to_wiki` 为空时抛 `ValueError`（`change_detection.py:311`），`_run_lookup` 在为空时 `raise SystemExit(...)`（`cli.py:77`）。损坏 JSON 会直接抛 `JSONDecodeError` 堆栈。

**风险**：概率中、影响严重（全链路阻塞，且堆栈吓人）。

**程序行为**：
- 检测：`load_json` 捕获 `JSONDecodeError`/`FileNotFoundError`，返回结构化错误而非异常。
- 引导：报错文案含「metadata 不存在或损坏 → 请先运行 `codetowiki build-index` 或 `codetowiki init`」，并附示例命令。
- 体验：统一退出码（建议用 2 表示配置错误，与 1 运行错误区分）。

### 4.2 NEG-02：非 git 仓库运行 — P1

**场景**：在错误目录（如 wiki 单独目录、CI 非仓库语境）跑 `build-index`（无 `--commit` 时调 `git rev-parse HEAD`，`index_builder.py:127`，`check=True`）或 `detect`/`lookup`（内部 `subprocess` 调 git）。

**代码依据**：`_current_commit` 用 `check=True`，非仓库会抛 `CalledProcessError` 堆栈；`lookup` 的 git 失败倒是有 `SystemExit(result.stderr)` 处理（`cli.py:91`），两处不一致。

**风险**：概率中、影响中等。

**程序行为**：
- 检测：`try/except CalledProcessError` 包裹所有 git 调用。
- 引导：提示「当前目录不是 git 仓库，请用 `--repo-dir` 指定仓库或 `--commit` 显式传入」。

### 4.3 NEG-03：无效 commit 哈希 — P1

**场景**：`--new-commit` / `--old-commit` 拼写错或已被 gc。

**代码依据**：`run_git_diff` 在 `returncode != 0` 时抛 `RuntimeError("git diff failed")`（`change_detection.py:137`），且 `detect.main` 未捕获 → 堆栈；而 `lookup` 用 `SystemExit`（`cli.py:91`），**两处错误处理不一致**。

**风险**：概率中、影响中等。

**程序行为**：
- 预防：diff 前先 `git cat-file -e <commit>` 校验存在。
- 引导：统一在 CLI 层捕获 git 错误，输出 `commit 不存在: <hash>`，而非裸 `RuntimeError`。

### 4.4 NEG-05：`wiki-format --fix` 无预览/无备份 — P1

**场景**：用户跑 `--fix` 想修 R1–R5，但机械修复（加 `<cite>`、补 `file://`、插「章节来源/图表来源」、重写目录）可能改动其定制排版，且**直接覆盖原文件**（`wiki_format_check.py:263`、`format_validation.py`），无 `--dry-run`、无 `.bak`。

**代码依据**：`_try_fix` 直接 `path.write_text(fixed)`（`wiki_format_check.py:263`）；R6 仅告警不修（R6 行号需人工）。

**风险**：概率中、影响中高（虽可 git 恢复，但体验差，且 R6 的"已修复"错觉）。

**程序行为**：
- 预防/容错：新增 `--dry-run` 仅打印 diff 不写盘；默认写入前生成 `.bak` 备份。
- 引导：修复后明确区分「已自动修复 R1-R5」与「R6 行号需人工补全」，避免误判全部完成。

### 4.5 NEG-07：wiki 引用不存在的源码路径（幽灵引用）— P1

**场景**：wiki 里 `<cite>` 写了 `file://src/foo.py`，但代码已重命名/删除。`build-index` **不做存在性校验**（`index_builder.py:91` 仅解析不入仓校验），于是索引指向幽灵文件；后续 `detect` 真实 git diff 永远匹配不上 → 报告「未覆盖变更」。

**风险**：概率中高（代码演进必漂移）、影响中等（静默、难排查）。

**程序行为**：
- 检测：`build-index` 可选地（`--check-paths`）对照 repo 校验每个 `file://` 路径是否存在。
- 引导：不存在的路径在 `warnings` 中列出（当前 `warnings` 字段已有机制，`index_builder.py:189`），并在 stdout 汇总「N 个引用指向不存在的源码」。

### 4.6 NEG-10：增量更新后残留指向已删 wiki 的链接 — P1

**场景**：某 wiki 页从磁盘删除，`incremental_index_update` 仅处理 `affected_wikis`（`incremental_index.py:24`）。当 `full_path` 不存在时 `new_sources = set()`，会移除该 wiki 的 `wiki_to_source` 条目，但**不会反向清理 `source_to_wiki` 中仍指向该已删 wiki 的记录**（`incremental_index.py:41` 只处理 `removed` 的源码）。

**代码依据**：`incremental_index.py:36-48`，删 wiki 时只 `wiki_to_source.pop`，未对 `source_to_wiki` 做"该 wiki 是否已不存在"的兜底修剪。

**风险**：概率中、影响中等（stale 链接导致 `lookup`/`detect` 命中已消失页面）。

**程序行为**：
- 恢复：`incremental_index_update` 末尾遍历 `source_to_wiki`，剔除 `wiki_to_source` 中已不存在的 wiki 引用；或提供 `codetowiki prune` 全量兜底。
- 引导：更新后 `stats` 标注「清理 N 条失效链接」。

### 4.7 NEG-04：`--old-commit` 缺失静默回退 — P2

**场景**：`detect` 缺 `--old-commit` 时取 `metadata.source.commit_id`（`change_detection.py:392`），`lookup` 缺时取 `<new>~1`（`cli.py:83`）。用户不知回退来源，**跨大版本对比会漏报/误报**。

**程序行为**：
- 引导：回退时显式打印「old-commit 回退为：<值>（来源：metadata / new~1），如不符请显式传 `--old-commit`」。

### 4.8 NEG-06：wiki-format 递归扫到 vendored 目录 — P2

**场景**：wiki 仓库内若含 `node_modules/`、`vendor/` 等带 `.md` 的目录，`iter_markdown_files` 无排除（`wiki_format_check.py:68` rglob 全量），会误报大量 R1/R3。

**程序行为**：
- 容错：增加 `--exclude` 参数（复用 `change_detection.build_pathspec_args` 思路），默认跳过常见 vendored 目录。

### 4.9 NEG-08：模糊匹配误报/漏报 — P2

**场景**：`three_level_match` 的 dirname/parent 级是启发式（`change_detection.py:141`）。改了同目录无关文件会"父目录级"命中（误报）；源码路径前缀与 `repo_prefix` 不匹配时精确命中失败（漏报）。

**程序行为**：
- 引导：输出已标注 `[dirname]`/`[父目录]`/`[精确]`，但需**在报告头部加一句"dirname/父目录级为启发式关联，建议人工确认"**，避免用户误信。

### 4.10 NEG-09：`repo_prefix` 配错 — P2

**场景**：`repo_prefix`（如 `src/`）配错，导致 `pattern_inference` 在前两级前缀上推断错位（`pattern_inference.py:43`），放置建议整体偏移。

**程序行为**：
- 检测：`infer_rules` 样本不足（`min_samples=3`）时规则为空，本就会落为"需人工判断"；建议 CLI 在配 prefix 时 `--dry-run` 打印推断样本数供核对。

### 4.11 NEG-15：浅克隆下 `~1` 失败 — P2

**场景**：CI 浅克隆，`lookup` 默认 `new_commit~1` 或 detect 回退 `commit_id` 不在本地 → git 报错。

**程序行为**：
- 检测：git 调用捕获后，若为浅克隆明确提示「浅克隆无法回溯父提交，请用 `--old-commit` 显式指定」。

### 4.12 NEG-17：安装后命令不在 PATH — P2

**场景**：`install-latest.sh` 用 uv/pip 把 `codetowiki` 装到 `~/.local/bin`，但该目录未在 `PATH`（`install-latest.sh` 注释已说明，但脚本未检测）。

**程序行为**（与刚改的安装脚本衔接）：
- 检测：安装后检查 `command -v codetowiki`，若不在 PATH，打印「请执行 `export PATH="$HOME/.local/bin:$PATH"`（或写入 shell rc）」。

### 4.13 NEG-13：必填参数缺失提示晦涩 — P3

**场景**：argparse `required=True` 缺失时输出英文 usage，缺场景化引导。

**程序行为**：在子命令 `--help`/error 中补充示例，如 `detect 需要 --metadata 与 --new-commit`。

## 5. 与正向需求的关联

| 负向场景 | 关联正向 | 关联说明 |
|----------|----------|----------|
| NEG-01 | REQ-01/02/03 | 任何链路都依赖 metadata，损坏即全阻 |
| NEG-02 | REQ-01/02/03 | git 是底层依赖，非仓库直接失败 |
| NEG-03 | REQ-02/03 | commit 参数是 detect/lookup 入口 |
| NEG-05 | REQ-04 | `--fix` 是格式校验的破坏性操作 |
| NEG-07 | REQ-01 | 索引质量依赖引用路径真实存在 |
| NEG-10 | REQ-06 | 增量更新需保证双向映射一致 |
| NEG-04 | REQ-02/03 | 回退 commit 影响对比正确性 |
| NEG-06 | REQ-04 | 校验扫描范围应可控 |
| NEG-08 | REQ-02 | 关联命中是启发式，需明确边界 |
| NEG-17 | REQ-07 | 安装成功 ≠ 命令可用 |

## 6. 设计建议

1. **优先级**：先落 NEG-01（P0，统一 `load_json` 容错）、NEG-05（`--fix` 加 `--dry-run`+备份）、NEG-10（增量清理），这三项直接影响数据安全与可用性。
2. **交互建议**：所有 git/配置错误走统一的「友好报错 + 示例命令」封装，消除当前 `RuntimeError`/`CalledProcessError`/`SystemExit` 混用。
3. **测试建议**：重点覆盖 metadata 损坏、非 git 目录、无效 commit、wiki 被删后增量更新、phantom 引用五类用例。
