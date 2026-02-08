#!/usr/bin/env python3
"""
双边策略回测 (做多做空)
验证在牛熊市都能盈利
"""

import sys
import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict

# 配置
SYMBOLS = [
    {"symbol": "BTCUSDT", "weight": 0.50},
    {"symbol": "ETHUSDT", "weight": 0.30},
    {"symbol": "SOLUSDT", "weight": 0.20},
]

STRATEGY_CONFIG = {
    "ma_fast": 10,
    "ma_slow": 20,
    "ma_trend": 120,  # 增加到120周期，长期趋势
    "stop_loss": 0.02,
    "take_profit": 0.10,  # 止盈增加到10%
}


def get_binance_klines(symbol, interval='4h', limit=1000):
    """获取K线数据"""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url, timeout=30)
    data = response.json()
    
    df = []
    for k in data:
        df.append({
            'time': k[0],
            'open': float(k[1]),
            'high': float(k[2]),
            'low': float(k[3]),
            'close': float(k[4]),
            'volume': float(k[5]),
        })
    
    return df


def calculate_ma(prices: List[float], period: int) -> float:
    """计算MA"""
    if len(prices) < period:
        return prices[-1] if prices else 0
    return sum(prices[-period:]) / period


def backtest_bidirectional(symbol, df, config):
    """
    双边策略回测
    
    规则:
    - 多头趋势(价格>MA90 & MA20>MA90) & MA10>MA20 → 做多
    - 空头趋势(价格<MA90 & MA20<MA90) & MA10<MA20 → 做空
    - 震荡: 不交易
    """
    ma_fast = config['ma_fast']
    ma_slow = config['ma_slow']
    ma_trend = config['ma_trend']
    stop_loss = config['stop_loss']
    take_profit = config['take_profit']
    
    closes = [k['close'] for k in df]
    max_ma = max(ma_fast, ma_slow, ma_trend)
    
    position = 0  # 1: 多头, -1: 空头, 0: 无
    entry_price = 0
    trades = []
    long_trades = 0
    short_trades = 0
    long_wins = 0
    short_wins = 0
    
    for i in range(max_ma, len(closes)):
        close = closes[i]
        
        # 计算MA
        ma_fast_val = calculate_ma(closes[:i+1], ma_fast)
        ma_slow_val = calculate_ma(closes[:i+1], ma_slow)
        ma_trend_val = calculate_ma(closes[:i+1], ma_trend)
        
        # 判断趋势
        in_uptrend = close > ma_trend_val and ma_slow_val > ma_trend_val
        in_downtrend = close < ma_trend_val and ma_slow_val < ma_trend_val
        
        signal = "HOLD"
        
        # 持有多头
        if position == 1:
            if ma_fast_val < ma_slow_val:  # 死叉
                signal = "CLOSE_LONG"
            elif close < entry_price * (1 - stop_loss):
                signal = "CLOSE_LONG_SL"
            elif close > entry_price * (1 + take_profit):
                signal = "CLOSE_LONG_TP"
        
        # 持有空头
        elif position == -1:
            if ma_fast_val > ma_slow_val:  # 金叉
                signal = "CLOSE_SHORT"
            elif close > entry_price * (1 + stop_loss):
                signal = "CLOSE_SHORT_SL"
            elif close < entry_price * (1 - take_profit):
                signal = "CLOSE_SHORT_TP"
        
        # 无持仓
        else:
            if in_uptrend and ma_fast_val > ma_slow_val:
                signal = "OPEN_LONG"
            elif in_downtrend and ma_fast_val < ma_slow_val:
                signal = "OPEN_SHORT"
        
        # 执行交易
        if signal == "OPEN_LONG" and position == 0:
            position = 1
            entry_price = close
            long_trades += 1
        
        elif signal == "OPEN_SHORT" and position == 0:
            position = -1
            entry_price = close
            short_trades += 1
        
        elif "CLOSE" in signal and position != 0:
            if position == 1:
                pnl = (close - entry_price) / entry_price
                if pnl > 0:
                    long_wins += 1
            else:
                pnl = (entry_price - close) / entry_price
                if pnl > 0:
                    short_wins += 1
            
            trades.append({
                'symbol': symbol,
                'type': signal,
                'entry': entry_price,
                'exit': close,
                'pnl': pnl * 100 if position == 1 else -(pnl * 100),
                'time': str(i),
            })
            
            position = 0
    
    # 计算指标
    pnls = [t['pnl'] for t in trades]
    
    if not pnls:
        return None
    
    total_ret = sum([(1 + p/100) for p in pnls]) - 1
    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(6*365) if np.std(pnls) > 0 else 0
    win_rate = sum(1 for p in pnls if p > 0) / len(pnls)
    
    return {
        'symbol': symbol,
        'trades': len(trades),
        'long_trades': long_trades,
        'short_trades': short_trades,
        'long_wins': long_wins,
        'short_wins': short_wins,
        'total_return': total_ret * 100,
        'sharpe': sharpe,
        'win_rate': win_rate * 100,
        'trades_detail': trades,
    }


def run_backtest():
    """运行回测"""
    print("=" * 70)
    print("📊 双边策略回测 (做多做空)")
    print("=" * 70)
    print()
    print("📋 策略规则:")
    print("   • 多头趋势 & MA10>MA20 → 做多")
    print("   • 空头趋势 & MA10<MA20 → 做空")
    print("   • 震荡 → 不交易")
    print("   • 止损2%, 止盈8%")
    print()
    
    all_results = []
    
    for s in SYMBOLS:
        symbol = s['symbol']
        print(f"📊 回测 {symbol}...")
        
        # 获取数据
        df = get_binance_klines(symbol, interval='4h', limit=4000)
        print(f"   获取 {len(df)} 条数据")
        
        if len(df) < 100:
            print(f"   ❌ 数据不足")
            continue
        
        # 回测
        result = backtest_bidirectional(symbol, df, STRATEGY_CONFIG)
        
        if result:
            print(f"   ✅ {symbol}: {result['trades']}笔交易, 收益: {result['total_return']:+.1f}%, 夏普: {result['sharpe']:+.2f}")
            print(f"      多头: {result['long_trades']}笔 ({result['long_wins']}胜)")
            print(f"      空头: {result['short_trades']}笔 ({result['short_wins']}胜)")
            
            all_results.append(result)
    
    # 汇总
    print()
    print("=" * 70)
    print("📊 回测结果汇总")
    print("=" * 70)
    print()
    
    total_long = sum(r['long_trades'] for r in all_results)
    total_short = sum(r['short_trades'] for r in all_results)
    avg_sharpe = np.mean([r['sharpe'] for r in all_results])
    
    print(f"{'品种':<12} {'交易数':>8} {'多头':>6} {'空头':>6} {'收益':>10} {'夏普':>8}")
    print("-" * 60)
    
    for r in all_results:
        status = "✅" if r['sharpe'] > 0 else "⚠️"
        print(f"{status} {r['symbol']:<10} {r['trades']:>8} {r['long_trades']:>6} {r['short_trades']:>6} {r['total_return']:>+9.1f}% {r['sharpe']:>+7.2f}")
    
    print("-" * 60)
    print(f"{'合计':<12} {sum(r['trades'] for r in all_results):>8} {total_long:>6} {total_short:>6}")
    print()
    
    print("📈 策略评估:")
    if avg_sharpe > 5:
        print("   ✅ 策略非常稳定 (夏普 > 5)")
    elif avg_sharpe > 2:
        print("   ✅ 策略稳定 (夏普 > 2)")
    elif avg_sharpe > 0:
        print("   ⚠️ 策略可用，但波动较大 (夏普 > 0)")
    else:
        print("   ❌ 策略需要优化 (夏普 < 0)")
    
    # 牛市vs熊市对比
    print()
    print("📊 多空对比:")
    long_win_rate = sum(r['long_wins'] for r in all_results) / total_long * 100 if total_long > 0 else 0
    short_win_rate = sum(r['short_wins'] for r in all_results) / total_short * 100 if total_short > 0 else 0
    print(f"   做多胜率: {long_win_rate:.0f}%")
    print(f"   做空胜率: {short_win_rate:.0f}%")
    
    # 保存结果
    result = {
        'config': STRATEGY_CONFIG,
        'symbols': SYMBOLS,
        'results': all_results,
        'avg_sharpe': avg_sharpe,
        'total_long': total_long,
        'total_short': total_short,
        'long_win_rate': long_win_rate,
        'short_win_rate': short_win_rate,
    }
    
    result_path = "/Users/chusungang/workspace/vnpy-strategies/result/crypto"
    os.makedirs(result_path, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    json_path = f"{result_path}/bidirectional_backtest_{date_str}.json"
    
    with open(json_path, 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print()
    print(f"💾 结果已保存: {json_path}")
    
    return result


if __name__ == "__main__":
    run_backtest()
