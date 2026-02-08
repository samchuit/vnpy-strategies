#!/usr/bin/env python3
"""
数字货币策略回测 - 优化版
调整参数适应数字货币高波动特性
"""

import sys
import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List

# 数字货币专用配置
SYMBOLS = [
    {"symbol": "BTCUSDT", "name": "比特币", "weight": 0.40},
    {"symbol": "ETHUSDT", "name": "以太坊", "weight": 0.30},
    {"symbol": "SOLUSDT", "name": "索拉纳", "weight": 0.15},
    {"symbol": "BNBUSDT", "name": "币安币", "weight": 0.10},
    {"symbol": "XRPUSDT", "name": "瑞波币", "weight": 0.05},
]

# 优化后的参数（适合数字货币）
CRYPTO_CONFIG = {
    "ma_period": 20,
    "atr_period": 14,
    "atr_multiplier": 3.0,    # 提高到3倍ATR（减少交易频率）
    "stop_loss": 0.05,        # 止损5%（数字货币波动大）
    "take_profit": 0.10,      # 止盈10%
}


def get_binance_kline(symbol, interval='1h', limit=1000):
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


def calculate_indicators(df):
    """计算技术指标"""
    close = df['close'].iloc[-1]
    ma20 = df['close'].rolling(20).mean().iloc[-1]
    atr = df['close'].rolling(14).std().iloc[-1]
    
    return {
        'close': close,
        'ma20': ma20,
        'atr': atr,
    }


def backtest_symbol(df, symbol, config):
    """回测单个品种"""
    position = 0
    entry_price = 0
    trades = []
    
    for i in range(20, len(df)):
        window = df.iloc[:i+1]
        ind = calculate_indicators(window)
        
        if ind is None:
            continue
        
        close = ind['close']
        ma20 = ind['ma20']
        atr = ind['atr']
        
        signal = "HOLD"
        
        # 持有多头
        if position > 0:
            if close > ma20 + atr * config['atr_multiplier']:
                signal = "CLOSE"
            # 止损/止盈
            if close < entry_price * (1 - config['stop_loss']):
                signal = "CLOSE"
            elif close > entry_price * (1 + config['take_profit']):
                signal = "CLOSE"
        else:
            if close < ma20 - atr * config['atr_multiplier']:
                signal = "LONG"
        
        if signal == "LONG" and position == 0:
            position = 1
            entry_price = close
            trades.append({
                'symbol': symbol,
                'type': 'BUY',
                'price': close,
                'time': str(df.index[i]),
            })
        
        elif signal == "CLOSE" and position > 0:
            pnl = (close - entry_price) / entry_price
            trades.append({
                'symbol': symbol,
                'type': 'SELL',
                'price': close,
                'pnl': pnl,
                'time': str(df.index[i]),
            })
            position = 0
    
    return trades


def run_backtest():
    """运行回测"""
    print("=" * 60)
    print("📊 数字货币策略回测（优化版）")
    print("=" * 60)
    print()
    
    print("📋 策略参数:")
    print(f"   MA周期: {CRYPTO_CONFIG['ma_period']}")
    print(f"   ATR周期: {CRYPTO_CONFIG['atr_period']}")
    print(f"   ATR倍数: {CRYPTO_CONFIG['atr_multiplier']}")
    print(f"   止损: {CRYPTO_CONFIG['stop_loss']*100}%")
    print(f"   止盈: {CRYPTO_CONFIG['take_profit']*100}%")
    print()
    
    all_results = []
    
    for s in SYMBOLS:
        symbol = s['symbol']
        print(f"📊 回测 {symbol}...")
        
        try:
            df = get_binance_kline(symbol, interval='1h', limit=1000)
            trades = backtest_symbol(df, symbol, CRYPTO_CONFIG)
            
            if trades:
                pnls = [t.get('pnl', 0) for t in trades if 'pnl' in t]
                total_ret = (1 + sum([(1+p) for p in pnls])) - 1 if pnls else 0
                sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(24*365) if np.std(pnls) > 0 else 0
                win_rate = sum(1 for p in pnls if p > 0) / len(pnls) if pnls else 0
                
                result = {
                    'symbol': symbol,
                    'name': s['name'],
                    'weight': s['weight'],
                    'trades': len(trades),
                    'wins': sum(1 for p in pnls if p > 0),
                    'losses': sum(1 for p in pnls if p <= 0),
                    'win_rate': win_rate,
                    'total_return': total_ret,
                    'sharpe': sharpe,
                    'avg_pnl': np.mean(pnls) if pnls else 0,
                    'max_pnl': max(pnls) if pnls else 0,
                    'min_pnl': min(pnls) if pnls else 0,
                }
            else:
                result = {
                    'symbol': symbol,
                    'name': s['name'],
                    'weight': s['weight'],
                    'trades': 0,
                    'win_rate': 0,
                    'total_return': 0,
                    'sharpe': 0,
                }
            
            print(f"   ✅ {symbol}: {result['trades']}笔, 胜率: {result['win_rate']*100:.0f}%, 收益: {result['total_return']*100:+.1f}%, 夏普: {result['sharpe']:+.2f}")
            all_results.append(result)
            
        except Exception as e:
            print(f"   ❌ {symbol} 失败: {e}")
    
    # 计算组合
    portfolio_return = sum([r['total_return'] * r['weight'] for r in all_results])
    
    print()
    print("=" * 60)
    print("📊 回测结果汇总")
    print("=" * 60)
    print()
    print(f"{'品种':<12} {'交易数':>6} {'胜率':>6} {'收益':>10} {'夏普':>8}")
    print("-" * 50)
    
    for r in all_results:
        print(f"{r['symbol']:<12} {r['trades']:>6} {r['win_rate']*100:>5.0f}% {r['total_return']*100:>+9.1f}% {r['sharpe']:>+7.2f}")
    
    print("-" * 50)
    print(f"{'组合':<12} {'':>6} {'':>6} {portfolio_return*100:>+9.1f}%")
    print()
    
    # 保存
    result_path = "/Users/chusungang/workspace/vnpy-strategies/result/crypto"
    os.makedirs(result_path, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    json_path = f"{result_path}/crypto_v2_{date_str}.json"
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'date': date_str,
            'config': CRYPTO_CONFIG,
            'symbols': SYMBOLS,
            'results': all_results,
            'portfolio_return': portfolio_return,
        }, f, ensure_ascii=False, indent=2)
    
    print(f"💾 结果已保存: {json_path}")
    
    return all_results


if __name__ == "__main__":
    run_backtest()
