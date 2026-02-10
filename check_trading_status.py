#!/usr/bin/env python3
"""实盘交易状态检查脚本"""

import sys
sys.path.insert(0, '/Users/chusungang/workspace/vnpy-strategies')

from binance_config import API_KEY, API_SECRET
import requests
import hmac
import hashlib
import time

# 代理配置
PROXIES = {
    'http': 'socks5://192.168.0.78:7897',
    'https': 'socks5://192.168.0.78:7897',
}

def get_balance():
    """获取余额"""
    url = 'https://fapi.binance.com/fapi/v2/balance'
    ts = int(time.time() * 1000)
    params = {'timestamp': ts}
    query = f"timestamp={ts}"
    signature = hmac.new(API_SECRET.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
    params['signature'] = signature
    headers = {'X-MBX-APIKEY': API_KEY}
    
    resp = requests.get(url, params=params, headers=headers, proxies=PROXIES, timeout=10)
    data = resp.json()
    
    for asset in data:
        if asset['asset'] == 'USDT':
            return float(asset['balance'])
    return 0

def get_positions():
    """获取持仓"""
    url = 'https://fapi.binance.com/fapi/v2/positionRisk'
    ts = int(time.time() * 1000)
    params = {'timestamp': ts}
    query = f"timestamp={ts}"
    signature = hmac.new(API_SECRET.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
    params['signature'] = signature
    headers = {'X-MBX-APIKEY': API_KEY}
    
    resp = requests.get(url, params=params, headers=headers, proxies=PROXIES, timeout=10)
    return resp.json()

def main():
    """主函数"""
    print("=" * 70)
    print("📊 实盘交易状态汇报")
    print("=" * 70)
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 余额
    balance = get_balance()
    print(f"💰 USDT 余额: {balance:.2f}")
    print()
    
    # 持仓
    positions = get_positions()
    print("📊 持仓情况:")
    has_position = False
    total_pnl = 0
    total_value = 0
    
    for p in positions:
        size = float(p['positionAmt'])
        if size != 0:
            has_position = True
            symbol = p['symbol']
            entry = float(p['entryPrice'])
            pnl = float(p['unRealizedProfit'])
            liq = float(p['liquidationPrice'])
            leverage = float(p['leverage'])
            value = abs(size * entry)
            
            total_pnl += pnl
            total_value += value
            
            side = "做空" if size < 0 else "做多"
            pnl_emoji = "✅" if pnl > 0 else ("🟡" if pnl == 0 else "🔴")
            
            print(f"   {pnl_emoji} {symbol}:")
            print(f"      方向: {side}")
            print(f"      数量: {abs(size):.4f}")
            print(f"      开仓价: {entry:.2f}")
            print(f"      未实现盈亏: {pnl:+.2f} USDT")
            print(f"      强平价: {liq:.2f}")
            print(f"      杠杆: {leverage}x")
            print(f"      仓位价值: {value:.2f} USDT")
            print()
    
    if not has_position:
        print("   📭 当前无持仓")
        print()
    
    print("-" * 70)
    print(f"💰 总未实现盈亏: {total_pnl:+.2f} USDT")
    print(f"📊 总仓位价值: {total_value:.2f} USDT")
    print(f"📈 收益率: {(total_pnl/balance*100) if balance > 0 else 0:.2f}%")
    print("=" * 70)

if __name__ == "__main__":
    main()
