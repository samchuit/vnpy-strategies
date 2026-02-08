#!/bin/bash
# VNPY策略仓库同步脚本

cd /Users/chusungang/workspace/vnpy-strategies

echo "📦 同步策略到GitHub..."
echo ""

# 检查是否已添加远程仓库
if ! git remote get-url origin >/dev/null 2>&1; then
    echo "❌ 未配置远程仓库，请先执行:"
    echo "   1. 在GitHub创建仓库: https://github.com/new"
    echo "      - 名称: vnpy-strategies"
    echo "      - 描述: VNPY期货策略库"
    echo "      - 不要初始化README"
    echo ""
    echo "   2. 执行:"
    echo "      git remote add origin https://github.com/samchuit/vnpy-strategies.git"
    echo "      git push -u origin main"
    exit 1
fi

# 添加新文件
git add -A

# 检查是否有变更
if git diff --cached --quiet; then
    echo "✅ 没有新变更"
else
    # 显示变更
    echo "📝 变更内容:"
    git status --short
    echo ""
    
    # 提交
    read -p "输入提交信息 (直接回车使用默认): " msg
    if [ -z "$msg" ]; then
        msg="更新: $(date '+%Y-%m-%d %H:%M')"
    fi
    
    git commit -m "$msg"
    
    # 推送到GitHub
    echo ""
    echo "🚀 推送到GitHub..."
    git push origin main
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ 同步完成!"
        echo "📎 https://github.com/samchuit/vnpy-strategies"
    else
        echo ""
        echo "❌ 推送失败，请检查网络或权限"
        exit 1
    fi
fi
