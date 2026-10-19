#!/usr/bin/env bash
# ==============================================================================
# OpenInk 汉王 N516 (OpenInkpot) 守护进程一次性持久化安装脚本
# ==============================================================================
# 作用：
#   通过单次 SSH 管道（兼容无 sftp-server 的精简 Dropbear）将守护进程与自启钩子
#   一次性写入 N516 的 NAND Flash 持久化分区：
#   - /usr/local/bin/openink-agent.sh        (主守护进程，启动时自动在 /tmp 生成按键二进制块)
#   - /etc/network/if-up.d/openink-agent     (USB 网络接通时自动拉起)
#   - /etc/network/if-down.d/openink-agent   (USB 网络断开时自动停止休眠省电)
#   - /etc/X11/Xsession.d/98openink-agent    (设备冷启动进入 X11 后自动检测并拉起)
#   - /etc/keys/madeye.ini                   (确保 space/Return 全屏与上下键翻页映射就绪)
# ==============================================================================

set -e

TARGET="${1:-n516}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[1/3] 正在打包并写入持久化守护进程与自启钩子至 $TARGET ..."
cat "$SCRIPT_DIR/openink-agent.sh" | ssh "$TARGET" "cat > /usr/local/bin/openink-agent.sh"
cat "$SCRIPT_DIR/if-up-openink-agent" | ssh "$TARGET" "cat > /etc/network/if-up.d/openink-agent"
cat "$SCRIPT_DIR/if-down-openink-agent" | ssh "$TARGET" "cat > /etc/network/if-down.d/openink-agent"
cat "$SCRIPT_DIR/98openink-agent" | ssh "$TARGET" "cat > /etc/X11/Xsession.d/98openink-agent"

echo "[2/3] 正在配置权限、按键映射并启动 N516 上的 openink-agent 守护进程 ..."
ssh "$TARGET" '
chmod +x /usr/local/bin/openink-agent.sh \
         /etc/network/if-up.d/openink-agent \
         /etc/network/if-down.d/openink-agent \
         /etc/X11/Xsession.d/98openink-agent

cat > /etc/keys/madeye.ini << "EOF"
[default]
Left=PREV_IMAGE
Right=NEXT_IMAGE
Up=PREV_IMAGE
Down=NEXT_IMAGE
Prior=PREV_IMAGE
Next=NEXT_IMAGE
space=FULLSCREEN
Return=FULLSCREEN
Escape=QUIT
EOF
sync

if [ -f /tmp/openink-agent.pid ]; then
    OLD_PID=$(cat /tmp/openink-agent.pid 2>/dev/null)
    [ -n "$OLD_PID" ] && kill "$OLD_PID" 2>/dev/null || true
    rm -f /tmp/openink-agent.pid
fi
DISPLAY=:0 /usr/local/bin/openink-agent.sh >/dev/null 2>&1 &
sleep 2
ps | grep -E "openink-agent|madeye|wget" | grep -v grep || true
'

echo "[3/3] 安装完成！所有文件已写入 NAND Flash 持久化目录，N516 重启后完全自动生效。"
