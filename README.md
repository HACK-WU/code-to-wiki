# CodeToWiki

把代码库转化为**结构化、可检索、带引用索引**的 Wiki 文档工具链。

本仓库只做一件事：**code → wiki + 引用索引（reference index）**，不依赖任何外部知识库 / 语义索引（如 ki / knowledge-indexer）。索引是纯本地 JSON（`metadata.json`），记录「源文件 ↔ Wiki 页面」的双向映射，并支持按 commit 增量更新。

## 组件

| 组件 | 说明 |
|------|------|
| `skills/code-to-wiki/` | AI 技能：分析代码库并生成合规 Wiki（R1-R6 格式规范内联） |
| `skills/wiki-incremental-update/` | AI 技能：按 commit 增量检测受影响 Wiki 并同步索引 |
| `skills/wiki-metadata-sync/` | AI 技能：Wiki 手动编辑后重建引用索引 |
| `src/codetowiki/` | Python 包：格式校验 + 引用索引构建/检测/反查/增量更新 |
| `tests/` | 单测 |

## 安装

### 一键安装（推荐）

通过 `curl | bash` 直接拉取最新 Release 的 wheel 并安装（脚本会自动用 `uv` 或 `pip` 安装，无需克隆仓库）：

```bash
curl -fsSL https://raw.githubusercontent.com/HACK-WU/CodeToWiki/master/scripts/install-latest.sh | bash
```

可选参数：

```bash
curl -fsSL https://raw.githubusercontent.com/HACK-WU/CodeToWiki/master/scripts/install-latest.sh | bash -s -- --pre  # 包含预发布版本
REPO=owner/repo curl -fsSL https://raw.githubusercontent.com/HACK-WU/CodeToWiki/master/scripts/install-latest.sh | bash  # 覆盖默认仓库
```

> 安装后如需加速 JSON 读写，可补装可选依赖：`pip install 'codetowiki[fast]'`。

### 从源码可编辑安装（开发者）

```bash
pip install -e .            # 可编辑安装，提供 codetowiki 命令
pip install -e ".[fast]"    # 可选：用 orjson 加速 JSON 读写
```

## CLI 用法

```bash
# 1) 为新项目生成 metadata.json 骨架（不含任何 ki 配置）
codetowiki init --project-name myproj --wiki-dir wiki --repo-url <git-url> --branch main

# 2) 构建引用索引（解析 <cite> / 章节来源，生成双向映射）
codetowiki build-index \
  --wiki-dir wiki \
  --metadata wiki/metadata.json \
  --repo-dir . \
  --repo-url <git-url> --branch main \
  --output wiki/metadata.json

# 3) 检测某次提交影响的 Wiki 页面（dry-run，不写文件）
codetowiki detect --metadata wiki/metadata.json --new-commit <sha> --repo-dir .

# 4) 按文件路径或 commit 反查受影响 Wiki
codetowiki lookup --metadata wiki/metadata.json --files src/foo.py
codetowiki lookup --metadata wiki/metadata.json --new-commit <sha> --repo-dir .

# 5) 格式校验（R1-R6），--fix 自动修复可机械修复项
codetowiki wiki-format --wiki-dir wiki
codetowiki wiki-format --file wiki/01-xxx.md --fix
```

所有子命令也可作为模块直接调用：`python -m codetowiki.cli ...`、`python -m codetowiki.wiki_format_check ...`。

## Python API

```python
from codetowiki import build_index, detect_changes, lookup_wikis, validate_and_fix

metadata = build_index("wiki/", commit_id="<sha>", repo_url="<git-url>", branch="main")
report = detect_changes(old_commit, new_commit, metadata, repo_dir=".")
ranked, unmatched = lookup_wikis(metadata["source_to_wiki"], ["src/foo.py"])
```

## metadata.json 结构

```json
{
  "project": "myproj",
  "wiki_path": "wiki/",
  "excluded_paths": ["node_modules/", "vendor/", "*/migrations/", "*/tests/", "*/__init__.py"],
  "noise_paths": ["*.pyc", "^docs/"],
  "source": { "commit_id": "...", "repo_url": "...", "branch": "..." },
  "source_to_wiki": { "src/foo.py": ["01-概览.md"] },
  "wiki_to_source": { "01-概览.md": ["src/foo.py"] },
  "stats": { "wiki_count": 1, "source_count": 1, "citation_count": 1 }
}
```

- `excluded_paths`：构建索引与变更检测都**完全排除**。
- `noise_paths`：参与索引构建（Wiki 可能引用），但 git diff 时不触发变更检测。

## 与具体项目解耦

- 默认排除项已泛化为通用规则（依赖/构建产物/测试/迁移）。
- 项目专属排除项通过已有 `metadata.json`（`--metadata`）保留，不会被默认值覆盖。
- 路径前缀（如仓库根下的 `src/`）可通过 `metadata.repo_prefix` 配置，供新文件 Wiki 目录推断使用。

## 设计边界

- **保留**：引用索引（reference index）+ 其增量更新。
- **不依赖**：ki / knowledge-indexer 等语义索引、Django 专属工具、任何外部配置模板。
