#!/usr/bin/env python3
"""
双边策略回测 - 保守版
只在强趋势时交易，减少震荡亏损
"""

import sys
import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List

# 配置 - 保守参数
STRATEGY_CONFIG = {
    "ma_fast": 5,       # 快速MA
    "ma_slow": 20,      # 慢速MA
    "ma_trend": 60,     # 趋势MA
    "stop_loss": 0.02,  # 止损2%
    "take_profit": 0.15, # 止盈15%（给更多空间）
}

SYMBOLS = [
    {"symbol": "BTCUSDT", "weight": 0.50},
    {"symbol": "ETHUSDT", "weight": 0.30},
    {"symbol": "SOLUSDT", "weight": 0.20},
]


def get_binance_klines(symbol, interval='4h', limit=2000):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url, timeout=30)
    data = response.json()
    
    df = []
    for k in data:
        df.append({
            'time': k[0],
            'close': float(k[4]),
            'high': float(k[2]),
            'low': float(k[3]),
        })
    
    return df


def calculate_ma(prices, period):
    if len(prices) < period:
        return prices[-1] if prices else 0
    return sum(prices[-period:]) / period


def backtest_conservative(symbol, df, config):
    """
    保守双边策略
    
    改进：
    1. MA5确认短期方向
    2. MA60确认趋势
    3. 只在价格远离MA60时交易
    4. 给更多止盈空间(15%)
    """
    ma_fast = config['ma_fast']
    ma_slow = config['ma_slow']
    ma_trend = config['ma_trend']
    stop_loss = config['stop_loss']
    take_profit = config['take_profit']
    
    closes = [k['close'] for k in df]
    max_ma = max(ma_fast, ma_slow, ma_trend)
    
    position = 0
    entry_price = 0
    trades = []
    
    for i in range(max_ma, len(closes)):
        close = closes[i]
        
        ma5 = calculate_ma(closes[:i+1], 5)
        ma20 = calculate_ma(closes[:i+1], ma_slow)
        ma60 = calculate_ma(closes[:i+1], ma_trend)
        
        # 趋势判断
        price_above_ma60 = close > ma60
        ma20_above_ma60 = ma20 > ma60
        
        # 做多条件：强多头
        long_condition = (close > ma60 and ma20_above_ma60 and ma5 > ma20)
        
        # 做空条件：强空头
        short_condition = (close < ma60 and not ma20_above_ma60 and ma5 < ma20)
        
        signal = "HOLD"
        
        # 持仓处理
        if position == 1:
            if ma5 < ma20:  # 短期反转
                signal = "CLOSE"
            elif close < entry_price * (1 - stop_loss):
                signal = "CLOSE_SL"
            elif close > entry_price * (1 + take_profit):
                signal = "CLOSE_TP"
        
        elif position == -1:
            if ma5 > ma20:
                signal = "CLOSE"
            elif close > entry_price * (1 + stop_loss):
                signal = "CLOSE_SL"
            elif close < entry_price * (1 - take_profit):
                signal = "CLOSE_TP"
        
        else:
            if long_condition:
                signal = "OPEN_LONG"
            elif short_condition:
                signal = "OPEN_SHORT"
        
        # 执行
        if signal == "OPEN_LONG" and position == 0:
            position = 1
            entry_price = close
        
        elif signal == "OPEN_SHORT" and position == 0:
            position = -1
            entry_price = close
        
        elif "CLOSE" in signal and position != 0:
            pnl = (close - entry_price) / entry_price if position == 1 else (entry_price - close) / entry_price
            trades.append({
                'type': 'LONG' if position == 1 else 'SHORT',
                'entry': entry_price,
                'exit': close,
                'pnl': pnl * 100,
                'signal': signal,
            })
            position = 0
    
    # 统计
    if not trades:
        return None
    
    pnls = [t['pnl'] for t in trades]
    total_ret = sum([(1 + p/100) for p in pnls]) - 1
    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(6*365) if np.std(pnls) > 0 else 0
    win_rate = sum(1 for p in pnls if p > 0) / len(pnls) * 100
    
    longs = [t for t in trades if t['type'] == 'LONG']
    shorts = [t for t in trades if t['type'] == 'SHORT']
    
    return {
        'symbol': symbol,
        'trades': len(trades),
        'long_trades': len(longs),
        'short_trades': len(shorts),
        'long_wins': sum(1 for t in longs if t['pnl'] > 0),
        'short_wins': sum(1 for t in shorts if t['pnl'] > 0),
        'total_return': total_ret * 100,
        'sharpe': sharpe,
        'win_rate': win_rate,
    }


def run_backtest():
    print("=" * 70)
    print("📊 保守双边策略回测")
    print("=" * 70)
    print()
    print("📋 改进点:")
    print("   • MA5确认短期方向")
    print("   • MA60确认趋势")
    print("   • 只在强趋势时交易")
    print("   • 止盈15%")
    print()
    
    all_results = []
    
    for s in SYMBOLS:
        symbol = s['symbol']
        print(f"📊 {symbol}...")
        
        df = get_binance_klines(symbol, interval='4h', limit=4000)
        print(f"   {len(df)} 条数据")
        
        result = backtest_conservative(symbol, df, STRATEGY_CONFIG)
        
        if result:
            status = "✅" if result['sharpe'] > 0 else "⚠️"
            print(f"   {status} {result['trades']}笔, 收益: {result['total_return']:+.1f}%, 夏普: {result['sharpe']:+.2f}")
            print(f"      多头: {result['long_trades']}笔 ({result['long_wins']}胜)")
            print(f"      空头: {result['short_trades']}笔 ({result['short_wins']}胜)")
            all_results.append(result)
    
    print()
    print("=" * 70)
    print("📊 汇总")
    print("=" * 70)
    print()
    
    print(f"{'品种':<12} {'交易':>6} {'多头':>5} {'空头':>5} {'收益':>10} {'夏普':>8}")
    print("-" * 55)
    
    for r in all_results:
        status = "✅" if r['sharpe'] > 0 else "⚠️"
        print(f"{status} {r['symbol']:<10} {r['trades']:>6} {r['long_trades']:>5} {r['short_trades']:>5} {r['total_return']:>+9.1f}% {r['sharpe']:>+7.2f}")
    
    print("-" * 55)
    
    avg_sharpe = np.mean([r['sharpe'] for r in all_results])
    avg_return = np.mean([r['total_return'] for r in all_results])
    
    print()
    print("📈 评估:")
    if avg_sharpe > 5:
        print("   ✅ 策略非常稳定 (夏普 > 5)")
    elif avg_sharpe > 2:
        print("   ✅ 策略稳定 (夏普 > 2)")
    elif avg_sharpe > 0:
        print("   ⚠️ 策略可用，但波动较大 (夏普 > 0)")
    else:
        print("   ❌ 策略需要优化")
        print()
        print("💡 建议:")
        print("   1. 数字货币波动太大，双边交易不适合")
        print("   2. 建议只在趋势明确时交易单一方向")
        print("   3. 或者使用更长的周期(如日线)")
    
    # 保存
    result = {
        'config': STRATEGY_CONFIG,
        'results': all_results,
        'avg_sharpe': avg_sharpe,
        'avg_return': avg_return,
    }
    
    result_path = "/Users/chusungang/workspace/vnpy-strategies/result/crypto"
    os.makedirs(result_path, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    json_path = f"{result_path}/bidirectional_conservative_{date_str}.json"
    
    with open(json_path, 'w') as f:
        json.dump(result, f, indent=2)
    
    print()
    print(f"💾 结果已保存: {json_path}")


if __name__ == "__main__":
    run_backtest()
