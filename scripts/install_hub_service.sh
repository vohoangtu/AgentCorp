#!/usr/bin/env bash
# ==============================================================================
# AgentCorp - Automated Central Hub Installer for Cloud VPS (Vultr / Lightweight)
# Optimized for low-RAM cloud instances (512MB RAM with automatic 2GB swap)
# Runs the Central Hub Server 24/7, binding to Tailscale and LAN on port 8000.
# ==============================================================================

set -e

CURRENT_USER=${SUDO_USER:-$(whoami)}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="agentcorp-hub"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PORT=${1:-8000}

echo "=================================================================="
echo "  🏢 Cài đặt AgentCorp 24/7 Central Hub Server (Vultr Cloud) 🏢"
echo "=================================================================="
echo "  Thư mục dự án  : $SCRIPT_DIR"
echo "  Tài khoản chạy : $CURRENT_USER"
echo "  Cổng lắng nghe : $PORT (0.0.0.0:$PORT)"
echo "=================================================================="

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Lỗi: Vui lòng chạy script này với quyền sudo:"
    echo "   sudo ./scripts/install_hub_service.sh [PORT]"
    exit 1
fi

# 1. Tự động kiểm tra và tạo 2GB Swap nếu RAM <= 1GB
TOTAL_MEM_MB=$(free -m | awk '/^Mem:/{print $2}')
if [ "$TOTAL_MEM_MB" -lt 1200 ] && [ ! -f /swapfile ]; then
    echo "💾 Phát hiện máy tính có RAM $TOTAL_MEM_MB MB. Đang kích hoạt 2GB Swap để chống tràn RAM..."
    fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi
    echo "✅ Đã kích hoạt 2GB Swap SSD thành công!"
fi

# 2. Chuẩn bị môi trường Python nhẹ
echo "📦 Chuẩn bị môi trường Python Hub..."
cd "$SCRIPT_DIR"

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    sudo -u "$CURRENT_USER" python3 -m venv "$SCRIPT_DIR/.venv"
fi

sudo -u "$CURRENT_USER" "$SCRIPT_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$CURRENT_USER" "$SCRIPT_DIR/.venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# 3. Tạo file cấu hình Systemd Service
echo "📝 Cấu hình Systemd Service ($SERVICE_FILE)..."
cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=AgentCorp 24/7 Central Master Hub Server
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/.venv/bin/uvicorn agentcorp_hub.server:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3s

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=agentcorp-hub
Environment=PYTHONUNBUFFERED=1

LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

# 4. Kích hoạt và bật service
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"
systemctl restart "${SERVICE_NAME}.service"

echo ""
echo "=================================================================="
echo "🎉 CENTRAL MASTER HUB ĐÃ ĐƯỢC CÀI ĐẶT THÀNH CÔNG TRÊN VULTR!"
echo "=================================================================="
echo "  Hub Server hiện đang chạy 24/7 và tự động bật khi khởi động VPS."
echo ""
echo "  📌 CÁC LỆNH QUẢN LÝ DỊCH VỤ HUB:"
echo "     • Kiểm tra trạng thái : sudo systemctl status ${SERVICE_NAME}"
echo "     • Xem log realtime    : journalctl -u ${SERVICE_NAME} -f"
echo "     • Khởi động lại       : sudo systemctl restart ${SERVICE_NAME}"
echo "     • Dừng dịch vụ        : sudo systemctl stop ${SERVICE_NAME}"
echo "=================================================================="
echo ""
systemctl status "${SERVICE_NAME}.service" --no-pager || true
