#!/usr/bin/env bash
# ============================================================
# A股见底信号仪表盘 —— 一键刷新数据并打开浏览器展示
# 可用于开机自启动（Hyprland autostart / cron / systemd 等）
#
# 依赖环境变量（二选一即可，tushare 会自动读取）：
#   TUSHARE_TOKEN  —— 你的 Tushare Pro token
# 可选环境变量：
#   PYTHON         —— 指定 Python 解释器（默认 python3，需已安装 tushare）
#   CHROME         —— 指定浏览器命令（默认 google-chrome-stable）
# ============================================================
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"
BUILD="$DIR/build_dashboard.py"
HTML="$DIR/index.html"
LOG="$DIR/run.log"
LOCK="$DIR/.run.lock"
URL="file://$HTML"
BROWSER="${CHROME:-google-chrome-stable}"

mkdir -p "$DIR"
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$LOG" >/dev/null; }
notify(){
  command -v omarchy-notification-send >/dev/null 2>&1 && omarchy-notification-send -u low "$1" 2>/dev/null && return
  command -v notify-send >/dev/null 2>&1 && notify-send "A股看板" "$1" 2>/dev/null
  return 0
}

# 防止重复运行（多会话 / 手动触发）
exec 9>"$LOCK"
flock -n 9 || { log "已在运行，跳过"; exit 0; }

log "==== 开始刷新看板 ===="
notify "A股见底看板：正在刷新数据…"

# 等待网络就绪（最多 ~40s）；无 ping/curl 时直接跳过
for i in $(seq 1 20); do
  if ping -c1 -W1 api.waditu.com >/dev/null 2>&1 \
     || curl -sf -m3 -o /dev/null https://api.waditu.com 2>/dev/null \
     || ! command -v curl >/dev/null 2>&1; then
    log "网络就绪 (第 ${i} 次尝试)"; break
  fi
  sleep 2
done

# 刷新数据（最多重试 3 次）
ok=1
for attempt in 1 2 3; do
  log "执行分析 (第 ${attempt} 次)…"
  if "$PY" "$BUILD" >>"$LOG" 2>&1; then ok=0; log "分析成功"; break; fi
  log "分析失败 (第 ${attempt} 次)，10s 后重试"; sleep 10
done

if [ "$ok" -ne 0 ]; then
  log "多次重试仍失败，打开上次结果"
  notify "A股看板更新失败，显示上次结果（详见 run.log）"
else
  notify "A股见底看板：已更新，正在打开…"
fi

# 用浏览器展示（后台，避免阻塞）
if [ -f "$HTML" ]; then
  setsid "$BROWSER" --new-tab "$URL" >>"$LOG" 2>&1 &
  log "已请求浏览器打开 $URL"
else
  log "未找到 $HTML，无法打开"
fi
log "==== 结束 ===="
