#!/usr/bin/env bash
# ==============================================================================
# AgentCorp - Systemd Service Uninstaller
# Stops and removes the AgentCorp background daemon from the system.
# ==============================================================================

set -e

SERVICE_NAME="agentcorp"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Lỗi: Vui lòng chạy script này với quyền sudo:"
    echo "   sudo ./scripts/uninstall_service.sh"
    exit 1
fi

echo "🛑 Dừng và vô hiệu hóa service ${SERVICE_NAME}..."
systemctl stop "${SERVICE_NAME}.service" 2>/dev/null || true
systemctl disable "${SERVICE_NAME}.service" 2>/dev/null || true

if [ -f "$SERVICE_FILE" ]; then
    rm -f "$SERVICE_FILE"
    echo "🗑️ Đã xóa file cấu hình service: $SERVICE_FILE"
fi

systemctl daemon-reload
echo "✅ Đã gỡ bỏ service ${SERVICE_NAME} thành công."
