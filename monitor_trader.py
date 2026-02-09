#!/usr/bin/env python3
"""
实盘程序监控脚本 - 仅检查错误
不自动重启，只汇报状态和错误
"""

import os
import sys
import time
import subprocess
from datetime import datetime

# 配置
LOG_FILE = "/Users/chusungang/workspace/vnpy-strategies/binance_trader_optimized.log"

def get_pid():
    """获取进程PID"""
    try:
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if 'binance_trader_optimized.py' in line and 'grep' not in line and 'python' in line:
                parts = line.split()
                if len(parts) >= 2:
                    return int(parts[1])
    except:
        pass
    return None

def get_last_log_time():
    """获取最后日志更新时间"""
    try:
        if os.path.exists(LOG_FILE):
            return os.path.getmtime(LOG_FILE)
    except:
        pass
    return None

def check_errors_in_log():
    """检查日志中的错误信息（最新10行）"""
    try:
        if not os.path.exists(LOG_FILE):
            return [], "日志文件不存在"
        
        # 读取最后10行
        result = subprocess.run(
            ['tail', '-n', '10', LOG_FILE],
            capture_output=True, text=True
        )
        
        lines = result.stdout.strip().split('\n')
        
        # 查找ERROR行
        errors = []
        for line in lines:
            if 'ERROR' in line or 'Error' in line or 'error' in line:
                # 提取时间戳和错误信息
                if '-' in line:
                    parts = line.split('-', 1)
                    if len(parts) >= 2:
                        errors.append(parts[1].strip())
        
        return errors, "OK"
        
    except Exception as e:
        return [], f"检查错误失败: {e}"

def main():
    """主函数 - 只检查状态和错误"""
    pid = get_pid()
    mtime = get_last_log_time()
    last_time = datetime.fromtimestamp(mtime).strftime("%H:%M:%S") if mtime else "未知"
    time_ago = int((time.time() - mtime) / 60) if mtime else 0
    
    errors, error_status = check_errors_in_log()
    
    # 构建状态报告
    status = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pid": pid,
        "running": pid is not None,
        "last_log_time": last_time,
        "log_age_minutes": time_ago,
        "error_count": len(errors),
        "errors": errors[:5] if errors else [],  # 最多显示5个错误
    }
    
    # 打印状态
    print(f"[{status['time']}]")
    print(f"PID: {status['pid']}")
    print(f"运行中: {'是' if status['running'] else '否'}")
    print(f"最后日志: {status['last_log_time']} ({status['log_age_minutes']}分钟前)")
    print(f"错误数量: {status['error_count']}")
    
    if errors:
        print("\n最近错误:")
        for i, err in enumerate(errors[:5], 1):
            print(f"  {i}. {err}")
    
    # 返回状态码
    if not status['running']:
        return 1  # 程序未运行
    elif status['error_count'] > 3:
        return 2  # 错误太多
    else:
        return 0  # 正常

if __name__ == "__main__":
    sys.exit(main())
