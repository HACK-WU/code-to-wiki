---
name: wiki-metadata-sync
description: When wiki markdown files are directly created, edited, or deleted (not through code-change-driven pipeline), automatically sync metadata.json bidirectional mappings (source_to_wiki / wiki_to_source) using build-index. Use after manually creating or editing wiki pages, updating cite blocks, or when the user asks to update metadata.json mappings.
---

# Wiki 元数据映射同步

> Wiki 文件直接编辑后，自动同步 `metadata.json` 中的 `source_to_wiki` / `wiki_to_source` 双向映射。

## 触发场景

- 手动新建了 Wiki 页面（含 `<cite>` 引用块）
- 修改了已有 Wiki 页面的 `<cite>` 引用或 `章节来源`
- 删除了 Wiki 页面，需要清理失效映射
- 用户要求「更新 metadata.json 映射」「同步 Wiki 索引」
- 用户要求「rebuild index」

## 与 wiki-incremental-update 的区别

| 维度 | wiki-incremental-update | wiki-metadata-sync（本 Skill） |
|------|------------------------|-------------------------------|
| 触发方向 | 代码变更 → 检测受影响 Wiki → 更新 Wiki → 同步 metadata | Wiki 直接编辑 → 同步 metadata |
| 核心命令 | `detect` + 人工更新 Wiki 内容 | `build-index` 自动全量重建 |
| 适用场景 | 源码变更后，需要 AI 分析并更新 Wiki | Wiki 原文手动创建/编辑后，更新映射关系 |

## 关键文件

| 文件 | 说明 |
|------|------|
| `<wiki_dir>/metadata.json` | 元信息、双向索引、源代码仓库信息 |
| `src/codetowiki/wiki_incremental/index_builder.py` | 扫描 wiki markdown，解析 `<cite>` 和 `章节来源` 引用，重建 `source_to_wiki` / `wiki_to_source` |
| `src/codetowiki/cli.py` | `build-index` 命令行入口 |
| `src/codetowiki/wiki_incremental/incremental_index.py` | 增量更新（仅更新指定 Wiki 的映射） |

## 前置检查

1. 确认 `<wiki_dir>/metadata.json` 存在
2. Wiki 文件中的引用格式必须符合规范：`- [名称](file://相对路径#Lx-Ly)`

## 标准流程

### Step 1: 提交 Wiki 变更

Wiki 文件变更建议先提交，确保 `build-index` 扫描到最新内容：

```bash
cd <wiki-repo>
git add <wiki_dir>/...
git commit -m "docs(wiki): 描述变更内容"
```

### Step 2: 重建映射

回到项目根目录执行 `build-index`：

```bash
cd <source-repo> && \
codetowiki build-index \
  --wiki-dir <wiki_dir> \
  --metadata <wiki_dir>/metadata.json \
  --repo-dir . \
  --output <wiki_dir>/metadata.json
```

参数说明：
- `--wiki-dir`：wiki 文档目录（相对路径）
- `--metadata`：已有 metadata.json（保留 excluded_paths、noise_paths 等配置）
- `--repo-dir`：源代码仓库根目录（用于获取当前 commit_id）
- `--output`：输出路径（原地更新）

### Step 3: 验证映射

检查生成的映射是否覆盖了新增/变更的 Wiki 页面：

```bash
cd <wiki-repo>
git diff <wiki_dir>/metadata.json | grep "新增的Wiki文件名"
```

关注点：
- 新增 Wiki 页面的 `wiki_to_source` 条目是否正确
- 引用源文件的 `source_to_wiki` 是否包含新页面
- `stats` 中的 `wiki_count`、`source_count`、`citation_count` 是否合理

### Step 4: 提交 metadata

```bash
cd <wiki-repo>
git add <wiki_dir>/metadata.json
git commit -m "chore: 更新 metadata.json 双向映射"
```

## 增量更新（可选）

如果仅少量 Wiki 文件变更，可使用增量方式避免全量重建：

```python
from codetowiki.wiki_incremental.incremental_index import incremental_index_update, save_metadata
from codetowiki.wiki_incremental.json_utils import load_json

metadata = load_json("<wiki_dir>/metadata.json")
new_commit = "当前HEAD的commit_id"
affected_wikis = ["核心组件/聚合引擎.md"]

updated = incremental_index_update(metadata, affected_wikis, new_commit, "<wiki_dir>")
save_metadata(updated, "<wiki_dir>/metadata.json")
```

增量失败时自动降级为全量 `build_index`（`safe_index_update` 函数已内置此逻辑）。

## build-index 解析机制

`index_builder.py` 的 `parse_citations()` 函数解析以下引用类型：

| 引用类型 | 识别方式 | 示例 |
|----------|---------|------|
| `<cite>` 块 | `<cite>...</cite>` 内的 `- [名称](file://路径)` | 文件顶部引用块 |
| 章节来源 | `章节来源` 标题后的 `- [名称](file://路径)` | 每个章节末尾 |
| 图表来源 | `图表来源` 或 `图示来源` 后的引用 | Mermaid 图之后 |

生成的映射结构：
```json
{
  "source_to_wiki": {
    "src/constants/issue.py": [
      "Issue功能/Issue 状态管理.md",
      "Issue功能/Issue 系统设计总览.md"
    ]
  },
  "wiki_to_source": {
    "Issue功能/Issue 状态管理.md": [
      "src/core/documents/issue.py",
      "src/constants/issue.py"
    ]
  }
}
```

## 完成摘要

执行后输出：
- 新增/删除的 Wiki 文件数
- `stats` 变更（wiki_count、source_count、citation_count）
- 新增/修改的映射条目概览
- commit_id 是否更新
