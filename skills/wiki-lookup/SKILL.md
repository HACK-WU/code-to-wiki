---
name: wiki-lookup
description: 根据 commit 或修改的文件路径，快速反查受影响的 Wiki 文档并按命中文件数降序排列。当用户在修改代码前想了解设计上下文、code review 时查受影响 Wiki、排查问题时理解模块架构，或评估变更影响范围时使用。
---

# Wiki 反查

> 已知 commit 或修改的文件路径，快速反查受影响的 Wiki 文档，按命中文件数降序排列。在修改代码前、code review 时、排查问题时使用。

## 触发场景

| 场景 | 说明 |
|------|------|
| 修改代码前 | 收到代码修改任务，通过 `--files` 查相关 Wiki 了解设计上下文 |
| code review 时 | 拿到 commit hash，通过 `--new-commit` 查受影响 Wiki 辅助审查 |
| 排查问题时 | 定位到问题文件后，反查 Wiki 了解模块架构和依赖关系 |
| 影响评估 | 合并模式下查特定文件在整个 commit 变更中的 Wiki 覆盖面 |
| 探索代码 | 不熟悉某个文件时，查引用它的 Wiki 了解用途和设计 |

## 关键依赖

| 依赖 | 说明 |
|------|------|
| `<wiki_dir>/metadata.json` | 必须包含 `source_to_wiki` 字段（由 `codetowiki build-index` 构建） |
| 源代码仓库 | `--repo-dir` 指向的工作区（commit 模式需要 git 可用） |

如果 `metadata.json` 不含 `source_to_wiki`，先构建索引：

```bash
codetowiki build-index \
  --wiki-dir <wiki_dir> \
  --metadata <wiki_dir>/metadata.json \
  --repo-dir . \
  --repo-url <repo-url> \
  --branch <branch> \
  --repo-prefix <repo-prefix> \
  --check-paths \
  --output <wiki_dir>/metadata.json
```

- `--metadata` 读取已有配置（excluded_paths/noise_paths 等），防止被默认值覆盖。
- `--repo-prefix`（可选）：仓库根下的路径前缀（如 `src/`），供 Wiki 目录推断使用。
- `--check-paths`（可选）：校验 wiki 引用的源码路径是否真实存在，发现幽灵引用时写入 `metadata.warnings`。

## 命令速查

所有能力通过 `codetowiki` CLI 暴露，本 Skill 不直接调用内部模块。

### 按文件路径反查

```bash
codetowiki lookup \
  --metadata <wiki_dir>/metadata.json \
  --files <file1> <file2> ...
```

### 按 commit 反查（自动 diff 父提交）

```bash
codetowiki lookup \
  --metadata <wiki_dir>/metadata.json \
  --new-commit <hash> \
  --repo-dir .
```

> `--new-commit` 省略 `--old-commit` 时，自动与父提交 `<hash>~1` 做 `git diff --name-only`。

### 按 commit 范围反查

```bash
codetowiki lookup \
  --metadata <wiki_dir>/metadata.json \
  --new-commit <hash> \
  --old-commit <earlier_hash> \
  --repo-dir .
```

### 文件 + commit 合并查询

同一文件在两种来源中自动去重：

```bash
codetowiki lookup \
  --metadata <wiki_dir>/metadata.json \
  --files <file1> \
  --new-commit <hash> \
  --repo-dir .
```

## 输出解读

```
指定文件: 1 个 + commit 3a3630a~1..3a3630a: 42 个文件

共 8 篇 Wiki 页面受影响：

  [  5 文件]  告警系统设计/告警引擎核心.md
          ↳ src/core/engine.py, src/core/check.py, src/core/scheduler.py ... +3

  [  3 文件]  API接口文档/告警管理API.md
          ↳ src/api/alert.py, src/api/alert/serializers.py, src/api/hooks.py ... +1

  ...

未匹配文件 (18):
  - src/new_module/views.py
  ...
```

| 输出元素 | 含义 | 行动 |
|----------|------|------|
| 首行 summary | 输入来源和文件数 | 确认输入正确 |
| `[ N 文件]` | 该 Wiki 被 N 个变更文件引用 | N 越大优先级越高，优先阅读 |
| `↳ file1, file2 ... +M` | 前 3 个匹配文件 + 剩余 M 个 | 了解哪些具体文件触发了匹配 |
| `未匹配文件` | 在 `source_to_wiki` 中无匹配的文件 | 这些文件可能没有对应 Wiki，或用 `codetowiki detect` 查看是否需要新建 |
| 排序规则 | 命中文件数降序 | 排名越靠前的 Wiki 与变更关联越紧密 |

## 行动策略

### 场景 1：修改代码前了解上下文

1. 用 `--files` 传入待修改的文件路径
2. 阅读排名前 3 的 Wiki 页面，理解模块设计和依赖
3. 关注"未匹配文件"——如果关键文件无 Wiki，考虑是否需要补充文档

### 场景 2：code review 时找相关文档

1. 用 `--new-commit` + `--old-commit` 传入审查的 commit 范围
2. 按命中数顺序阅读 Wiki，验证代码变更是否与设计文档一致
3. 命中数异常低（如变更 50 个文件但只命中 2 篇 Wiki）→ 可能缺少文档覆盖

### 场景 3：排查问题时理解架构

1. 用 `--files` 传入出问题的文件路径
2. 阅读命中的 Wiki 了解该文件的职责和依赖关系
3. 结合代码级工具（如 git/IDE 的调用链分析）进一步了解实现

### 场景 4：影响评估

1. 用合并模式（`--files` + `--new-commit`）同时指定关键文件和 commit 范围
2. 查看关键文件在整体变更中的 Wiki 覆盖情况
3. 对 `--files` 指定的文件，确认其在 Wiki 中的角色是否与变更意图一致

## 与 detect 的区别

| | `lookup` | `detect` |
|--|----------|----------|
| 用途 | 反查 Wiki | 变更检测 + 新功能识别 |
| 输出 | Wiki 排名列表 | 三级匹配报告 + 新文件簇 |
| 适用时机 | 修改前查文档、review 时找设计 | 增量更新时分析影响 |
| 新文件 | 未匹配列表 | 聚类 + 推断 + 建议 |

两者互补：`lookup` 快速知道"改什么前应该读什么"，`detect` 详细分析"改完后要更新哪些 Wiki"。

## 常见问题

**Q: 输出为空？**
A: `source_to_wiki` 不包含你传入的文件。检查文件路径是否准确（工作区相对路径），或先跑 `codetowiki build-index` 重建索引。

**Q: 命中数感觉不准确？**
A: `lookup` 精确匹配 `source_to_wiki` 的键。检查文件中是否正确添加了 `<cite>` 标签和 `file://` 引用。

**Q: 想同时看变更影响和新功能簇？**
A: 先用 `lookup` 了解相关 Wiki，再用 `codetowiki detect` 分析完整变更和新文件聚类。
