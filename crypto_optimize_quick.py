#!/usr/bin/env python3
"""
数字货币策略参数优化 - 快速版
只优化BTC，减少参数组合
"""

import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import itertools

SYMBOL = "BTCUSDT"

# 精简参数空间
PARAM_GRID = {
    "ma_fast": [5, 10],
    "ma_slow": [20, 30],
    "ma_trend": [60, 90],
    "stop_loss": [0.02, 0.03],
    "take_profit": [0.06, 0.08, 0.10],
}


def get_binance_kline(symbol, interval='4h', limit=2000):
    url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
    response = requests.get(url, timeout=30)
    data = response.json()
    
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'
    ])
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('datetime')
    df = df.drop(['timestamp', 'close_time', 'ignore'], axis=1)
    
    return df


def backtest(df, config):
    ma_fast = config['ma_fast']
    ma_slow = config['ma_slow']
    ma_trend = config['ma_trend']
    stop_loss = config['stop_loss']
    take_profit = config['take_profit']
    
    max_ma = max(ma_fast, ma_slow, ma_trend)
    position = 0
    entry_price = 0
    pnls = []
    
    for i in range(max_ma, len(df)):
        window = df.iloc[:i+1]
        
        close = window['close'].iloc[-1]
        ma_fast_val = window['close'].rolling(ma_fast).mean().iloc[-1]
        ma_slow_val = window['close'].rolling(ma_slow).mean().iloc[-1]
        ma_trend_val = window['close'].rolling(ma_trend).mean().iloc[-1]
        
        in_uptrend = close > ma_trend_val and ma_slow_val > ma_trend_val
        
        if position > 0:
            if ma_fast_val < ma_slow_val:
                pnl = (close - entry_price) / entry_price
                pnls.append(pnl)
                position = 0
            elif close < entry_price * (1 - stop_loss):
                pnl = (close - entry_price) / entry_price
                pnls.append(pnl)
                position = 0
            elif close > entry_price * (1 + take_profit):
                pnl = (close - entry_price) / entry_price
                pnls.append(pnl)
                position = 0
        else:
            if ma_fast_val > ma_slow_val and in_uptrend:
                position = 1
                entry_price = close
    
    if not pnls:
        return {'sharpe': -999, 'total_return': 0, 'trades': 0}
    
    total_ret = (1 + sum([(1+p) for p in pnls])) - 1
    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(6*365) if np.std(pnls) > 0 else 0
    
    return {
        'sharpe': sharpe,
        'total_return': total_ret,
        'trades': len(pnls),
        'config': config,
    }


print("=" * 60)
print(f"📊 参数优化 - {SYMBOL}")
print("=" * 60)

# 获取数据
print("📂 获取数据...")
df = get_binance_kline(SYMBOL, interval='4h', limit=2000)
print(f"   {len(df)} 条数据")

# 生成参数组合
keys = list(PARAM_GRID.keys())
values = list(PARAM_GRID.values())
combos = list(itertools.product(*values))

print(f"📋 测试 {len(combos)} 种组合...")

results = []
for i, combo in enumerate(combos):
    config = dict(zip(keys, combo))
    result = backtest(df, config)
    results.append(result)
    if (i + 1) % 20 == 0:
        print(f"   进度: {i+1}/{len(combos)}")

# 排序
results.sort(key=lambda x: x['sharpe'], reverse=True)

# 显示Top 10
print()
print("🏆 Top 10 参数组合:")
print("-" * 60)
print(f"{'排名':>4} {'夏普':>8} {'收益':>10} {'交易数':>6} {'参数'}")
print("-" * 60)

for i, r in enumerate(results[:10]):
    cfg = r['config']
    params = f"MA({cfg['ma_fast']}/{cfg['ma_slow']}/{cfg['ma_trend']}) SL{cfg['stop_loss']*100:.0f}% TP{cfg['take_profit']*100:.0f}%"
    print(f"{i+1:>4} {r['sharpe']:>+8.2f} {r['total_return']*100:>+9.1f}% {r['trades']:>6} {params}")

# 最佳
best = results[0]
print()
print("=" * 60)
print("✅ 最佳配置:")
print(f"   夏普: {best['sharpe']:.2f}")
print(f"   收益: {best['total_return']*100:.1f}%")
print(f"   交易数: {best['trades']}")
for k, v in best['config'].items():
    print(f"   {k}: {v}")

# 保存
result_path = "/Users/chusungang/workspace/vnpy-strategies/result/crypto"
os.makedirs(result_path, exist_ok=True)

json_path = f"{result_path}/optimize_{SYMBOL}_quick.json"
with open(json_path, 'w') as f:
    json.dump(best['config'], f, indent=2)

print()
print(f"💾 结果已保存: {json_path}")
