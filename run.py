import uvicorn
import subprocess
import sys
from app.core.config import PORT

def ensure_dependencies():
    """
    启动前确保 psutil 已安装
    """
    try:
        import psutil
    except ImportError:
        print("检测到缺失核心监控组件 psutil，正在尝试自动安装...")
        try:
            # 执行 pip install psutil
            subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
            print("psutil 安装成功！")
        except Exception as e:
            print(f"自动安装失败，请手动执行 'pip install psutil'。错误原因: {e}")

if __name__ == "__main__":
    # 1. 执行依赖检查与安装
    ensure_dependencies()
    
    # 2. 启动应用
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=True)