#!/usr/bin/env bash
# Quick Worker Installer & Launcher for AgentCorp Client Node
set -e

echo "=== Cài đặt AgentCorp Node trên máy này ==="

# Tạo môi trường ảo nếu chưa có
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Mặc định kết nối về Hub
HUB_URL=${1:-"ws://192.168.1.4:8000/ws/hub"}
NODE_NAME=${2:-"Worker-Client-$(hostname)"}
NODE_ID=${3:-"node-$(hostname | tr '[:upper:]' '[:lower:]')"}
PERSONA=${4:-"growth_gary"}

echo "--------------------------------------------------"
echo "Đang kết nối Node về Hub: $HUB_URL"
echo "Tên Agent: $NODE_NAME (ID: $NODE_ID, Persona: $PERSONA)"
echo "--------------------------------------------------"

python3 -m agentcorp_node.daemon \
    --hub-url "$HUB_URL" \
    --name "$NODE_NAME" \
    --node-id "$NODE_ID" \
    --persona "$PERSONA"
