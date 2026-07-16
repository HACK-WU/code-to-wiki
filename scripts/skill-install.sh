#!/usr/bin/env bash
# ============================================================
# CodeToWiki Skill 安装器 — 从远程仓库下载 Skills 并复制到目标项目
#
# 与上游 HACK-WU/skills 的 skill-install.sh 行为一致，仅支持
# --skills 模式（不含 --rules）。**默认从远程仓库下载 skills/**
# （与上游一致：Skills 本就是远程分发的，不具备本地复制能力），
# 仅当显式设置 SKILLS_SRC 且为有效目录时，才改用本地目录（开发者覆盖）。
#
# 用法:
#   bash scripts/skill-install.sh --skills -t /path/to/target
#   bash scripts/skill-install.sh --skills -t /p1 -t /p2
#   bash scripts/skill-install.sh --skills -n code-to-wiki -t ~/app
#   bash scripts/skill-install.sh --skills --file ~/targets.txt
#   bash scripts/skill-install.sh /path/to/target            # 兼容简写（默认按 skills）
#
# 也支持 curl|bash 一键安装:
#   curl -fsSL https://raw.githubusercontent.com/HACK-WU/CodeToWiki/master/scripts/skill-install.sh \
#     | bash -s -- --skills -t /path/to/target
#
# 环境变量:
#   SKILLS_SRC   可选：覆盖为本地源 skills 目录（默认从远程下载，不依赖本地）
#   REPO         远程仓库 owner/repo（默认: HACK-WU/CodeToWiki）
#   REF          远程分支/标签（默认: master）
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# 源 skills 目录：默认留空，稍后在父 shell 中解析为远程下载；
# 仅当显式设置 SKILLS_SRC 且为有效目录时改用本地（开发者覆盖）。
SOURCE_SKILLS_DIR="${SKILLS_SRC:-}"
DEFAULT_TARGETS="$HOME/.skill-targets"

POSITIONAL_TARGET=""
TARGETS=()
CONFIG_FILE=""
MODES=()
NAME_FILTER=""

# ============================================================
# 参数解析
# ============================================================
while [ $# -gt 0 ]; do
  arg="$1"
  case "$arg" in
    --skills) MODES+=("skills") ;;
    --rules)  echo "错误: --rules 暂不支持（本项目仅分发 Skills）" >&2; exit 1 ;;
    -t) shift; [ $# -eq 0 ] && { echo "错误: -t 需要参数" >&2; exit 1; }; TARGETS+=("$1") ;;
    --file) shift; [ $# -eq 0 ] && { echo "错误: --file 需要参数" >&2; exit 1; }; CONFIG_FILE="$1" ;;
    --file=*) CONFIG_FILE="${arg#*=}" ;;
    -n) shift; [ $# -eq 0 ] && { echo "错误: -n 需要参数" >&2; exit 1; }; NAME_FILTER="${NAME_FILTER:+$NAME_FILTER,}$1" ;;
    --all|--docs) echo "错误: ${arg} 已废弃" >&2; exit 1 ;;
    -*) echo "未知选项: $arg" >&2; exit 1 ;;
    *) POSITIONAL_TARGET="$arg" ;;
  esac
  shift
done

# 互斥检查
if [ ${#TARGETS[@]} -gt 0 ] && [ -n "$CONFIG_FILE" ]; then
  echo "错误: -t 和 --file 不能同时使用" >&2
  exit 1
fi

# ============================================================
# 解析目标目录
# ============================================================
if [ ${#TARGETS[@]} -gt 0 ]; then
  TARGET_DIRS=("${TARGETS[@]}")
  SOURCE_DESC="命令行参数 (-t × ${#TARGET_DIRS[@]})"
elif [ -n "$CONFIG_FILE" ]; then
  [ -f "$CONFIG_FILE" ] || { echo "错误: 配置文件不存在: $CONFIG_FILE" >&2; exit 1; }
  TARGET_DIRS=()
  while IFS= read -r line; do
    line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -z "$line" ] && continue
    [[ "$line" =~ ^# ]] && continue
    TARGET_DIRS+=("$line")
  done < "$CONFIG_FILE"
  [ ${#TARGET_DIRS[@]} -eq 0 ] && { echo "错误: 配置文件为空: $CONFIG_FILE" >&2; exit 1; }
  SOURCE_DESC="配置文件: $CONFIG_FILE"
elif [ ${#MODES[@]} -gt 0 ]; then
  # 模式特定的默认配置文件
  TARGET_DIRS=()
  if [ -f "$DEFAULT_TARGETS" ]; then
    while IFS= read -r line; do
      line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      [ -z "$line" ] && continue
      [[ "$line" =~ ^# ]] && continue
      found=0
      if [ ${#TARGET_DIRS[@]} -gt 0 ]; then
        for existing in "${TARGET_DIRS[@]}"; do
          [ "$existing" = "$line" ] && { found=1; break; }
        done
      fi
      [ "$found" -eq 0 ] && TARGET_DIRS+=("$line")
    done < "$DEFAULT_TARGETS"
  fi
  [ ${#TARGET_DIRS[@]} -gt 0 ] && SOURCE_DESC="默认配置 ($DEFAULT_TARGETS)"
elif [ -n "$POSITIONAL_TARGET" ]; then
  TARGET_DIRS=("$POSITIONAL_TARGET")
  SOURCE_DESC="位置参数"
else
  TARGET_DIRS=()
fi

# 本项目仅分发 Skills：未显式指定 --skills 但提供了目标时，默认按 skills 处理
if [ ${#MODES[@]} -eq 0 ] && [ ${#TARGET_DIRS[@]} -gt 0 ]; then
  MODES=("skills")
fi

if [ ${#TARGET_DIRS[@]} -eq 0 ] || [ ${#MODES[@]} -eq 0 ]; then
  if [ -n "$NAME_FILTER" ] && [ ${#MODES[@]} -eq 0 ]; then
    echo "错误: -n 参数必须配合 --skills 使用" >&2
  fi
  echo "用法: bash scripts/skill-install.sh [--skills] [-t ... | --file ...]" >&2
  echo "" >&2
  echo "  --skills   安装 AI Skill 定义（复制到目标项目的 skills/）" >&2
  echo "  -n         指定要安装的 skill 名称（逗号分隔或多次使用）" >&2
  echo "  -t         指定目标目录（可多次使用，与 --file 互斥）" >&2
  echo "  --file     指定目标目录配置文件（与 -t 互斥，每行一个路径）" >&2
  echo "" >&2
  echo "示例:" >&2
  echo "  bash scripts/skill-install.sh --skills -t ~/projects/app" >&2
  echo "  bash scripts/skill-install.sh --skills -n code-to-wiki -t ~/projects/app" >&2
  echo "  bash scripts/skill-install.sh --skills --file ~/my-targets.txt" >&2
  echo "" >&2
  echo "默认配置文件（不指定 -t / --file 时自动读取）:" >&2
  echo "  --skills → $DEFAULT_TARGETS" >&2
  exit 1
fi

# ============================================================
# 通用函数
# ============================================================
copy_file() {
  local src="$1" dest="$2"
  mkdir -p "$(dirname "$dest")"
  if cp -f "$src" "$dest" 2>/dev/null; then
    return 0
  fi
  rm -f "$dest" 2>/dev/null
  return 1
}

# 解析名称过滤器
if [ -n "$NAME_FILTER" ]; then
  IFS=',' read -ra NAME_LIST <<< "$NAME_FILTER"
  for i in "${!NAME_LIST[@]}"; do
    NAME_LIST[$i]="$(echo "${NAME_LIST[$i]}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  done
else
  NAME_LIST=()
fi

# 检查名称是否在过滤列表中（空列表表示全部匹配）
name_matches() {
  local name="$1"
  [ ${#NAME_LIST[@]} -eq 0 ] && return 0
  for filter_name in "${NAME_LIST[@]}"; do
    [ "$name" = "$filter_name" ] && return 0
  done
  return 1
}

# 递归发现 skills 目录下的文件列表（本地或远程回退后均可用）
# 输出: 每行一个相对路径（如 wiki-incremental-update/SKILL.md）
discover_skills() {
  if [ ! -d "$SOURCE_SKILLS_DIR" ]; then
    echo "错误: 源 skills 目录不存在: $SOURCE_SKILLS_DIR" >&2
    return 1
  fi
  ( cd "$SOURCE_SKILLS_DIR" && find . -type f | sed 's#^\./##' )
}

# 本地 skills 目录缺失时（典型场景: curl|bash 管道运行），
# 从 GitHub 下载仓库 tarball 并解压出 skills/ 作为源。
fetch_remote_skills() {
  local repo="${REPO:-HACK-WU/CodeToWiki}"
  local ref="${REF:-master}"
  local tar_url="https://github.com/${repo}/archive/refs/heads/${ref}.tar.gz"
  local tmp
  tmp="$(mktemp -d)"
  echo "本地 skills 目录缺失，改从远程下载: ${repo}@${ref}" >&2

  if ! curl -fsSL "$tar_url" -o "$tmp/repo.tgz" 2>/dev/null; then
    tar_url="https://github.com/${repo}/archive/${ref}.tar.gz"
    curl -fsSL "$tar_url" -o "$tmp/repo.tgz" 2>/dev/null \
      || { echo "错误: 远程下载失败: $tar_url" >&2; rm -rf "$tmp"; exit 1; }
  fi

  tar -xzf "$tmp/repo.tgz" -C "$tmp" 2>/dev/null \
    || { echo "错误: 远程 tarball 解压失败: $tar_url" >&2; rm -rf "$tmp"; exit 1; }

  local extracted
  extracted="$(find "$tmp" -maxdepth 1 -type d -name '*-*' | head -n1)"
  if [ -z "$extracted" ] || [ ! -d "$extracted/skills" ]; then
    echo "错误: 远程 tarball 中未找到 skills/ 目录" >&2
    rm -rf "$tmp"
    exit 1
  fi
  # 仅本行作为返回值（stdout）被调用方捕获，进度信息一律走 stderr
  echo "$extracted/skills"
}

# ============================================================
# --skills: 将本项目内置 Skills 复制到目标项目
# ============================================================
install_skills() {
  if [ "${NORMALIZED_DIR##*/}" = "skills" ]; then
    DEST="$NORMALIZED_DIR"
  else
    DEST="$NORMALIZED_DIR/skills"
  fi
  mkdir -p "$DEST"

  local FILES=()
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    FILES+=("$f")
  done < <(discover_skills)

  echo "🧠 安装 AI Skills → ${DEST}"
  echo ""

  local file_count=0 skipped=0 installed_skill_dirs=0
  local skill_names_all=() _sn_fail=() _sn_installed=()

  for f in "${FILES[@]}"; do
    # 提取 skill 名称用于过滤（取第一级目录名）
    local skill_name="${f%%/*}"
    # 记录 skill 目录（去重）并初始化失败计数
    local found=0 i=0
    for sn in "${skill_names_all[@]}"; do
      [ "$sn" = "$skill_name" ] && { found=1; break; }
      i=$((i + 1))
    done
    if [ "$found" -eq 0 ]; then
      skill_names_all+=("$skill_name")
      _sn_fail+=(0)
      _sn_installed+=(0)
    fi

    if ! name_matches "$skill_name"; then
      continue
    fi

    local src="$SOURCE_SKILLS_DIR/$f"
    local dest="$DEST/$f"
    if copy_file "$src" "$dest"; then
      echo " [OK] ${f}"
      file_count=$((file_count + 1))
      # 首次成功安装该 skill 目录时计入覆盖数
      local si=0
      for sn in "${skill_names_all[@]}"; do
        if [ "$sn" = "$skill_name" ]; then
          if [ "${_sn_installed[$si]}" -eq 0 ]; then
            _sn_installed[$si]=1
            installed_skill_dirs=$((installed_skill_dirs + 1))
          fi
          break
        fi
        si=$((si + 1))
      done
    else
      echo " [FAIL] ${f}"
      local fi_idx=0
      for sn in "${skill_names_all[@]}"; do
        [ "$sn" = "$skill_name" ] && { _sn_fail[$fi_idx]=$((${_sn_fail[$fi_idx]} + 1)); break; }
        fi_idx=$((fi_idx + 1))
      done
    fi
  done

  # 统计跳过的 skill 数（目录级）
  for sn in "${skill_names_all[@]}"; do
    name_matches "$sn" || skipped=$((skipped + 1))
  done
  [ $skipped -gt 0 ] && echo " 跳过: ${skipped} 个未匹配的 skill"

  # 输出不完整 skill 的警告（存在复制失败文件的 skill）
  local _warned=0 _wi=0
  for sn in "${skill_names_all[@]}"; do
    if name_matches "$sn" && [ "${_sn_fail[$_wi]}" -gt 0 ]; then
      [ $_warned -eq 0 ] && { echo ""; echo "⚠️ 以下 skill 存在复制失败的文件："; }
      echo " - ${sn}: ${_sn_fail[$_wi]} 个文件失败"
      _warned=1
    fi
    _wi=$((_wi + 1))
  done

  echo ""
  echo "已安装: ${file_count} 个文件（覆盖 ${installed_skill_dirs} 个 skill 目录）"
  if [ $file_count -gt 0 ]; then ANY_INSTALLED=1; fi
}

# ============================================================
# 按模式执行（支持多目标目录）
# ============================================================
echo "🚀 skill-install.sh"
echo " 目标来源:  ${SOURCE_DESC}"
echo " 目标数量:  ${#TARGET_DIRS[@]}"
echo " 安装模式:  ${MODES[*]}"
[ ${#NAME_LIST[@]} -gt 0 ] && echo " 名称过滤:  $(IFS=', '; echo "${NAME_LIST[*]}")"
echo ""

# 源 skills 目录解析：默认从远程仓库 tarball 下载；仅当显式设置
# SKILLS_SRC 且为有效目录时，才使用本地目录（开发者覆盖）。
# 远程下载在父 shell 中执行，失败会真实报错退出，不会静默"完成"。
if [ -n "$SOURCE_SKILLS_DIR" ] && [ -d "$SOURCE_SKILLS_DIR" ]; then
  echo "（使用本地源 skills: ${SOURCE_SKILLS_DIR}）"
else
  SOURCE_SKILLS_DIR="$(fetch_remote_skills)"
fi

ANY_INSTALLED=0
for i in "${!TARGET_DIRS[@]}"; do
  TARGET_DIR="${TARGET_DIRS[$i]}"
  LABEL="[$(($i + 1))/${#TARGET_DIRS[@]}]"
  if [ ! -d "$TARGET_DIR" ]; then
    echo "${LABEL} 创建目标目录: $TARGET_DIR"
    mkdir -p "$TARGET_DIR"
  fi
  NORMALIZED_DIR="${TARGET_DIR%/}"
  for mode in "${MODES[@]}"; do
    case "$mode" in
      skills) install_skills ;;
    esac
    echo ""
  done
done

echo ""
if [ $ANY_INSTALLED -eq 0 ] && [ ${#NAME_LIST[@]} -gt 0 ]; then
  echo "⚠️ 未找到匹配的项，请检查名称是否正确" >&2
  exit 1
fi
echo "✅ 完成"
