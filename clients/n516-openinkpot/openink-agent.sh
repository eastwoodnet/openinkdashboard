#!/bin/sh
# ==============================================================================
# OpenInk Universal Pull & Long-Polling Daemon for Hanvon N516 (OpenInkpot)
# ==============================================================================
# 1. 100% 重启安全 (Reboot-Safe)：
#    本身持久化安装在 /usr/local/bin/openink-agent.sh；
#    每次启动时自动在 /tmp/openink_keys/ 生成 64 字节 Linux struct input_event 按键块，
#    彻底解决 /tmp (tmpfs) 重启丢失 enter.bin 的问题。
# 2. 智能省电与电子书休眠感知 (USB Network & Reading Mode Aware)：
#    仅当 USB 网络 (usb0 carrier=1 且 usb online=1) 激活时才启动拉取、长连接与轮播；
#    一旦断开 USB 网络，立即退出后台循环（0% CPU、0 唤醒），让 N516 纯粹作为电子书休眠省电。
# 3. 150ms 无闪原地刷新与自动轮播：
#    采用双缓冲/多页 NEXT_IMAGE 步进机制，绕过 madeye Evas 同名文件内存缓存，
#    无需 killall/重启 madeye 即可在 150ms 内原地无闪切换与更新画面。
# ==============================================================================

SERVER="${OPENINK_SERVER:-http://192.168.111.2:8000}"
DEVICE_ID="${OPENINK_DEVICE_ID:-n516}"
CACHE_DIR="/tmp/openink_cache"
DASH_DIR="/tmp/dashboard"
KEYS_DIR="/tmp/openink_keys"
PID_FILE="/tmp/openink-agent.pid"
LOG_FILE="/tmp/openink-agent.log"
EVENT_DEV="/dev/event0"

# 单实例锁：若已有守护进程存活则直接退出
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null && [ "$OLD_PID" != "$$" ]; then
        exit 0
    fi
fi
echo "$$" > "$PID_FILE"
trap 'rm -f "$PID_FILE"; exit 0' INT TERM EXIT

mkdir -p "$CACHE_DIR" "$DASH_DIR" "$KEYS_DIR"

# ------------------------------------------------------------------------------
# 1. 动态生成 64 字节 MIPS32 little-endian struct input_event 按键注入文件 (重启不丢)
# ------------------------------------------------------------------------------
gen_key_bin() {
    # $1: 十六进制 keycode (例如 39=KEY_SPACE, 1c=KEY_ENTER, 6c=KEY_DOWN, 67=KEY_UP)
    # $2: 输出文件路径
    printf "\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x$1\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x$1\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00" > "$2"
}

ensure_key_bins() {
    [ -s "$KEYS_DIR/fullscreen.bin" ] || gen_key_bin 39 "$KEYS_DIR/fullscreen.bin"
    [ -s "$KEYS_DIR/enter.bin" ]      || gen_key_bin 1c "$KEYS_DIR/enter.bin"
    [ -s "$KEYS_DIR/next.bin" ]       || gen_key_bin 6c "$KEYS_DIR/next.bin"
    [ -s "$KEYS_DIR/prev.bin" ]       || gen_key_bin 67 "$KEYS_DIR/prev.bin"
    # 兼容旧路径 /tmp/enter.bin
    [ -s "/tmp/enter.bin" ]           || cp "$KEYS_DIR/enter.bin" "/tmp/enter.bin"
}

ensure_key_bins

# ------------------------------------------------------------------------------
# 2. USB 网络连接状态检测（未连网时立即休眠退出以省电）
# ------------------------------------------------------------------------------
is_usb_net_online() {
    if [ -f /sys/class/power_supply/usb/online ]; then
        usb_on=$(cat /sys/class/power_supply/usb/online 2>/dev/null)
        [ "$usb_on" = "0" ] && return 1
    fi
    if [ -f /sys/class/net/usb0/carrier ]; then
        carrier=$(cat /sys/class/net/usb0/carrier 2>/dev/null)
        [ "$carrier" = "1" ] && return 0
        return 1
    fi
    ifconfig usb0 2>/dev/null | grep -q "RUNNING" && return 0
    return 1
}

# JSON 字段轻量提取辅助函数
json_str() {
    echo "$1" | tr '{},' '\n' | sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -n 1
}

json_val() {
    echo "$1" | tr '{},' '\n' | sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\([a-z0-9_.-]*\).*/\1/p" | head -n 1
}

# ------------------------------------------------------------------------------
# 3. 操控 madeye 渲染器（启动全屏、原地翻页刷新、阅读模式礼让）
# ------------------------------------------------------------------------------
MADEYE_LAUNCHED_ONCE=0
USER_EXITED_TO_READER=0

ensure_madeye_running() {
    # $1: force_respawn (1=新版本或紧急通知强制唤醒; 0=常规轮询尊重阅读模式)
    FORCE="$1"
    if pidof madeye >/dev/null 2>&1; then
        return 0
    fi
    if [ "$MADEYE_LAUNCHED_ONCE" = "1" ] && [ "$FORCE" != "1" ]; then
        # 用户之前按了 Escape 退出看板看电子书，且没有新通知/新发布，不打扰看书
        USER_EXITED_TO_READER=1
        return 1
    fi
    FIRST_IMG=$(ls "$DASH_DIR"/*.png 2>/dev/null | sort | head -n 1)
    [ -z "$FIRST_IMG" ] && return 1
    DISPLAY=:0 madeye "$FIRST_IMG" >/dev/null 2>&1 &
    MADEYE_LAUNCHED_ONCE=1
    USER_EXITED_TO_READER=0
    sleep 1
    cat "$KEYS_DIR/fullscreen.bin" > "$EVENT_DEV" 2>/dev/null
    return 0
}

trigger_inplace_refresh() {
    # $1: mode ("carousel" 或 "manual")
    # $2: page_count
    MODE="$1"
    PCOUNT="$2"
    ensure_key_bins
    if ! pidof madeye >/dev/null 2>&1; then
        ensure_madeye_running 1
        return
    fi
    if [ "$PCOUNT" -le 1 ]; then
        # 单页模式下 /tmp/dashboard 存有 01_page_1.png 与 02_page_1_dup.png，
        # 注入一次 next.bin 即可在 150ms 内无闪切换至最新图像并释放旧缓存！
        cat "$KEYS_DIR/next.bin" > "$EVENT_DEV" 2>/dev/null
    else
        if [ "$MODE" = "manual" ]; then
            # 多页手动模式下：步进一次再退回，淘汰 Evas 缓存同时保持在当前页码
            cat "$KEYS_DIR/next.bin" > "$EVENT_DEV" 2>/dev/null
            sleep 1
            cat "$KEYS_DIR/prev.bin" > "$EVENT_DEV" 2>/dev/null
        else
            # 多页轮播模式下：直接步进展示最新页面
            cat "$KEYS_DIR/next.bin" > "$EVENT_DEV" 2>/dev/null
        fi
    fi
}

# ------------------------------------------------------------------------------
# 4. 同步服务端 /api/v1/display 清单并按哈希增量拉取 PNG
# ------------------------------------------------------------------------------
LAST_VERSION=""
LAST_ALERT_ACTIVE="false"
LAST_ALERT_HASH=""
CURRENT_MODE="carousel"
CAROUSEL_INTERVAL=60
PAGE_COUNT=1

sync_display() {
    MANIFEST=$(wget -q -T 5 -O - "$SERVER/api/v1/display?device_id=$DEVICE_ID" 2>/dev/null)
    [ -z "$MANIFEST" ] && return 1

    VERSION=$(json_str "$MANIFEST" "version")
    MODE=$(json_str "$MANIFEST" "mode")
    INTERVAL=$(json_val "$MANIFEST" "carousel_interval_sec")

    [ -n "$MODE" ] && CURRENT_MODE="$MODE"
    [ -n "$INTERVAL" ] && CAROUSEL_INTERVAL="$INTERVAL"

    # 解析紧急通知状态
    ALERT_SECTION=$(echo "$MANIFEST" | sed -n 's/.*"alert"[[:space:]]*:[[:space:]]*{\([^}]*\)}.*/\1/p')
    ALERT_ACTIVE=$(json_val "$ALERT_SECTION" "active")
    ALERT_HASH=$(json_str "$ALERT_SECTION" "hash")
    ALERT_URL=$(json_str "$ALERT_SECTION" "url")

    if [ "$ALERT_ACTIVE" = "true" ] && [ -n "$ALERT_URL" ]; then
        if [ "$ALERT_HASH" != "$LAST_ALERT_HASH" ] || [ "$LAST_ALERT_ACTIVE" != "true" ]; then
            if wget -q -T 5 -O "$CACHE_DIR/00_alert.png.tmp" "$ALERT_URL" 2>/dev/null; then
                mv "$CACHE_DIR/00_alert.png.tmp" "$CACHE_DIR/00_alert.png"
                # 覆盖 /tmp/dashboard 为双份 00_alert.png，确保一次 NEXT_IMAGE 即可立即全屏呈现通知
                rm -f "$DASH_DIR"/*.png
                cp "$CACHE_DIR/00_alert.png" "$DASH_DIR/01_page_1.png"
                cp "$CACHE_DIR/00_alert.png" "$DASH_DIR/02_page_1_dup.png"
                trigger_inplace_refresh "carousel" 1
                if [ "$ALERT_HASH" != "$LAST_ALERT_HASH" ]; then
                    aplay -q /usr/share/madaudio/beep.wav >/dev/null 2>&1 &
                fi
                LAST_ALERT_HASH="$ALERT_HASH"
                LAST_ALERT_ACTIVE="true"
                LAST_VERSION="$VERSION"
            fi
        fi
        return 0
    fi

    # 解析 playlist 数组中的 (filename, hash, url)
    PLAYLIST_RAW=$(echo "$MANIFEST" | sed -n 's/.*"playlist"[[:space:]]*:[[:space:]]*\[\(.*\)\].*/\1/p')
    ANY_CHANGED=0
    COUNT=0
    VALID_FILES=""

    # 逐对象解析 playlist
    OLD_IFS="$IFS"
    IFS="}"
    for ITEM in $PLAYLIST_RAW; do
        FNAME=$(json_str "$ITEM" "filename")
        FHASH=$(json_str "$ITEM" "hash")
        FURL=$(json_str "$ITEM" "url")
        if [ -n "$FNAME" ] && [ -n "$FURL" ]; then
            COUNT=$((COUNT + 1))
            VALID_FILES="$VALID_FILES $FNAME"
            OLD_HASH=$(cat "$CACHE_DIR/$FNAME.hash" 2>/dev/null)
            if [ "$FHASH" != "$OLD_HASH" ] || [ ! -s "$CACHE_DIR/$FNAME" ]; then
                if wget -q -T 8 -O "$CACHE_DIR/$FNAME.tmp" "$FURL" 2>/dev/null; then
                    mv "$CACHE_DIR/$FNAME.tmp" "$CACHE_DIR/$FNAME"
                    echo "$FHASH" > "$CACHE_DIR/$FNAME.hash"
                    ANY_CHANGED=1
                fi
            fi
        fi
    done
    IFS="$OLD_IFS"

    [ "$COUNT" -gt 0 ] && PAGE_COUNT="$COUNT"

    # 若刚从紧急通知恢复，或之前文件数不一致，也触发同步
    if [ "$LAST_ALERT_ACTIVE" = "true" ]; then
        ANY_CHANGED=1
        LAST_ALERT_ACTIVE="false"
    fi

    # 检查 /tmp/dashboard 是否缺文件
    if [ ! -s "$DASH_DIR/01_page_1.png" ]; then
        ANY_CHANGED=1
    fi

    if [ "$ANY_CHANGED" = "1" ]; then
        rm -f "$DASH_DIR"/*.png
        for FNAME in $VALID_FILES; do
            if [ -s "$CACHE_DIR/$FNAME" ]; then
                cp "$CACHE_DIR/$FNAME" "$DASH_DIR/$FNAME"
            fi
        done
        # 单页看板时自动生成双缓冲镜像文件 02_page_1_dup.png，保证 NEXT_IMAGE 150ms 原地刷新
        if [ "$PAGE_COUNT" -le 1 ] && [ -s "$DASH_DIR/01_page_1.png" ]; then
            cp "$DASH_DIR/01_page_1.png" "$DASH_DIR/02_page_1_dup.png"
        fi
        trigger_inplace_refresh "$CURRENT_MODE" "$PAGE_COUNT"
    else
        # 没有内容变更时，仅在首次启动时拉起 madeye
        ensure_madeye_running 0
    fi

    LAST_VERSION="$VERSION"
    return 0
}

# ------------------------------------------------------------------------------
# 5. 主循环：USB 网络感知 + HTTP 心跳长轮询 (/api/v1/wait) + 自动轮播步进
# ------------------------------------------------------------------------------
OFFLINE_STRIKES=0
ELAPSED_CAROUSEL_SEC=0

while true; do
    # (A) 检查 USB 网络是否在线：若断开则立即退出守护进程，让 N516 纯粹作为电子书休眠省电
    if ! is_usb_net_online; then
        OFFLINE_STRIKES=$((OFFLINE_STRIKES + 1))
        if [ "$OFFLINE_STRIKES" -ge 2 ]; then
            echo "[OpenInk Agent] USB network disconnected, exiting daemon to save battery." >> "$LOG_FILE"
            exit 0
        fi
        sleep 3
        continue
    fi
    OFFLINE_STRIKES=0

    # (B) 同步最新看板与通知
    if ! sync_display; then
        # 服务端尚未启动或不可达，低频退避等待
        sleep 10
        continue
    fi

    # (C) 心跳式长轮询：每次最多挂起 60 秒（保持在线心跳并及时响应网络插拔），累计达到 CAROUSEL_INTERVAL 时翻页
    CHUNK_WAIT=60
    if [ "$CURRENT_MODE" = "carousel" ] && [ "$PAGE_COUNT" -gt 1 ] && [ "$LAST_ALERT_ACTIVE" != "true" ]; then
        REMAINING=$((CAROUSEL_INTERVAL - ELAPSED_CAROUSEL_SEC))
        if [ "$REMAINING" -lt 60 ] && [ "$REMAINING" -gt 0 ]; then
            CHUNK_WAIT="$REMAINING"
        elif [ "$REMAINING" -le 0 ]; then
            CHUNK_WAIT=1
        fi
    fi
    HTTP_TIMEOUT=$((CHUNK_WAIT + 5))

    # (D) 发起零功耗长轮询挂起请求 (/api/v1/wait)
    WAIT_RESP=$(wget -q -T "$HTTP_TIMEOUT" -O - "$SERVER/api/v1/wait?device_id=$DEVICE_ID&version=$LAST_VERSION&timeout=$CHUNK_WAIT" 2>/dev/null)

    if [ -z "$WAIT_RESP" ]; then
        sleep 5
        continue
    fi

    CHANGED=$(json_val "$WAIT_RESP" "changed")
    if [ "$CHANGED" = "true" ]; then
        # 服务端有新发布/新待办/新通知，重置计时器并在下一轮循环立即增量拉取！
        ELAPSED_CAROUSEL_SEC=0
        continue
    fi

    # (E) 长轮询正常超时 (changed=false)：累计轮播时间，达到设定阈值时翻页
    ELAPSED_CAROUSEL_SEC=$((ELAPSED_CAROUSEL_SEC + CHUNK_WAIT))
    if [ "$CURRENT_MODE" = "carousel" ] && [ "$PAGE_COUNT" -gt 1 ] && [ "$LAST_ALERT_ACTIVE" != "true" ]; then
        if [ "$ELAPSED_CAROUSEL_SEC" -ge "$CAROUSEL_INTERVAL" ]; then
            ELAPSED_CAROUSEL_SEC=0
            if pidof madeye >/dev/null 2>&1; then
                ensure_key_bins
                cat "$KEYS_DIR/next.bin" > "$EVENT_DEV" 2>/dev/null
            fi
        fi
    else
        ELAPSED_CAROUSEL_SEC=0
    fi
done
