#!/bin/bash

# =================================================================
# --- 1. 配置模块 (用户需根据项目环境填写) ---
# =================================================================
PROJECT_ROOT="$(pwd)"

# [填写建议] GIT_TOKEN: 建议在终端通过 export GIT_TOKEN=xxx 设置，不要硬编码在脚本中
GIT_TOKEN="${GIT_TOKEN:-}"
# [填写建议] GIT_BRANCH: 填写 Proto 仓库的分支名，默认 main
GIT_BRANCH="${GIT_BRANCH:-main}"
# [填写建议] GITLAB_URL: 仓库的 HTTPS 路径（不带 https:// 和 token 部分）
GITLAB_URL="gitlab.ejsafe.com/backend-base/lawgenesis_proto.git"

# [填写建议] TEMP_DIR: 脚本运行时的临时工作目录，执行完会自动删除
TEMP_DIR="./temp_proto_repo"
# [填写建议] OUT_DIR: 生成代码的存放位置，这直接决定了 Python 的 import 路径
OUT_DIR="dubbo/generated"

# =================================================================
# --- 2. 环境检查 ---
# =================================================================
if [ -z "$GIT_TOKEN" ]; then
    echo "❌ Error: 必须提供 GIT_TOKEN 环境变量才能克隆仓库。"
    exit 1
fi

echo "🚀 正在初始化环境..."
# 每次运行前清理旧的临时文件和已生成的旧代码
rm -rf "$TEMP_DIR" "$OUT_DIR"
# 创建输出目录（包含父目录 dubbo）
mkdir -p "$OUT_DIR"
# 记录输出目录的绝对路径，防止 cd 切换目录后找不到位置
ABS_OUT_DIR="$(pwd)/$OUT_DIR"

# =================================================================
# --- 3. 克隆仓库 ---
# =================================================================
echo "📥 正在从 GitLab 克隆 Proto 协议文件..."
# 使用 oauth2 协议通过 Token 鉴权克隆
git clone -b "$GIT_BRANCH" --single-branch --depth 1 "https://oauth2:${GIT_TOKEN}@${GITLAB_URL}" "$TEMP_DIR"

if [ $? -ne 0 ]; then
    echo "❌ Clone 失败，请检查 Token 权限或网络。"
    exit 1
fi

# =================================================================
# --- 4. 生成 Python 代码 ---
# =================================================================
echo "⚙️  正在调用 protoc 生成 gRPC 代码..."
# 进入克隆下来的 proto 源码所在目录
cd "$TEMP_DIR/proto" || exit

# 找到当前目录下所有的 .proto 文件
PROTO_FILES=$(find . -name "*.proto")
if [ -n "$PROTO_FILES" ]; then
    # 执行编译命令
    python -m grpc_tools.protoc \
      --proto_path=. \
      --python_out="$ABS_OUT_DIR" \
      --grpc_python_out="$ABS_OUT_DIR" \
      $PROTO_FILES

    # =============================================================
    # --- 5. 核心补正逻辑: 修正 Python 导入路径 ---
    # =============================================================
    # 背景：protoc 生成的 import 语句是绝对路径，直接在包内使用会报 Import 错误
    echo "🔧 正在根据目录结构 ($OUT_DIR) 补正导入路径..."

    # 进入生成的代码目录，方便进行批量替换
    cd "$ABS_OUT_DIR" || exit
    echo "层级初始化: 正在所有目录创建 __init__.py..."
    # 在输出目录及其所有子目录下创建 __init__.py
    # -type d 表示只找文件夹，-exec 对每个文件夹执行 touch
    find "$ABS_OUT_DIR" -type d -exec touch {}/__init__.py \;
    # [逻辑点] 修正 _pb2.py 文件
    # 查找所有 import xxx_pb2，替换为 from dubbo.generated import xxx_pb2
    # 使用 perl 兼容性更好，(?!from) 确保不会重复替换
    find . -name "*_pb2.py" -print0 | xargs -0 perl -i -pe "s/^(?!from)import ([^ ]+_pb2)/from dubbo.generated import \$1/g"

    # [逻辑点] 修正 _pb2_grpc.py 文件
    # 这里的 sed 会将行首的 "from " 统一加上包名前缀
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS 特供版 sed
        find "$ABS_OUT_DIR" -name "*_pb2_grpc.py" -exec sed -i '' 's/^from /from dubbo.generated./g' {} +
    else
        # Linux 特供版 sed
        find "$ABS_OUT_DIR" -name "*_pb2_grpc.py" -exec sed -i 's/^from /from dubbo.generated./g' {} +
    fi

    # --- 验证环节 ---
    echo "🔍 正在扫描是否还存在未处理的相对导入 (from .)..."
    GREP_RES=$(grep -r "from \." . || true)
    if [ -z "$GREP_RES" ]; then
        echo "✅ 验证通过：导入路径已全部指向 dubbo.generated"
    else
        echo "⚠️ 警告：仍有相对导入残留，可能导致运行报错："
        echo "$GREP_RES"
    fi
fi

# =================================================================
# --- 6. 清理现场 ---
# =================================================================
# 使用 cd - 返回之前的目录，或者直接使用最开始记录的根路径
cd "$PROJECT_ROOT" || exit

echo "🧹 正在清理临时克隆目录..."
# 这里使用绝对路径删除，确保在任何目录下都能删掉 TEMP_DIR
rm -rf "$PROJECT_ROOT/$TEMP_DIR"

echo "✨ 处理完成！代码位于: $OUT_DIR"