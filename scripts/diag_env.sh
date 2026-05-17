#!/bin/bash
# 环境变量诊断脚本
# 用于检查 Docker 容器中的环境变量是否正确设置

echo "=========================================="
echo "🔍 环境变量诊断"
echo "=========================================="

# 检查关键环境变量
ENV_VARS=(
    "TG_BOT_TOKEN"
    "TG_CHAT_ID"
    "EMBY_API_KEY"
    "TMDB_API_KEY"
    "WEBHOOK_TOKEN"
    "EMBY_HOST"
)

for var in "${ENV_VARS[@]}"; do
    value=$(printenv "$var")
    if [ -n "$value" ]; then
        length=${#value}
        echo "✅ $var: 已设置 (长度: $length)"
    else
        echo "❌ $var: 未设置"
    fi
done

echo ""
echo "=========================================="
echo "📁 配置文件检查"
echo "=========================================="

# 检查配置文件
if [ -f "/workspace/config/config.json" ]; then
    echo "✅ 配置文件存在: /workspace/config/config.json"
    echo ""
    echo "配置文件内容（脱敏）:"
    cat /workspace/config/config.json | python3 -c "
import sys, json
data = json.load(sys.stdin)
sensitive = ['tg_bot_token', 'tg_user_bot_token', 'emby_api_key', 'tmdb_api_key', 'webhook_token', 'moviepilot_token', 'wecom_corpsecret', 'wecom_token', 'wecom_aeskey']
for key in sensitive:
    if key in data and data[key]:
        data[key] = '****（配置文件中存在）'
    elif key in data:
        data[key] = '（空）'
print(json.dumps(data, indent=2, ensure_ascii=False))
"
else
    echo "❌ 配置文件不存在: /workspace/config/config.json"
fi

echo ""
echo "=========================================="
echo "🔍 容器内环境变量（完整列表）"
echo "=========================================="
env | grep -E "^(TG_|EMBY_|TMDB_|WEBHOOK_|MOVIEPILOT_|WECOM_)" | sort
