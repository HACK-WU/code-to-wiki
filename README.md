# CodeToWiki

把代码库转化为**结构化、可检索、带引用索引**的 Wiki 文档工具链。

只做一件事：**code → wiki + 引用索引（reference index）**，不依赖任何外部知识库 / 语义索引（如 ki / knowledge-indexer）。索引是纯本地 JSON（`metadata.json`），记录「源文件 ↔ Wiki 页面」的双向映射，并支持按 commit 增量更新。
## 组件

`skills/` 下四个 AI 技能（`code-to-wiki` 生成 Wiki、`wiki-incremental-update` 增量同步、`wiki-metadata-sync` 手动编辑后重建索引、`wiki-lookup` 按文件/commit 反查受影响 Wiki）；`src/codetowiki/` 为格式校验 + 索引构建/检测/反查/增量更新的 Python 包；`tests/` 为单测。

## 安装

推荐一键安装（自动用 `uv`/`pip` 拉取最新 Release wheel，无需克隆仓库）：

```bash
curl -fsSL https://raw.githubusercontent.com/HACK-WU/CodeToWiki/master/scripts/install-latest.sh | bash
# 可选参数：--pre 含预发布版本；REPO=owner/repo 覆盖默认仓库
```

开发者可编辑安装（提供 `codetowiki` 命令；`[fast]` 可选 orjson 加速）：

```bash
pip install -e ".[fast]"
```

## 安装 AI Skills 到目标项目

把本项目的四个 AI 技能（`code-to-wiki` / `wiki-incremental-update` / `wiki-metadata-sync` / `wiki-lookup`）安装到任意项目，供 CodeBuddy 等加载。

```bash
curl -fsSL https://raw.githubusercontent.com/HACK-WU/CodeToWiki/master/scripts/skill-install.sh \
  | bash -s -- --skills -t /path/to/target
```

本地运行同样默认远程下载（不依赖本地 `skills/`）：

```bash
bash scripts/skill-install.sh --skills -t /path/to/target
```

### 参数说明

| 参数 | 作用 |
|------|------|
| `--skills` | 安装模式开关：把 Skills 复制到目标项目的 `skills/` |
| `-t <dir>` | 指定目标项目目录，可多次使用（如 `-t a -t b`） |
| `--file <txt>` | 从配置文件读取目标目录列表（每行一个路径，支持 `#` 注释），与 `-t` 互斥 |
| `-n <name>` | 按 skill 名过滤，逗号分隔或多次使用（如 `-n code-to-wiki`），缺省安装全部 |
| `--rules` | **不支持**（本项目仅分发 Skills），传入即报错退出 |

说明：
- `-t` 与 `--file` 互斥；都不传时读取默认配置 `$HOME/.skill-targets`。
- 目标目录若以 `skills` 结尾则直接写入、不再额外嵌套 `skills/` 子目录。
- 位置参数等价于 `-t`（如 `bash scripts/skill-install.sh /path/to/target`）。
- 远程安装时可用环境变量覆盖来源：`REPO`（默认 `HACK-WU/CodeToWiki`）、`REF`（默认 `master`）；如需改用本地源（开发调试）可用 `SKILLS_SRC` 覆盖源 `skills/` 目录。

## Skills 使用方式

安装到目标项目后，由 CodeBuddy 等 AI 编码助手按场景自动加载。四个 Skill 覆盖「生成 → 增量更新 → 索引同步 → 反查」完整链路；所有能力均通过 `codetowiki` CLI 暴露，Skill 本身不直接调用内部 Python 模块。

| Skill | 触发场景 | 关键命令 |
|-------|----------|----------|
| [`code-to-wiki`](skills/code-to-wiki/SKILL.md) | 用户要求「根据代码生成 wiki」「为某模块写文档」「梳理代码生成文档」。先与用户确认 Wiki 存储位置，再走「大纲确认 → 分批撰写 → 每篇 `codetowiki wiki-format` 校验」流程 | `codetowiki wiki-format --file/--wiki-dir [--fix]` |
| [`wiki-incremental-update`](skills/wiki-incremental-update/SKILL.md) | 用户要求「根据某 commit 更新 Wiki」「分析变更影响哪些 Wiki 页面」。先 `detect` dry-run，AI 决策新功能是否建页，再更新受影响页面并 `sync-index` | `codetowiki detect` / `codetowiki cleanup-citations` / `codetowiki sync-index` / `codetowiki wiki-format` |
| [`wiki-metadata-sync`](skills/wiki-metadata-sync/SKILL.md) | 用户直接手动创建/编辑/删除 Wiki 后，要求「更新 metadata.json 映射」「rebuild index」 | `codetowiki build-index` / `codetowiki sync-index` |
| [`wiki-lookup`](skills/wiki-lookup/SKILL.md) | 用户要求「改代码前查相关 Wiki」「review 时查受影响 Wiki」「排查问题时理解架构」。按文件或 commit 反查受影响 Wiki 并按命中数降序 | `codetowiki lookup` |

> 各 Skill 的详细流程、Wiki 格式规范（R1-R7）与调用纪律见 [`skills/code-to-wiki/SKILL.md`](skills/code-to-wiki/SKILL.md)、[`skills/wiki-incremental-update/SKILL.md`](skills/wiki-incremental-update/SKILL.md)、[`skills/wiki-metadata-sync/SKILL.md`](skills/wiki-metadata-sync/SKILL.md)、[`skills/wiki-lookup/SKILL.md`](skills/wiki-lookup/SKILL.md)。

## metadata.json 结构

`init` / `build-index` 读写的本地索引文件，纯 JSON、无外部依赖。它是所有 `detect`/`lookup` 命令的输入。

```json
{
  "project": "myproj",
  "wiki_path": "wiki/",
  "excluded_paths": [
    "node_modules/",
    "vendor/",
    "*/migrations/",
    "*/tests/",
    "*/__init__.py"
  ],
  "noise_paths": [
    "*.pyc",
    "^docs/"
  ],
  "source": {
    "commit_id": "...",
    "repo_url": "...",
    "branch": "..."
  },
  "source_to_wiki": {
    "src/foo.py": ["01-概览.md"]
  },
  "wiki_to_source": {
    "01-概览.md": ["src/foo.py"]
  },
  "repo_prefix": "",
  "stats": {
    "wiki_count": 1,
    "source_count": 1,
    "citation_count": 1
  },
  "warnings": [
    "引用指向不存在的源码: src/legacy.py"
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `project` | str | 项目名称 |
| `wiki_path` | str | Wiki 文档目录（相对路径） |
| `excluded_paths` | list[str] | 索引构建与变更检测都**完全排除**的路径（glob/前缀） |
| `noise_paths` | list[str] | 参与索引构建，但 git diff 时不触发变更检测 |
| `source.commit_id` | str | 构建时的 commit，由 `--commit` 或 `--repo-dir` 的 `HEAD` 填入 |
| `source.repo_url` / `branch` | str | 源码仓库地址与分支，缺省时继承 `--metadata` 已有值 |
| `source_to_wiki` | map[str→list] | 源文件 → 引用它的 Wiki 页面列表（双向映射之一） |
| `wiki_to_source` | map[str→list] | Wiki 页面 → 它引用的源文件列表（双向映射之二） |
| `repo_prefix` | str | 仓库根下路径前缀（如 `src/`），供新文件 Wiki 目录推断 |
| `stats` | map | 统计：`wiki_count` / `source_count` / `citation_count` |
| `warnings` | list[str] | 仅 `--check-paths` 发现幽灵引用时写入 |

> `excluded_paths` 与 `noise_paths` 的默认值已泛化为通用规则（依赖 / 构建产物 / 测试 / 迁移）。项目专属排除项通过已有 `metadata.json`（`--metadata`）保留，不会被默认值覆盖。

## 命令参考

### init —— 生成 metadata.json 骨架
```bash
codetowiki init --project-name myproj --wiki-dir wiki --repo-url <git-url> --branch main --output wiki/metadata.json
```
```
已生成 metadata 骨架: wiki/metadata.json
  project      : myproj
  wiki_dir     : wiki
  excluded_paths: 9 条默认规则
```

### build-index —— 构建引用索引
```bash
codetowiki build-index --wiki-dir wiki --metadata wiki/metadata.json --repo-dir . \
  --repo-url <git-url> --branch main --repo-prefix src/ --check-paths --output wiki/metadata.json
```
- `--metadata`：保留已有配置并继承 `source.repo_url`/`branch`；`--repo-prefix`（可选）供 Wiki 目录推断；`--check-paths`（可选）校验引用真实性并写入 `metadata.warnings`；`--commit` 省略则从 `--repo-dir` 取 `HEAD`
```
[warning] 引用指向不存在的源码: src/legacy.py
```

### detect —— 检测提交影响的 Wiki 页面（dry-run）
```bash
codetowiki detect --metadata wiki/metadata.json --new-commit <sha> --old-commit <old> --repo-dir .
```
`--old-commit` 省略时取 `metadata.source.commit_id`。输出分类：精确 / dirname / 父目录 / 新功能文件 / 新功能文件簇 / 可推断放置位置 / 需人工判断 / 未覆盖变更。
```
Wiki incremental change analysis (<old> -> <sha>)
Changed files: 3 (excluded 0, total 3)
Affected wiki pages: 2

| 级别 | Wiki 页面 | 变更文件 |
|------|-----------|----------|
| [精确] | 01-概览.md | src/foo.py |
```

### lookup —— 反查受影响的 Wiki
```bash
codetowiki lookup --metadata wiki/metadata.json --files src/foo.py   # 或 --new-commit <sha> --repo-dir . 先 git diff 再查
```
```
指定文件: 1 个

共 1 篇 Wiki 页面受影响：

  [  1 文件]  01-概览.md
          ↳ src/foo.py
```

### wiki-format —— 格式校验（R1-R6）
```bash
codetowiki wiki-format --wiki-dir wiki                 # 递归扫描目录
codetowiki wiki-format --file wiki/01-xxx.md --fix     # 单文件 + 自动修复
```
`--wiki-dir` 与 `--file` 互斥必填；`--strict` 使警告也失败；`--json` 输出 JSON。
```
Wiki 格式检查报告
========================================
文件总数: 1    ✅ 通过: 0    ❌ 错误: 1    ⚠️ 警告: 0
📄 wiki/01-xxx.md
   ❌ R1 (行 1): 缺少 <cite> 块
```
退出码：`0`=合规；`1`=存在 error（或 `--strict` 时 warning）；`2`=运行异常（文件无法读取 / 非 git 仓库等）。

### cleanup-citations —— 清理失效/重命名引用
```bash
codetowiki cleanup-citations --file wiki/01-x.md --dead src/old.py
codetowiki cleanup-citations --file wiki/01-x.md --renamed src/old.py:src/new.py
```
源文件删除/重命名后清理 Wiki 中的 `<cite>` 与 `章节来源` 引用：`--dead` 移除引用条目并清理空来源块，`--renamed` 替换引用路径。`--output` 缺省时覆盖 `--file`。

### sync-index —— 增量同步索引
```bash
codetowiki sync-index --metadata wiki/metadata.json --wiki-dir wiki \
  --wikis wiki/01-x.md wiki/02-y.md --commit <sha> --output wiki/metadata.json
```
仅重算指定 Wiki 的 `source_to_wiki` / `wiki_to_source` 与 `stats`，并更新 `source.commit_id`；其余映射不动。增量失败时自动降级为全量 `build-index`。


