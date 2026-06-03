#!/usr/bin/env bash
# install.sh - 一键安装 obsidian-personal-todo-tracker (V1.0)
#
# 学 finance track V1.3.4 install.sh 模式:
# - --dry-run 支持 (打印预期行为, 不真改文件)
# - MD5 校验 (config/ 跟 vault 端副本必须一致)
# - 软告警: 文件已存在时不覆盖, 让用户确认
# - 退出码: 0=成功, 1=致命错误, 2=用户已存在文件需要确认
#
# 用法:
#   bash install.sh --dry-run          # 打印将做什么
#   bash install.sh                    # 真装
#   bash install.sh --force            # 覆盖已存在文件
#   bash install.sh --vault PATH       # 自定义 vault 路径 (默认 ~/Obsidian/todo)

set -euo pipefail

# ============================================================
# 配置
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# V1.0.3: 兼容两种跑法
#   1) install.sh 在 skill 目录 (aweskill install 后的实际场景):
#      $SCRIPT_DIR = ~/.aweskill/skills/obsidian-todo-track/
#      scripts/config/plist 都在 SCRIPT_DIR 下
#   2) install.sh 在仓库根 (开发调试场景, V1.0 旧假设):
#      $SCRIPT_DIR = ~/Project/obsidian-personal-todo-tracker/
#      scripts/config/plist 在 skills/obsidian-todo-track/ 下
# 优先用 (1) 跑法, 找不到再回退 (2)
if [[ -d "$SCRIPT_DIR/scripts" ]] && [[ -d "$SCRIPT_DIR/config" ]]; then
    SKILL_DIR="$SCRIPT_DIR"
    REPO_ROOT="$SCRIPT_DIR/.."
elif [[ -d "$SCRIPT_DIR/skills/obsidian-todo-track/scripts" ]]; then
    SKILL_DIR="$SCRIPT_DIR/skills/obsidian-todo-track"
    REPO_ROOT="$SCRIPT_DIR"
else
    echo "❌ ERROR: 找不到 scripts/ 目录" >&2
    echo "   试过: $SCRIPT_DIR/scripts (aweskill 装完后应该有)" >&2
    echo "   试过: $SCRIPT_DIR/skills/obsidian-todo-track/scripts (仓库根跑应该这样)" >&2
    echo "   请确认 install.sh 跑在 aweskill 装完的 skill 目录, 或仓库根" >&2
    exit 1
fi
DEFAULT_VAULT="$HOME/Obsidian/todo"
VAULT="${VAULT:-$DEFAULT_VAULT}"
DRY_RUN=0
FORCE=0

# 要 cp 的文件 (相对 skill 目录)
CONFIG_SRC="$SKILL_DIR/config/default_priorities.yaml"

# ============================================================
# 参数解析
# ============================================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --force)
            FORCE=1
            shift
            ;;
        --install-plist)
            INSTALL_PLIST=1
            export INSTALL_PLIST
            shift
            ;;
        --vault)
            VAULT="$2"
            shift 2
            ;;
        --vault=*)
            VAULT="${1#*=}"
            shift
            ;;
        -h|--help)
            cat <<'EOF'
install.sh - 一键安装 obsidian-personal-todo-tracker (V1.0.3)

用法:
    bash install.sh --dry-run          打印将做什么, 不真改
    bash install.sh                    真装 (已存在文件会跳过并告警)
    bash install.sh --force            覆盖已存在文件
    bash install.sh --vault PATH       自定义 vault 路径
    bash install.sh --install-plist    装 3 段 launchd plist + launchctl load
    bash install.sh -h                 显示帮助

支持从两种位置跑:
    1) skill 目录 (aweskill install 完后): ~/.aweskill/skills/obsidian-todo-track/
    2) 仓库根 (开发调试): ~/Project/obsidian-personal-todo-tracker/

环境变量:
    VAULT    等价于 --vault, 优先级: --vault > $VAULT > ~/Obsidian/todo
EOF
            exit 0
            ;;
        *)
            echo "ERROR: 未知参数: $1" >&2
            echo "跑 'bash install.sh -h' 看帮助" >&2
            exit 2
            ;;
    esac
done

# 参数解析完后才能用 $VAULT
CONFIG_DST="$VAULT/default_priorities.yaml"
REQUIRED_DIRS=(
    "$VAULT"
    "$VAULT/ACTIVE"
    "$VAULT/DONE"
    "$VAULT/BLOCKED"
    "$VAULT/SNOOZED"
    "$VAULT/CANCELED"
)

# ============================================================
# 工具函数
# ============================================================

log() {
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "[DRY-RUN] $*"
    else
        echo "$*"
    fi
}

warn() {
    echo "⚠️  $*"
}

err() {
    echo "❌ $*" >&2
}

action_mkdir() {
    local path="$1"
    if [[ -d "$path" ]]; then
        log "目录已存在: $path"
    else
        if [[ $DRY_RUN -eq 1 ]]; then
            log "将创建: $path"
        else
            mkdir -p "$path"
            log "✓ 创建: $path"
        fi
    fi
}

action_cp() {
    local src="$1"
    local dst="$2"
    if [[ ! -f "$src" ]]; then
        err "源文件不存在: $src"
        return 1
    fi
    if [[ -f "$dst" ]] && [[ $FORCE -eq 0 ]]; then
        # 已存在, 不覆盖, 但 MD5 校验
        local src_md5 dst_md5
        src_md5=$(md5 -q "$src" 2>/dev/null || md5sum "$src" | cut -d' ' -f1)
        dst_md5=$(md5 -q "$dst" 2>/dev/null || md5sum "$dst" | cut -d' ' -f1)
        if [[ "$src_md5" == "$dst_md5" ]]; then
            log "文件已存在且 MD5 一致: $dst"
        else
            warn "文件已存在但 MD5 不一致: $dst"
            warn "  src: $src_md5"
            warn "  dst: $dst_md5"
            warn "  加 --force 覆盖, 或手动 'cp $src $dst' 同步"
        fi
        return 2
    fi
    if [[ $DRY_RUN -eq 1 ]]; then
        log "将 cp: $src -> $dst"
    else
        cp "$src" "$dst"
        log "✓ cp: $src -> $dst"
    fi
    return 0
}

# ============================================================
# 主流程
# ============================================================

echo "=========================================="
if [[ $DRY_RUN -eq 1 ]]; then
    echo "  install.sh --dry-run (不真改文件)"
else
    echo "  install.sh (V1.0)"
fi
echo "=========================================="
echo ""
echo "Repo:        $REPO_ROOT"
echo "Skill dir:   $SKILL_DIR"
echo "Vault:       $VAULT"
echo "Dry-run:     $DRY_RUN"
echo "Force:       $FORCE"
echo ""

# 步骤 0: 校验 repo 完整性 (SKILL_DIR 已在上面解析, 这里 sanity check)
if [[ ! -d "$SKILL_DIR/scripts" ]]; then
    err "scripts/ 目录不存在: $SKILL_DIR/scripts"
    err "SKILL_DIR=$SKILL_DIR 解析异常, 这是 install.sh 内部 bug, 请报 issue"
    exit 1
fi

if [[ ! -f "$CONFIG_SRC" ]]; then
    err "config/default_priorities.yaml 不存在: $CONFIG_SRC"
    exit 1
fi

# 步骤 1: 创建 vault 目录
log "=== 步骤 1: 创建 vault 目录 ==="
for dir in "${REQUIRED_DIRS[@]}"; do
    action_mkdir "$dir"
done
echo ""

# 3. cp config 到 vault
log "=== 步骤 2: 复制 config 到 vault 端 ==="
set +e
action_cp "$CONFIG_SRC" "$CONFIG_DST"
cp_exit=$?
set -e
if [[ $cp_exit -eq 2 ]]; then
    # 文件已存在, 已 warn, 继续
    :
fi
echo ""

# 步骤 3: (可选) 装 launchd plist 启用定时主动
if [[ $DRY_RUN -eq 1 ]]; then
    log "=== 步骤 3: 装 launchd plist (DRY-RUN, 不真装) ==="
    if [[ -d "$SKILL_DIR/plist" ]]; then
        for plist in "$SKILL_DIR/plist"/*.plist; do
            plist_name=$(basename "$plist")
            log "将 cp: $plist -> ~/Library/LaunchAgents/$plist_name"
            log "       然后 launchctl load ~/Library/LaunchAgents/$plist_name"
        done
    fi
    echo ""
    log "(跳过 plist 装, 跑 'bash $0 --install-plist' 真装)"
elif [[ "${INSTALL_PLIST:-0}" -eq 1 ]]; then
    log "=== 步骤 3: 装 launchd plist ==="
    if [[ ! -d "$SKILL_DIR/plist" ]]; then
        warn "plist 目录不存在: $SKILL_DIR/plist"
    else
        mkdir -p ~/Library/LaunchAgents
        for plist in "$SKILL_DIR/plist"/*.plist; do
            plist_name=$(basename "$plist")
            dst=~/Library/LaunchAgents/$plist_name
            cp "$plist" "$dst"
            log "✓ cp: $plist -> $dst"
            if launchctl load "$dst" 2>&1; then
                log "✓ launchctl load: $dst"
            else
                warn "launchctl load 失败 (可能已加载), 跑 'launchctl unload $dst' 后重试"
            fi
        done
    fi
    echo ""
fi

# 5. 总结
echo "=========================================="
if [[ $DRY_RUN -eq 1 ]]; then
    echo "  DRY-RUN 完成 (上面是预期行为, 实际未改任何文件)"
else
    echo "  ✅ 安装完成"
fi
echo "=========================================="
echo ""
echo "下一步:"
echo "  1. 编辑 $VAULT/todo-config.md (Agent Onboarding 时生成)"
echo "  2. 跟 Agent 说 '开始用 todo' 触发 Onboarding 7 步"
echo "  3. 跟 Agent 说 '建个 todo 提醒我 X' 创建第一个 todo"
echo ""
echo "启用定时主动 (V1.0.2 新):"
echo "  bash $0 --install-plist                # 装 3 段 plist + launchctl load (从哪跑都行)"
echo "  launchctl list | grep com.todo.        # 验证 3 段都跑起来"
echo "  tail -f /tmp/todo-daily-integrity.log  # 看每天 18:00 跑 daily_check"
echo ""
echo "验证安装:"
echo "  python3 $SKILL_DIR/scripts/validate_todo.py --help"
echo "  python3 $SKILL_DIR/scripts/daily_todo_check.py --vault $VAULT --list-only"
echo ""
echo "V1.0 不做的事 (V1.1+ 才加):"
echo "  - 6 段 plist 模板 (V1.1 真交付, 学 finance track V1.3.4)"
echo "  - weekly_summary.py / monthly_summary.py"
echo "  - en 翻译 / aweskill 同步 / Dataview 仪表盘"
