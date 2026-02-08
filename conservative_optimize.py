#!/usr/bin/env python3
"""
保守版策略参数优化
针对BTC/ETH/SOL寻找最佳参数
"""

import sys
import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import itertools

# 基础配置
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# 参数搜索空间
PARAM_GRID = {
    "ma_fast": [5, 10],
    "ma_slow": [20, 30],
    "ma_trend": [60, 90, 120],
    "stop_loss": [0.02, 0.03],
    "take_profit": [0.10, 0.15, 0.20],
}


def get_binance_klines(symbol, interval='4h', limit=2000):
    """获取K线"""
    all_data = []
    
    for i in range(4):  # 获取约1年数据
        try:
            url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}&startTime={i*1000*4*3600000}"
            response = requests.get(url, timeout=30)
            data = response.json()
            if not data:
                break
            all_data.extend(data)
        except:
            break
    
    df = []
    for k in all_data:
        df.append({'close': float(k[4])})
    
    return df


def calculate_ma(prices, period):
    if len(prices) < period:
        return prices[-1] if prices else 0
    return sum(prices[-period:]) / period


def backtest(df, config):
    """回测"""
    ma_fast = config['ma_fast']
    ma_slow = config['ma_slow']
    ma_trend = config['ma_trend']
    stop_loss = config['stop_loss']
    take_profit = config['take_profit']
    
    closes = [k['close'] for k in df]
    max_ma = max(ma_fast, ma_slow, ma_trend)
    
    if len(closes) < max_ma + 100:
        return None
    
    position = 0
    entry_price = 0
    pnls = []
    
    for i in range(max_ma, len(closes)):
        close = closes[i]
        
        ma5 = calculate_ma(closes[:i+1], 5)
        ma20 = calculate_ma(closes[:i+1], ma_slow)
        ma60 = calculate_ma(closes[:i+1], ma_trend)
        
        long_condition = (close > ma60 and ma20 > ma60 and ma5 > ma20)
        short_condition = (close < ma60 and not (ma20 > ma60) and ma5 < ma20)
        
        if position == 1:
            if ma5 < ma20 or close < entry_price * (1 - stop_loss) or close > entry_price * (1 + take_profit):
                pnl = (close - entry_price) / entry_price
                pnls.append(pnl)
                position = 0
        
        elif position == -1:
            if ma5 > ma20 or close > entry_price * (1 + stop_loss) or close < entry_price * (1 - take_profit):
                pnl = (entry_price - close) / entry_price
                pnls.append(pnl)
                position = 0
        
        else:
            if long_condition:
                position = 1
                entry_price = close
            elif short_condition:
                position = -1
                entry_price = close
    
    if not pnls:
        return None
    
    total_ret = sum([(1 + p) for p in pnls]) - 1
    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(6*365) if np.std(pnls) > 0 else -999
    
    return {
        'sharpe': sharpe,
        'total_return': total_ret * 100,
        'trades': len(pnls),
        'win_rate': sum(1 for p in pnls if p > 0) / len(pnls) * 100,
    }


def optimize_for_symbol(symbol):
    """为单个品种优化"""
    print(f"\n{'='*60}")
    print(f"Optimizing: {symbol}")
    print(f"{'='*60}")
    
    df = get_binance_klines(symbol, interval='4h', limit=2000)
    print(f"Data: {len(df)} records")
    
    keys = list(PARAM_GRID.keys())
    values = list(PARAM_GRID.values())
    combinations = list(itertools.product(*values))
    
    print(f"Testing {len(combinations)} combinations...")
    
    results = []
    for i, combo in enumerate(combinations):
        config = dict(zip(keys, combo))
        result = backtest(df, config)
        
        if result:
            result['config'] = config
            results.append(result)
        
        if (i + 1) % 20 == 0:
            print(f"   Progress: {i+1}/{len(combinations)}")
    
    # 按夏普排序
    results.sort(key=lambda x: x['sharpe'], reverse=True)
    
    # Top 10
    print(f"\nTop 10 configurations:")
    print("-" * 80)
    print(f"{'Rank':>4} {'Sharpe':>8} {'Return':>10} {'Trades':>6} {'Win%':>6} {'Config'}")
    print("-" * 80)
    
    for i, r in enumerate(results[:10]):
        cfg = r['config']
        params = f"MA({cfg['ma_fast']}/{cfg['ma_slow']}/{cfg['ma_trend']}) SL{cfg['stop_loss']*100:.0f}% TP{cfg['take_profit']*100:.0f}%"
        print(f"{i+1:>4} {r['sharpe']:>+8.2f} {r['total_return']:>+9.1f}% {r['trades']:>6} {r['win_rate']:>5.0f}% {params}")
    
    # 最佳配置
    best = results[0]
    print(f"\nBest configuration for {symbol}:")
    print(f"   Sharpe: {best['sharpe']:.2f}")
    print(f"   Return: {best['total_return']:.1f}%")
    for k, v in best['config'].items():
        print(f"   {k}: {v}")
    
    return {
        'symbol': symbol,
        'best_config': best['config'],
        'best_sharpe': best['sharpe'],
        'top10': results[:10],
    }


def run_optimization():
    """运行优化"""
    print("=" * 70)
    print("Conservative Strategy Parameter Optimization")
    print("=" * 70)
    print()
    print("Searching for best parameters across BTC/ETH/SOL...")
    print()
    
    all_results = {}
    
    for symbol in SYMBOLS:
        result = optimize_for_symbol(symbol)
        all_results[symbol] = result
    
    # 汇总
    print()
    print("=" * 70)
    print("OVERALL SUMMARY")
    print("=" * 70)
    print()
    
    # 找共同最佳配置
    config_scores = {}
    
    for symbol, result in all_results.items():
        cfg = result['best_config']
        cfg_key = tuple(sorted(cfg.items()))
        
        if cfg_key not in config_scores:
            config_scores[cfg_key] = {'count': 0, 'sharpe_sum': 0, 'config': cfg}
        
        config_scores[cfg_key]['count'] += 1
        config_scores[cfg_key]['sharpe_sum'] += result['best_sharpe']
    
    # 计算平均夏普
    for cfg_key in config_scores:
        config_scores[cfg_key]['avg_sharpe'] = config_scores[cfg_key]['sharpe_sum'] / config_scores[cfg_key]['count']
    
    # 排序
    sorted_configs = sorted(config_scores.values(), key=lambda x: x['avg_sharpe'], reverse=True)
    
    print("Best unified configurations (work well across multiple symbols):")
    print("-" * 80)
    print(f"{'Config':<50} {'Symbols':>10} {'Avg Sharpe':>12}")
    print("-" * 80)
    
    for i, item in enumerate(sorted_configs[:5]):
        cfg = item['config']
        params = f"MA({cfg['ma_fast']}/{cfg['ma_slow']}/{cfg['ma_trend']}) SL{cfg['stop_loss']*100:.0f}% TP{cfg['take_profit']*100:.0f}%"
        print(f"{params:<50} {item['count']:>10} {item['avg_sharpe']:>+11.2f}")
    
    # 最佳统一配置
    best_unified = sorted_configs[0]
    
    print()
    print("=" * 70)
    print("RECOMMENDED CONFIGURATION")
    print("=" * 70)
    print()
    cfg = best_unified['config']
    print(f"Parameters:")
    print(f"   ma_fast: {cfg['ma_fast']}")
    print(f"   ma_slow: {cfg['ma_slow']}")
    print(f"   ma_trend: {cfg['ma_trend']}")
    print(f"   stop_loss: {cfg['stop_loss']}")
    print(f"   take_profit: {cfg['take_profit']}")
    print()
    print(f"Expected performance:")
    print(f"   Average Sharpe: {best_unified['avg_sharpe']:.2f}")
    print(f"   Works on: {best_unified['count']}/3 symbols")
    
    # 保存结果
    result = {
        'date': datetime.now().strftime("%Y-%m-%d %H:%M"),
        'all_results': all_results,
        'best_unified': {
            'config': best_unified['config'],
            'avg_sharpe': best_unified['avg_sharpe'],
        },
    }
    
    result_path = "/Users/chusungang/workspace/vnpy-strategies/result/crypto"
    os.makedirs(result_path, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    json_path = f"{result_path}/conservative_optimize_{date_str}.json"
    
    with open(json_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print()
    print(f"Results saved: {json_path}")
    
    return best_unified['config']


if __name__ == "__main__":
    run_optimization()
