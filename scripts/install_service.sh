#!/usr/bin/env bash
# ==============================================================================
# AgentCorp - Automated Systemd Service Installer
# Installs AgentCorp as a background daemon/service that automatically starts
# on system boot, connects to Tailscale P2P mesh, and restarts on failure.
# ==============================================================================

set -e

# Detect real user when running under sudo
CURRENT_USER=${SUDO_USER:-$(whoami)}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="agentcorp"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

AGENT_NAME=${1:-"Agent-${HOSTNAME}"}
PERSONA=${2:-"devops_dan"}

echo "=================================================================="
echo "  ⚡ Cài đặt AgentCorp Service (Systemd Daemon) ⚡"
echo "=================================================================="
echo "  Thư mục dự án   : $SCRIPT_DIR"
echo "  Tài khoản chạy  : $CURRENT_USER"
echo "  Tên Agent       : $AGENT_NAME"
echo "  Persona         : $PERSONA"
echo "=================================================================="

# Check for root/sudo permissions
if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Lỗi: Vui lòng chạy script này với quyền sudo:"
    echo "   sudo ./scripts/install_service.sh [TÊN_AGENT] [PERSONA]"
    exit 1
fi

# Ensure python3 and python3-venv are available
if ! command -v python3 &> /dev/null; then
    echo "❌ Lỗi: Chưa tìm thấy Python 3 trên máy."
    exit 1
fi

echo "📦 Bước 1: Chuẩn bị môi trường Python..."
cd "$SCRIPT_DIR"

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "  Tạo môi trường ảo (.venv)..."
    sudo -u "$CURRENT_USER" python3 -m venv "$SCRIPT_DIR/.venv"
fi

echo "  Cài đặt các thư viện phụ thuộc (requirements.txt)..."
sudo -u "$CURRENT_USER" "$SCRIPT_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$CURRENT_USER" "$SCRIPT_DIR/.venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

echo "📝 Bước 2: Tạo file cấu hình Systemd Service ($SERVICE_FILE)..."
cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=AgentCorp Autonomous P2P Agent Mesh
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/.venv/bin/python3 $SCRIPT_DIR/run_mesh.py --name "$AGENT_NAME" --persona "$PERSONA"
Restart=always
RestartSec=5s

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=agentcorp
Environment=PYTHONUNBUFFERED=1

# Security & Isolation sandbox settings
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

echo "🔄 Bước 3: Kích hoạt và khởi động service..."
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"
systemctl restart "${SERVICE_NAME}.service"

echo ""
echo "=================================================================="
echo "🎉 CÀI ĐẶT THÀNH CÔNG SERVICE AGENTCORP!"
echo "=================================================================="
echo "  Service hiện đang chạy ngầm 24/7 và tự động bật khi khởi động máy."
echo ""
echo "  📌 CÁC LỆNH QUẢN LÝ DỊCH VỤ:"
echo "     • Kiểm tra trạng thái : sudo systemctl status ${SERVICE_NAME}"
echo "     • Xem log realtime    : journalctl -u ${SERVICE_NAME} -f"
echo "     • Khởi động lại       : sudo systemctl restart ${SERVICE_NAME}"
echo "     • Dừng dịch vụ        : sudo systemctl stop ${SERVICE_NAME}"
echo "     • Gỡ bỏ dịch vụ       : sudo ./scripts/uninstall_service.sh"
echo "=================================================================="
echo ""
systemctl status "${SERVICE_NAME}.service" --no-pager || true
