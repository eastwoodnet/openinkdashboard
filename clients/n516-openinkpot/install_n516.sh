#!/usr/bin/env bash
# ==============================================================================
# OpenInk 汉王 N516 (OpenInkpot) 守护进程一次性持久化安装脚本
# ==============================================================================
# 作用：
#   通过 scp -O (兼容无 sftp-server 的 Dropbear) 将守护进程与自启钩子
#   写入 N516 的 NAND Flash 持久化分区：
#   - /usr/local/bin/openink-agent.sh        (主守护进程，启动时自动在 /tmp 生成按键二进制块)
#   - /etc/inittab                           (BusyBox init 原生守护，崩溃/断网/异常自动重生)
#   - /etc/network/if-up.d/openink-agent     (USB 网络接通辅助拉起)
#   - /etc/network/if-down.d/openink-agent   (USB 网络断开自愈钩子)
#   - /etc/X11/Xsession.d/98openink-agent    (设备冷启动进入 X11 后自动检测并拉起)
#   - /etc/keys/madeye.ini                   (确保 space/Return 全屏与上下键翻页映射就绪)
# ==============================================================================

set -e

TARGET="${1:-n516}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[1/2] 正在复制守护脚本与钩子至 $TARGET ..."
scp -O "$SCRIPT_DIR/openink-agent.sh" "$TARGET:/usr/local/bin/openink-agent.sh"
scp -O "$SCRIPT_DIR/if-up-openink-agent" "$TARGET:/etc/network/if-up.d/openink-agent"
scp -O "$SCRIPT_DIR/if-down-openink-agent" "$TARGET:/etc/network/if-down.d/openink-agent"
scp -O "$SCRIPT_DIR/98openink-agent" "$TARGET:/etc/X11/Xsession.d/98openink-agent"

echo "[2/2] 正在配置自启、按键映射并让 BusyBox init 接管常驻守护 ..."
ssh -T "$TARGET" sh << 'REMOTE_SCRIPT'
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

# 写入 BusyBox /etc/inittab 自动常驻守护（无论断网重连、异常还是冷重启均能自动拉起）
if ! grep -q "openink-agent.sh" /etc/inittab; then
    echo "::respawn:/usr/local/bin/openink-agent.sh" >> /etc/inittab
fi

sync

# 清理历史孤儿 wget 与旧守护进程
killall -9 wget 2>/dev/null || true
if [ -f /tmp/openink-agent.pid ]; then
    OLD_PID=$(cat /tmp/openink-agent.pid 2>/dev/null)
    [ -n "$OLD_PID" ] && kill -9 "$OLD_PID" 2>/dev/null || true
    rm -f /tmp/openink-agent.pid
fi
killall -9 openink-agent.sh 2>/dev/null || true

# 异步通知 BusyBox init 重载 inittab 并接管常驻守护（防止断开 SSH 会话）
(sleep 1 && kill -HUP 1) >/dev/null 2>&1 &

sleep 1
ps | grep -E "openink-agent|madeye|wget" | grep -v grep || true
REMOTE_SCRIPT

echo "==> 安装完成！所有文件已写入 NAND Flash 持久化目录，由 BusyBox init 自动常驻守护。"
