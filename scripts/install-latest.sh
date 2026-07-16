#!/usr/bin/env bash
# ============================================================
# CodeToWiki 安装脚本（安装 GitHub Release 上的最新版本）
# 从 GitHub Release 获取 codetowiki 最新 wheel 并通过 uv 安装
#
# 用法:
# ./scripts/install-latest.sh            # 安装最新正式版
# ./scripts/install-latest.sh --pre      # 允许安装预发布版
# ./scripts/install-latest.sh --help     # 查看帮助
#
# 环境变量:
# REPO=owner/repo        手动指定 GitHub 仓库（默认从 git remote 推断，
#                        失败则回退到 HACK-WU/CodeToWiki-）
# GITHUB_TOKEN=xxx       提供后用于 GitHub API 鉴权，缓解未登录时的限流
# INSTALL_METHOD=uv|pip  强制指定安装后端（默认 uv，未安装则回退 pip）
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PKG_NAME="codetowiki"
PKG_CMD="codetowiki"          # 安装后用于校验版本的命令
DEFAULT_REPO="HACK-WU/CodeToWiki-"
INCLUDE_PRE="false"
INSTALL_METHOD="${INSTALL_METHOD:-}"

usage() {
  cat <<EOF
用法: $0 [选项]

从 GitHub Release 安装 ${PKG_NAME} 的最新版本。

选项:
  --pre           允许安装预发布版本（默认只安装正式版）
  --help, -h      显示本帮助并退出

环境变量:
  REPO=owner/repo           覆盖 GitHub 仓库（默认从 git remote 推断）
  GITHUB_TOKEN=xxx          用于 GitHub API 鉴权（缓解限流）
  INSTALL_METHOD=uv|pip     强制指定安装后端（默认 uv，回退 pip）

示例:
  $0
  $0 --pre
  REPO=ACME/codetowiki $0
EOF
}

# ────────────────────────────────────────────────────────────
# 参数解析
# ────────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --pre)       INCLUDE_PRE="true" ;;
    --help|-h)   usage; exit 0 ;;
    *)           echo "错误: 未知参数 '$arg'" >&2; usage >&2; exit 1 ;;
  esac
done

# ────────────────────────────────────────────────────────────
# 推断 GitHub 仓库（owner/repo），支持环境变量覆盖
# ────────────────────────────────────────────────────────────
detect_repo() {
  local url
  # 锚定脚本自身目录推断，避免从其他 git 仓库的 cwd 误推断
  url="$(git -C "$SCRIPT_DIR" remote get-url origin 2>/dev/null || true)"
  if [ -z "$url" ]; then
    local first
    first="$(git -C "$SCRIPT_DIR" remote 2>/dev/null | head -1)"
    if [ -n "$first" ]; then
      url="$(git -C "$SCRIPT_DIR" remote get-url "$first" 2>/dev/null || true)"
    fi
  fi
  [ -z "$url" ] && { printf '%s' "$DEFAULT_REPO"; return; }
  local cleaned="${url%.git}"
  cleaned="$(printf '%s' "$cleaned" | sed -E 's#.*github\.com[/:]##')"
  printf '%s' "$cleaned"
}

REPO="${REPO:-$(detect_repo)}"
if ! printf '%s' "$REPO" | grep -Eq '^[^/]+/[^/]+$'; then
  echo "错误: 无法推断 REPO（得到 '$REPO'），请设置环境变量 REPO=owner/repo" >&2
  exit 1
fi

API_URL="https://api.github.com/repos/${REPO}/releases"

# 带可选鉴权的 GitHub API 请求（GITHUB_TOKEN 非空时附带 Authorization 头）
curl_api() {
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    curl -fsSL --header "Authorization: Bearer ${GITHUB_TOKEN}" "$API_URL"
  else
    curl -fsSL "$API_URL"
  fi
}

echo "==> 安装 ${PKG_NAME}（最新版本）"
echo " GitHub 仓库: ${REPO}"
echo " 包含预发布:  ${INCLUDE_PRE}"
echo ""

# ────────────────────────────────────────────────────────────
# 检查当前已安装版本
# ────────────────────────────────────────────────────────────
CURRENT_VERSION=""
if command -v "$PKG_CMD" >/dev/null 2>&1; then
  # 优先用 --version；失败则回退到 importlib.metadata
  if "$PKG_CMD" --version >/dev/null 2>&1; then
    CURRENT_VERSION="$("$PKG_CMD" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.]+)?' | head -1)"
  fi
  if [ -z "$CURRENT_VERSION" ]; then
    CURRENT_VERSION="$(python3 -c "import importlib.metadata as m; print(m.version('${PKG_NAME}'))" 2>/dev/null || true)"
  fi
fi
if [ -n "$CURRENT_VERSION" ]; then
  echo "==> 当前已安装版本: ${CURRENT_VERSION}"
else
  echo "==> 当前未安装 ${PKG_NAME}"
fi

# ────────────────────────────────────────────────────────────
# 获取最新 Release（多级降级容错）
# 输出 3 行: <version> <tag> <wheel_download_url>
# ────────────────────────────────────────────────────────────
get_latest_via_api() {
  curl_api 2>/dev/null | python3 -c '
import sys, json
pre = (sys.argv[1] == "true") if len(sys.argv) > 1 else False
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
for r in data:
    if r.get("draft"):
        continue
    if r.get("prerelease") and not pre:
        continue
    tag = r.get("tag_name", "")
    if not tag.startswith("v"):
        continue
    ver = tag[1:]
    for a in r.get("assets", []):
        name = a.get("name", "")
        if name.startswith("codetowiki-") and name.endswith(".whl"):
            print(ver)
            print(tag)
            print(a.get("browser_download_url", ""))
            sys.exit(0)
sys.exit(1)
' "$INCLUDE_PRE"
}

get_latest_via_gh() {
  command -v gh >/dev/null 2>&1 || return 1
  gh auth status >/dev/null 2>&1 || return 1
  local tag
  tag="$(gh release list --repo "$REPO" --limit 100 \
    --json tagName,isPrerelease \
    | python3 -c '
import sys, json
pre = (sys.argv[1] == "true") if len(sys.argv) > 1 else False
try:
    rows = json.load(sys.stdin)
except Exception:
    sys.exit(1)
for r in rows:
    if r.get("isPrerelease") and not pre:
        continue
    if r.get("tagName", "").startswith("v"):
        print(r["tagName"]); break
' "$INCLUDE_PRE" 2>/dev/null | head -1)"
  [ -n "$tag" ] || return 1
  local url
  url="$(gh release view "$tag" --repo "$REPO" --json assets \
    --jq '.assets[] | select(.name | startswith("codetowiki-") and endswith(".whl")) | .browser_download_url' 2>/dev/null | head -1)"
  [ -n "$url" ] || return 1
  echo "${tag#v}"
  echo "$tag"
  echo "$url"
}

get_latest_via_grep() {
  local body tag url
  body="$(curl_api 2>/dev/null)" || return 1
  # 朴素解析（最后兜底，不区分预发布/草稿）：取第一个 codetowiki-*.whl 直链
  url="$(printf '%s' "$body" | grep -oE '"browser_download_url":\s*"https://[^"]*codetowiki-[^"]*\.whl"' \
    | head -1 | sed -E 's/.*"browser_download_url":\s*"([^"]+)".*/\1/')"
  [ -n "$url" ] || return 1
  tag="$(printf '%s' "$url" | sed -E 's#.*/download/([^/]+)/.*#\1#')"
  [ -n "$tag" ] || return 1
  echo "${tag#v}"
  echo "$tag"
  echo "$url"
}

LATEST_VERSION=""
LATEST_TAG=""
DOWNLOAD_URL=""

# 每个解析函数成功时向 stdout 输出 3 行: <version> <tag> <wheel_url>
# 仅调用一次，避免重复请求 GitHub API 触发限流。
fetch_latest() {
  local raw
  if raw="$(get_latest_via_api)"; then
    :
  elif raw="$(get_latest_via_gh)"; then
    :
  elif raw="$(get_latest_via_grep)"; then
    :
  else
    return 1
  fi
  LATEST_VERSION="$(printf '%s' "$raw" | sed -n '1p')"
  LATEST_TAG="$(printf '%s' "$raw" | sed -n '2p')"
  DOWNLOAD_URL="$(printf '%s' "$raw" | sed -n '3p')"
}

if ! fetch_latest; then
  echo "错误: 未找到合规的 Release 或 wheel 资产（仓库: ${REPO}）" >&2
  echo "可检查: GitHub API 限流（设置 GITHUB_TOKEN）、网络连通性或仓库是否已有 Release。" >&2
  exit 1
fi

if [ -z "$LATEST_VERSION" ] || [ -z "$DOWNLOAD_URL" ]; then
  echo "错误: 未找到合规的 Release 或 wheel 资产（仓库: ${REPO}）" >&2
  echo "可检查: GitHub API 限流（设置 GITHUB_TOKEN）、网络连通性或仓库是否已有 Release。" >&2
  exit 1
fi

echo "==> 最新版本: ${LATEST_VERSION} (tag ${LATEST_TAG})"
echo " 下载链接: ${DOWNLOAD_URL}"

# ────────────────────────────────────────────────────────────
# 若已是最新，跳过安装
# ────────────────────────────────────────────────────────────
if [ -n "$CURRENT_VERSION" ] && [ "$CURRENT_VERSION" = "$LATEST_VERSION" ]; then
  echo ""
  echo "==> 已是最新版本 (${CURRENT_VERSION})，无需更新。"
  exit 0
fi

# ────────────────────────────────────────────────────────────
# 安装
# ────────────────────────────────────────────────────────────
do_install() {
  if [ -z "$INSTALL_METHOD" ] && command -v uv >/dev/null 2>&1; then
    INSTALL_METHOD="uv"
  elif [ -z "$INSTALL_METHOD" ]; then
    INSTALL_METHOD="pip"
  fi

  if [ "$INSTALL_METHOD" = "uv" ]; then
    echo "==> 使用 uv 安装（强制覆盖已装版本）..."
    if command -v uv >/dev/null 2>&1; then
      uv tool install --force "$DOWNLOAD_URL"
    else
      echo "错误: 未找到 uv，但 INSTALL_METHOD=uv" >&2
      return 1
    fi
  else
    echo "==> 使用 pip 安装（--user --upgrade --force-reinstall）..."
    if command -v pip3 >/dev/null 2>&1; then
      pip3 install --user --upgrade --force-reinstall "$DOWNLOAD_URL"
    elif command -v pip >/dev/null 2>&1; then
      pip install --user --upgrade --force-reinstall "$DOWNLOAD_URL"
    else
      echo "错误: 未找到 pip" >&2
      return 1
    fi
  fi
}

if ! do_install; then
  echo "错误: 安装失败" >&2
  exit 1
fi

# ────────────────────────────────────────────────────────────
# 验证
# ────────────────────────────────────────────────────────────
echo ""
echo "==> 验证安装..."
if command -v "$PKG_CMD" >/dev/null 2>&1; then
  INSTALLED_VER="$("$PKG_CMD" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.]+)?' | head -1)"
  if [ -n "$INSTALLED_VER" ]; then
    echo " ✅ 安装成功: ${PKG_NAME} ${INSTALLED_VER}"
  else
    echo " ✅ ${PKG_CMD} 已在 PATH 中（未能解析版本号，请手动确认）"
  fi
  echo " 运行 '${PKG_CMD} --help' 查看可用命令"
  echo " 可选：安装加速等可选依赖 → pip install '${PKG_NAME}[fast]'"
else
  echo " ⚠️ 未检测到 ${PKG_CMD} 命令在 PATH 中。"
  echo " 若使用 uv 安装，请确认 ~/.local/bin（或 uv 的 bin 目录）已加入 PATH；"
  echo " 或运行: uv tool install --force \"${DOWNLOAD_URL}\""
fi
