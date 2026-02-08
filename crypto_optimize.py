#!/usr/bin/env python3
"""
数字货币策略参数优化
针对BTC/ETH/SOL等品种找最优参数
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

# 目标品种
TARGET_SYMBOL = "BTCUSDT"

# 参数搜索空间
PARAM_GRID = {
    "ma_fast": [5, 10, 15],
    "ma_slow": [20, 30, 40],
    "ma_trend": [60, 90, 120],
    "stop_loss": [0.02, 0.03, 0.05],
    "take_profit": [0.06, 0.08, 0.10, 0.12],
}

# 默认配置
DEFAULT_CONFIG = {
    "ma_fast": 5,
    "ma_slow": 20,
    "ma_trend": 60,
    "stop_loss": 0.03,
    "take_profit": 0.08,
}


def get_binance_kline(symbol, interval='4h', limit=2000):
    """获取Binance K线数据"""
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


def calculate_indicators(df, config):
    """计算技术指标"""
    max_ma = max(config['ma_fast'], config['ma_slow'], config['ma_trend'])
    if len(df) < max_ma:
        return None
    
    close = df['close'].iloc[-1]
    ma_fast = df['close'].rolling(config['ma_fast']).mean().iloc[-1]
    ma_slow = df['close'].rolling(config['ma_slow']).mean().iloc[-1]
    ma_trend = df['close'].rolling(config['ma_trend']).mean().iloc[-1]
    
    return {
        'close': close,
        'ma_fast': ma_fast,
        'ma_slow': ma_slow,
        'ma_trend': ma_trend,
    }


def backtest(df, config):
    """回测单个配置"""
    ma_fast = config['ma_fast']
    ma_slow = config['ma_slow']
    ma_trend = config['ma_trend']
    stop_loss = config['stop_loss']
    take_profit = config['take_profit']
    
    max_ma = max(ma_fast, ma_slow, ma_trend)
    position = 0
    entry_price = 0
    trades = []
    pnls = []
    
    for i in range(max_ma, len(df)):
        window = df.iloc[:i+1]
        ind = calculate_indicators(window, config)
        
        if ind is None:
            continue
        
        close = ind['close']
        
        in_uptrend = close > ind['ma_trend'] and ind['ma_slow'] > ind['ma_trend']
        
        signal = "HOLD"
        
        if position > 0:
            if ind['ma_fast'] < ind['ma_slow']:
                signal = "CLOSE"
            if close < entry_price * (1 - stop_loss):
                signal = "CLOSE"
            elif close > entry_price * (1 + take_profit):
                signal = "CLOSE"
        else:
            if ind['ma_fast'] > ind['ma_slow'] and in_uptrend:
                signal = "LONG"
        
        if signal == "LONG" and position == 0:
            position = 1
            entry_price = close
        
        elif signal == "CLOSE" and position > 0:
            pnl = (close - entry_price) / entry_price
            pnls.append(pnl)
            trades.append({'pnl': pnl})
            position = 0
    
    # 计算指标
    if not pnls:
        return {'sharpe': -999, 'total_return': 0, 'trades': 0, 'config': config}
    
    total_ret = (1 + sum([(1+p) for p in pnls])) - 1
    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(6*365) if np.std(pnls) > 0 else 0
    win_rate = sum(1 for p in pnls if p > 0) / len(pnls)
    
    return {
        'sharpe': sharpe,
        'total_return': total_ret,
        'trades': len(pnls),
        'win_rate': win_rate,
        'config': config,
    }


def optimize_params(symbol):
    """参数优化"""
    print("=" * 60)
    print(f"📊 参数优化 - {symbol}")
    print("=" * 60)
    print()
    
    # 获取数据
    print("📂 获取数据...")
    df = get_binance_kline(symbol, interval='4h', limit=2000)
    print(f"   数据条数: {len(df)}")
    print()
    
    # 生成参数组合
    param_keys = list(PARAM_GRID.keys())
    param_values = list(PARAM_GRID.values())
    combinations = list(itertools.product(*param_values))
    
    print(f"📋 测试 {len(combinations)} 种参数组合...")
    print()
    
    results = []
    
    for i, combo in enumerate(combinations):
        config = dict(zip(param_keys, combo))
        
        result = backtest(df, config)
        results.append(result)
        
        # 每100次显示进度
        if (i + 1) % 100 == 0:
            print(f"   进度: {i+1}/{len(combinations)} ({100*(i+1)//len(combinations)}%)")
    
    # 按夏普排序
    results.sort(key=lambda x: x['sharpe'], reverse=True)
    
    # 显示Top 10
    print()
    print("=" * 60)
    print("🏆 Top 10 参数组合")
    print("=" * 60)
    print()
    print(f"{'排名':>4} {'夏普':>8} {'收益':>10} {'交易数':>6} {'胜率':>6} {'参数'}")
    print("-" * 80)
    
    for i, r in enumerate(results[:10]):
        params = f"MA({r['config']['ma_fast']}/{r['config']['ma_slow']}/{r['config']['ma_trend']}) SL{r['config']['stop_loss']*100:.0f}% TP{r['config']['take_profit']*100:.0f}%"
        print(f"{i+1:>4} {r['sharpe']:>+8.2f} {r['total_return']*100:>+9.1f}% {r['trades']:>6} {r['win_rate']*100:>5.0f}% {params}")
    
    # 最佳配置
    best = results[0]
    print()
    print("=" * 60)
    print("✅ 最佳配置")
    print("=" * 60)
    print()
    print(f"   夏普: {best['sharpe']:.2f}")
    print(f"   收益: {best['total_return']*100:.1f}%")
    print(f"   交易数: {best['trades']}")
    print(f"   胜率: {best['win_rate']*100:.0f}%")
    print()
    print("📋 参数详情:")
    for k, v in best['config'].items():
        print(f"   {k}: {v}")
    
    # 保存结果
    result_path = "/Users/chusungang/workspace/vnpy-strategies/result/crypto"
    os.makedirs(result_path, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    json_path = f"{result_path}/optimize_{symbol}_{date_str}.json"
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'symbol': symbol,
            'date': date_str,
            'best_config': best['config'],
            'best_sharpe': best['sharpe'],
            'best_return': best['total_return'],
            'top10': results[:10],
            'all_results': [{'config': r['config'], 'sharpe': r['sharpe'], 'return': r['total_return']} for r in results],
        }, f, ensure_ascii=False, indent=2)
    
    print()
    print(f"💾 结果已保存: {json_path}")
    
    return best['config'], results[:10]


def run_all_symbols():
    """运行所有品种优化"""
    symbols = [
        {"symbol": "BTCUSDT", "name": "比特币"},
        {"symbol": "ETHUSDT", "name": "以太坊"},
        {"symbol": "SOLUSDT", "name": "索拉纳"},
    ]
    
    all_best = {}
    
    for s in symbols:
        print()
        print("=" * 80)
        best_config, top10 = optimize_params(s['symbol'])
        all_best[s['symbol']] = {
            'config': best_config,
            'top10': top10,
        }
    
    # 汇总
    print()
    print("=" * 80)
    print("📊 所有品种最佳配置汇总")
    print("=" * 80)
    print()
    
    for symbol, data in all_best.items():
        print(f"📈 {symbol}:")
        cfg = data['config']
        print(f"   MA({cfg['ma_fast']}/{cfg['ma_slow']}/{cfg['ma_trend']}) SL{cfg['stop_loss']*100:.0f}% TP{cfg['take_profit']*100:.0f}%")
        print()


if __name__ == "__main__":
    run_all_symbols()
