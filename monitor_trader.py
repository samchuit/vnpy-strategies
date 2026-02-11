#!/usr/bin/env python3
"""
实盘程序监控脚本 - 增强版
功能:
1. 检测程序运行状态
2. 检查日志错误
3. 连续10分钟报错则自动重启
"""

import os
import sys
import time
import subprocess
from datetime import datetime

# 配置
LOG_FILE = "/Users/chusungang/workspace/vnpy-strategies/binance_trader_optimized.log"
PYTHON_SCRIPT = "binance_trader_optimized.py"
DATA_DIR = "/Users/chusungang/workspace/vnpy-strategies"
ERROR_THRESHOLD_MINUTES = 10  # 10分钟持续报错则重启

# 状态文件
STATUS_FILE = "/Users/chusungang/workspace/vnpy-strategies/.monitor_status.json"

def load_status():
    """加载上次状态"""
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {
        "last_error_time": None,
        "last_check_ok": True,
        "restart_count": 0,
        "last_restart_time": None
    }

def save_status(status):
    """保存状态"""
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f)
    except:
        pass

def get_pid():
    """获取进程PID"""
    try:
        # 使用-f参数匹配完整命令行
        result = subprocess.run(
            ['pgrep', '-f', 'binance_trader_optimized'],
            capture_output=True, text=True
        )
        pid = result.stdout.strip()
        if pid and pid.isdigit():
            return int(pid)
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

def get_last_log_content():
    """获取最后一条日志内容（跳过分隔线）"""
    try:
        if not os.path.exists(LOG_FILE):
            return None
        
        # 读取最后3行（跳过分隔线）
        result = subprocess.run(
            ['tail', '-n', '3', LOG_FILE],
            capture_output=True, text=True
        )
        
        lines = result.stdout.strip().split('\n')
        
        # 找到最后一条非分隔线的内容
        for line in reversed(lines):
            line = line.strip()
            if line and not line.strip().endswith('------'):
                return line
        
        return None
        
    except:
        pass
    return None

def check_recent_errors():
    """检查最近N分钟的错误（返回错误行和时间戳）"""
    try:
        if not os.path.exists(LOG_FILE):
            return [], None
        
        # 获取文件修改时间
        mtime = os.path.getmtime(LOG_FILE)
        
        # 读取最后50行（增加行数以覆盖10分钟日志）
        result = subprocess.run(
            ['tail', '-n', '50', LOG_FILE],
            capture_output=True, text=True
        )
        
        lines = result.stdout.strip().split('\n')
        
        # 查找ERROR行及其时间戳（排除保证金不足等正常业务错误）
        errors = []
        for line in lines:
            # 排除 "Margin is insufficient" 等正常业务错误
            if ('ERROR' in line or 'Error' in line or ' error:' in line.lower()) and \
               'Margin is insufficient' not in line:
                errors.append(line.strip())
        
        return errors, mtime
        
    except Exception as e:
        return [], None

def restart_trader():
    """重启交易程序"""
    print("🔄 尝试重启交易程序...")
    
    # 获取当前PID
    pid = get_pid()
    
    # 停止旧进程
    if pid:
        print(f"   停止旧进程 PID {pid}...")
        subprocess.run(['kill', str(pid)], capture_output=True)
        time.sleep(2)
        
        # 再次确认停止
        subprocess.run(['kill', '-9', str(pid)], capture_output=True)
        time.sleep(1)
    
    # 启动新进程
    print("   启动新进程...")
    subprocess.Popen(
        ['nohup', 'python3', PYTHON_SCRIPT, '&'],
        cwd=DATA_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    time.sleep(5)
    
    # 检查是否启动成功
    new_pid = get_pid()
    if new_pid:
        print(f"   ✅ 重启成功! 新 PID: {new_pid}")
        return new_pid
    else:
        print("   ❌ 重启失败")
        return None

def main(report_only=False):
    """主函数"""
    status = load_status()
    current_time = time.time()
    
    # 获取当前状态
    pid = get_pid()
    mtime = get_last_log_time()
    errors, error_mtime = check_recent_errors()
    last_log_content = get_last_log_content()
    
    last_time_str = datetime.fromtimestamp(mtime).strftime("%H:%M:%S") if mtime else "未知"
    time_ago = int((current_time - mtime) / 60) if mtime else 0
    
    has_errors = len(errors) > 0
    error_minutes = 0
    
    if has_errors:
        # 有错误
        if status['last_error_time'] is None:
            # 第一次发现错误，记录开始时间
            status['last_error_time'] = error_mtime
        
        # 计算错误持续时间
        error_minutes = int((current_time - status['last_error_time']) / 60)
    else:
        # 无错误，重置状态（恢复正常，重置计时器）
        status['last_error_time'] = None
    
    status['last_check_ok'] = not has_errors
    
    # 判断是否需要重启
    should_restart = False
    restart_reason = ""
    
    if not pid:
        # 程序未运行，需要启动
        should_restart = True
        restart_reason = "程序未运行"
    elif has_errors and error_minutes >= ERROR_THRESHOLD_MINUTES:
        should_restart = True
        restart_reason = f"连续{ERROR_THRESHOLD_MINUTES}分钟报错"
    
    # 构建状态报告
    print("=" * 60)
    print("📊 实盘程序监控报告")
    print("=" * 60)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"PID: {pid if pid else '❌ 未运行'}")
    print(f"运行中: {'✅ 是' if pid else '❌ 否'}")
    print(f"最后日志: {last_time_str} ({time_ago}分钟前)")
    if last_log_content:
        # 只显示日志内容部分（去掉时间戳）
        log_parts = last_log_content.split(' - ', 2)
        if len(log_parts) >= 3:
            content = log_parts[2].strip()
            # 移除末尾的分隔线
            if content.endswith('------'):
                content = content[:-70].strip()
            print(f"📝 最新日志: {content[:120]}")
        else:
            print(f"📝 最新日志: {last_log_content[:120]}")
    print(f"错误数量: {len(errors)}")
    
    if has_errors:
        print(f"错误持续: {error_minutes} 分钟")
        if errors[:3]:
            print("最近错误:")
            for i, err in enumerate(errors[:3], 1):
                print(f"  {i}. {err[:100]}")
    
    # 执行重启/启动
    restart_result = None
    if not report_only and should_restart:
        print(f"\n⚠️  {restart_reason}，准备重启...")
        restart_result = restart_trader()
        if restart_result:
            status['restart_count'] += 1
            status['last_restart_time'] = current_time
            status['last_error_time'] = None  # 重置错误状态
            pid = restart_result
    
    # 保存状态
    save_status(status)
    
    print()
    if restart_result:
        print(f"✅ 已重启，PID: {restart_result}")
        print(f"重启次数: {status['restart_count']}")
    
    # 返回状态码
    if not pid:
        return 1  # 程序未运行
    elif has_errors and error_minutes < ERROR_THRESHOLD_MINUTES:
        return 2  # 有错误但未达到重启阈值
    elif restart_result:
        return 0  # 已重启
    else:
        return 0  # 正常

if __name__ == "__main__":
    import json
    report_only = "--report-only" in sys.argv or "-r" in sys.argv
    sys.exit(main(report_only))
