# Wiki 增量更新

> 根据 `<wiki_dir>/metadata.json` 中的源文件与 Wiki 映射关系，以及用户指定的 commit，分析并增量更新受影响的 Wiki 页面。

## 触发场景

- 用户要求根据某个 commit 更新 Wiki
- 用户要求分析代码变更会影响哪些 Wiki 页面
- 用户要求维护 `metadata.json` 中的 source/wiki 双向索引

## 关键文件

| 文件 | 说明 |
|------|------|
| `<wiki_dir>/metadata.json` | Wiki 元信息、排除规则、双向索引、**源代码仓库信息** (`source.repo_url`, `source.branch`, `source.commit_id`) |
| `src/codetowiki/wiki_incremental/index_builder.py` | 全量构建 `source_to_wiki` / `wiki_to_source`，记录源代码仓库 URL/分支/commit |
| `src/codetowiki/wiki_incremental/change_detection.py` | git diff 变更检测和三级匹配 |
| `src/codetowiki/wiki_incremental/pattern_inference.py` | 从 `source_to_wiki` 归纳路径模式，为新文件推断 Wiki 目录归属 |
| `src/codetowiki/wiki_incremental/citation_cleanup.py` | 删除/重命名文件的旧引用清理 |
| `src/codetowiki/wiki_incremental/format_validation.py` | Wiki 格式校验和机械修复 |
| `src/codetowiki/wiki_incremental/incremental_index.py` | 受影响 Wiki 的增量索引同步 |

## 前置检查

1. 确认当前工作目录是源代码仓库根目录。
2. 确认 `<wiki_dir>/metadata.json` 是否存在：
   - **不存在**：先 `init` 生成骨架（写入默认 `excluded_paths`/`noise_paths`，`source.commit_id` 留空，后续由 build-index 填充）：

     ```bash
     codetowiki init \
       --project-name <project> \
       --wiki-dir <wiki_dir> \
       --repo-url <repo-url> \
       --branch <branch> \
       --output <wiki_dir>/metadata.json
     ```
   - **已存在**：直接进入下一步。
3. 如果 `metadata.json` 不含 `source_to_wiki` 或 `wiki_to_source`，先构建索引：

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

- `--metadata` 读取已有配置（excluded_paths/noise_paths 等），防止被 `setdefault` 默认值覆盖。
- `--repo-prefix`（可选）：仓库根下的路径前缀（如 `src/`），供新文件 Wiki 目录推断使用，与 `metadata.repo_prefix` 对应。
- `--check-paths`（可选）：校验 wiki 引用的源码路径是否真实存在，发现幽灵引用时写入 `metadata.warnings` 并输出到 stderr；它不改写索引，仅辅助暴露失效引用，引用仓库外源码时可省略。

## 标准流程

### Step 1: 确认 commit 范围

- `old_commit` 默认读取 `<wiki_dir>/metadata.json` 的 `source.commit_id`
- `new_commit` 必须由用户指定（`--new-commit` 为必填参数）
- `source.repo_url` 和 `source.branch` 记录了源代码仓库的地址和分支，仅作追溯用途，不参与 diff 计算

### Step 2: Dry-run 变更检测

```bash
codetowiki detect \
  --metadata <wiki_dir>/metadata.json \
  --new-commit <new_commit> \
  --repo-dir .
```

输出需要重点检查：

- `[精确]`：源文件在索引中精确命中，可直接作为更新候选
- `[dirname]`：同目录模糊命中，必须在摘要里标注需要审核
- `[父目录]`：父目录回退命中，必须在摘要里标注需要审核
- `新功能文件`：新增且未被现有 Wiki 引用的文件（平铺列表）
- `新功能文件簇`：**新增**，将新功能文件按公共父目录聚类，每个簇包含文件列表、文件数、是否有 pattern inference 命中。用于 AI 判断是否构成独立新功能
- `可推断放置位置`：新功能文件中，通过路径模式推断出 Wiki 目录归属的（含置信度和关联页面）
- `需人工判断`：新功能文件中，路径模式未命中的，进入 Step 2.5 由 AI 分析
- `未覆盖变更`：已修改但无索引命中，仅在用户要求时处理

其中 `可推断放置位置` 表格各列含义：

| 列 | 说明 |
|----|------|
| 源文件 | 新增的源文件路径 |
| 建议 Wiki 目录 | 推断出的 Wiki 顶级目录 |
| 置信度 | 基于现有映射统计的匹配百分比（≥60% 才输出） |
| 策略 | `extend_existing`：同目录已有关联 Wiki，建议扩展；`new_page`：无关联页面，建议新建 |
| 关联页面 | 同路径前缀的已有 Wiki 页面（最多显示 2 个） |

dry-run 阶段不得写入任何 Wiki 或 metadata 文件。

### Step 2.5: AI 新功能分析决策（核心新增）

对 `新功能文件簇` 中的每个簇，AI 需做语义判断：**这个文件簇是否构成一个独立的新功能，值得单独建 Wiki 页面？**

#### 判断流程

对每个 FeatureCluster：

1. **如果簇中有文件已被 `可推断放置位置` 命中且 `strategy=extend_existing`**：
   - 这些文件应扩展到已有 Wiki，不单独建页
   - 跳过后续判断

2. **读取代表性文件**：取簇中 2-3 个核心文件（跳过 `__init__.py`、`urls.py`），快速阅读理解功能定位

3. **三维判断**：

| 判断维度 | 评估方法 | 阈值 |
|----------|---------|------|
| **规模独立** | 簇文件数 ≥ 3 | 多文件模块通常是独立功能 |
| **领域独立** | 代码中的类名/模块名/注释是否引入新领域概念 | 新 module/app 名 = 新功能信号 |
| **文档缺失** | 已有 wiki 中是否有针对性文档 | 无 = 新建，有 = 扩展 |

4. **输出建议**：

```markdown
## AI 新功能分析

| 文件簇 | 文件数 | 建议 | 理由 |
|--------|--------|------|------|
| src/issue/ | 6 | 🆕 新建 Issue 功能 Wiki | 新模块，6 文件构成独立子域 |
| core/scheduler/ | 1 | 📎 扩展已有 wiki | 单文件工具类，无独立领域概念 |
| core/drf/ | 2 | ⏭️ 跳过 | 基础设施增强，无需文档 |
```

5. **用户确认**：将建议呈现给用户，让用户决定：
   - 确认全部建议 → 进入 Step 4b 执行
   - 调整建议 → 按用户调整后的方案执行
   - 全部跳过 → 直接进入 Step 4 更新已有 Wiki

#### 决策原则

- **宁可建议，让用户否决**：不确定时建议新建，标注低置信度
- **单文件簇通常跳过**：除非该文件定义了新的核心领域模型
- **无独立名空间的小改动直接跳过**：如新增 utils/helpers/constants 文件
- **模式推断命中但 AI 判断不一致时，以 AI 判断为准**：pattern inference 只看路径前缀，AI 看代码语义

### Step 3: 用户确认

除非用户已经明确要求直接执行，否则在展示 dry-run 结果后询问是否继续实际更新。

如果受影响 Wiki 超过 50 个，必须提醒风险并等待确认。

### Step 4: 更新受影响 Wiki

> **⚠️ 禁止使用脚本自动更新 Wiki 内容。** Wiki 内容必须由 Agent 读取源文件后**手动分析和撰写**，不得使用任何脚本（如 `sed`、`awk`、Python 脚本等）自动生成或替换 Wiki 正文内容。脚本仅用于**辅助工具调用**（如 `citation_cleanup` 清理引用、`format_validation` 格式校验），不参与正文生成。原因：脚本批量处理容易丢失上下文、破坏格式一致性、引入难以觉察的内容错误。

对每个受影响 Wiki：

1. 读取当前 Wiki 内容，保留手动编辑内容。
2. 读取相关源文件的旧版本、新版本和 diff。
3. 只更新受变更影响的章节，避免重写整篇文档。
4. 如果源文件删除，调用 `citation_cleanup.cleanup_dead_citations(content, dead_files=[path], renamed_files={})` 清理失效引用。
5. 如果源文件重命名，调用 `citation_cleanup.cleanup_dead_citations(content, dead_files=[], renamed_files={old: new})` 替换路径。
6. 保持现有 Wiki 风格：
   - 文件顶部标题后保留 `<cite>`
   - 目录使用中文标题锚点，如 `[简介](#简介)`
   - 来源标题使用现有纯文本风格：`章节来源`、`图表来源`、`图示来源`
   - 引用格式为 `[名称](file://相对路径#Lx-Ly)`

### Step 4b: 新建 Wiki 页面（新功能簇）

对 Step 2.5 中用户确认需要新建 Wiki 的文件簇：

#### 确定 Wiki 结构

1. **如果簇中已有 `可推断放置位置` 的建议 Wiki 目录**：使用建议的顶级目录 + 根据功能模块创建子目录
2. **如果簇无推断结果但文件数 ≥ 5**：建议按功能拆分为总览 + 子功能多篇 Wiki
3. **如果簇文件数 2-4**：建议单篇 Wiki 覆盖所有文件

#### 生成 Wiki 内容

> **⚠️ 禁止使用脚本生成 Wiki 内容。** 新建 Wiki 页面必须由 Agent 读取源文件后**手动分析撰写**，不得使用任何脚本自动生成正文。格式校验脚本 `validate_and_fix` 仅用于事后格式检查，不参与内容生成。

1. **读取簇中所有源文件**：理解功能定位、核心类和接口
2. **确定放置路径**：在建议的 Wiki 顶级目录下创建子目录
3. **按模板生成内容**：
   - 文件顶部：`# 标题` + `<cite>` 引用块（列出引用的源文件）
   - 目录：中文标题锚点，如 `[简介](#简介)`
   - 章节：简介 → 项目结构 → 核心组件 → 架构总览 → 组件详细分析 → 依赖关系分析 → 结论
   - 每个章节后附 `章节来源`（引用格式：`[名称](file://相对路径#Lx-Ly)`）
   - 如有架构图，使用 Mermaid 并附 `图示来源`
4. **标注审核状态**：新建页面在文件首行添加 `<!-- [待审核] AI 自动生成，请人工确认后移除此标记 -->`
5. **格式校验**：同 Step 5，使用 `codetowiki wiki-format` 校验格式。
6. **索引同步**：同 Step 6，新建页面参与增量索引更新。

对 `strategy=extend_existing` 的文件：

- 优先在关联页面中补充新文件相关的章节和引用，不单独建页。

对 `需人工判断` 的文件：

- 这些文件已在 `新功能文件簇` 中展示。对于文件数为 1 的簇，AI 读取代码后判断是否值得建页；如不值得，标注「建议跳过」。
- 不再简单放弃，而是由 Step 2.5 的 AI 分析接管。

### Step 5: 格式校验

写入前对每个更新或新建的 wiki 执行格式校验：

```python
from codetowiki.wiki_incremental.format_validation import validate_and_fix

content, violations = validate_and_fix(updated_content)
# violations 中包含所有 R1-R6 违规及修复状态
```

校验规则：

- `<cite>` 块存在
- 引用路径使用 `file://相对路径`
- 目录条目和 `##` 章节一致
- Mermaid 图后保留来源段落
- 更新章节保留或补充 `章节来源`

机械修复只能改格式，不得凭空改正文含义。

### Step 6: 索引同步

更新完成后，只扫描受影响 Wiki 并更新 metadata：

```python
from codetowiki.wiki_incremental.incremental_index import incremental_index_update, save_metadata
```

更新内容：

- `source.commit_id = <new_commit>`（`repo_url` 和 `branch` 保持不变）
- `source_to_wiki`
- `wiki_to_source`
- `stats.source_count`
- `stats.wiki_count`
- `stats.citation_count`

如果增量索引失败，降级为全量 `build_index`。

## AI 更新原则

| 原则 | 要求 |
|------|------|
| 最小修改 | 只改受变更影响的章节和引用 |
| 保留人工内容 | 不删除人工补充说明、注释和未受影响章节 |
| 引用可追溯 | 新增或修改内容必须能对应到源文件引用 |
| 模糊命中保守 | `[dirname]` / `[父目录]` 命中优先标注审核，不做大范围推断 |
| 先预览后写入 | 默认 dry-run；用户确认后才实际改文件 |
| 新建标注审核 | AI 生成的新 Wiki 页面必须标注 `[待审核]`，人工确认后才算正式入库 |
| 高置信度优先 | 只对置信度 ≥60% 的推断结果生成页面，低置信度的仅列出不生成 |

## 完成摘要

实际更新后输出：

- commit 范围
- 更新 Wiki 数
- 新建 Wiki 数（含置信度和放置路径）
- 扩展已有页面数
- 需人工判断的新功能数
- 删除引用数
- 更新引用数
- 需要人工审核的 Wiki 列表（含新建页面）
- 是否已同步 `metadata.json`
