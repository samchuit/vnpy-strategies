#!/usr/bin/env python3
"""
双边策略长期回测 - 验证稳定性
与实盘策略对比
"""

import sys
import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# 配置
CONSERVATIVE_CONFIG = {
    "ma_fast": 5,
    "ma_slow": 20,
    "ma_trend": 60,
    "stop_loss": 0.02,
    "take_profit": 0.15,
}

ORIGINAL_CONFIG = {
    "ma_fast": 10,
    "ma_slow": 20,
    "ma_trend": 90,
    "stop_loss": 0.02,
    "take_profit": 0.08,
}

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def get_all_klines(symbol, interval='4h'):
    """获取所有历史K线"""
    all_data = []
    
    for i in range(8):
        try:
            url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=1000&startTime={i*1000*4*3600000}"
            response = requests.get(url, timeout=30)
            data = response.json()
            
            if not data:
                break
            
            all_data.extend(data)
            print(f"   Batch {i+1}: {len(data)} records")
            
        except Exception as e:
            print(f"   Batch {i+1} failed: {e}")
            break
    
    df = []
    for k in all_data:
        df.append({
            'time': k[0],
            'close': float(k[4]),
        })
    
    return df


def calculate_ma(prices, period):
    if len(prices) < period:
        return prices[-1] if prices else 0
    return sum(prices[-period:]) / period


def backtest_bidirectional(df, config):
    """双边策略回测"""
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
        
        long_condition = (close > ma60 and ma20 > ma60 and ma5 > ma20)
        short_condition = (close < ma60 and not (ma20 > ma60) and ma5 < ma20)
        
        if position == 1:
            if ma5 < ma20 or close < entry_price * (1 - stop_loss) or close > entry_price * (1 + take_profit):
                pnl = (close - entry_price) / entry_price
                trades.append({'type': 'LONG', 'pnl': pnl * 100})
                position = 0
        
        elif position == -1:
            if ma5 > ma20 or close > entry_price * (1 + stop_loss) or close < entry_price * (1 - take_profit):
                pnl = (entry_price - close) / entry_price
                trades.append({'type': 'SHORT', 'pnl': pnl * 100})
                position = 0
        
        else:
            if long_condition:
                position = 1
                entry_price = close
            elif short_condition:
                position = -1
                entry_price = close
    
    if not trades:
        return None
    
    pnls = [t['pnl'] for t in trades]
    total_ret = sum([(1 + p/100) for p in pnls]) - 1
    sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(6*365) if np.std(pnls) > 0 else 0
    win_rate = sum(1 for p in pnls if p > 0) / len(pnls) * 100
    
    return {
        'trades': len(trades),
        'total_return': total_ret * 100,
        'sharpe': sharpe,
        'win_rate': win_rate,
        'avg_pnl': np.mean(pnls),
        'max_pnl': max(pnls),
        'min_pnl': min(pnls),
    }


def run_long_term_backtest():
    """长期回测"""
    print("=" * 70)
    print("Long-term Backtest: Bidirectional Strategy")
    print("=" * 70)
    print()
    
    results = {
        'conservative': {},
        'original': {},
    }
    
    for symbol in SYMBOLS:
        print("\n" + "=" * 60)
        print(f"Testing: {symbol}")
        print("=" * 60)
        
        print("\nFetching historical data...")
        df = get_all_klines(symbol, interval='4h')
        
        if len(df) < 100:
            print(f"Insufficient data: {len(df)}")
            continue
        
        start_date = datetime.fromtimestamp(df[0]['time']/1000).strftime('%Y-%m-%d')
        end_date = datetime.fromtimestamp(df[-1]['time']/1000).strftime('%Y-%m-%d')
        years = (df[-1]['time'] - df[0]['time']) / (1000 * 3600 * 24 * 365)
        
        print(f"   Range: {start_date} ~ {end_date}")
        print(f"   Records: {len(df)}")
        print(f"   Years: {years:.1f}")
        
        # Conservative strategy
        print("\n[1] Conservative (MA5/20/60, TP15%):")
        conservative = backtest_bidirectional(df, CONSERVATIVE_CONFIG)
        if conservative:
            print(f"   Trades: {conservative['trades']}")
            print(f"   Return: {conservative['total_return']:+.1f}%")
            print(f"   Sharpe: {conservative['sharpe']:+.2f}")
            print(f"   Win Rate: {conservative['win_rate']:.0f}%")
            results['conservative'][symbol] = conservative
        
        # Original strategy
        print("\n[2] Original (MA10/20/90, TP8%):")
        original = backtest_bidirectional(df, ORIGINAL_CONFIG)
        if original:
            print(f"   Trades: {original['trades']}")
            print(f"   Return: {original['total_return']:+.1f}%")
            print(f"   Sharpe: {original['sharpe']:+.2f}")
            print(f"   Win Rate: {original['win_rate']:.0f}%")
            results['original'][symbol] = original
        
        # Comparison
        if conservative and original:
            print(f"\nComparison:")
            if conservative['sharpe'] > original['sharpe']:
                print(f"   WINNER: Conservative (Sharpe {conservative['sharpe']:.2f} vs {original['sharpe']:.2f})")
            else:
                print(f"   WINNER: Original (Sharpe {original['sharpe']:.2f} vs {conservative['sharpe']:.2f})")
    
    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    
    # Conservative summary
    print("Conservative Strategy:")
    for symbol, r in results['conservative'].items():
        status = "PASS" if r['sharpe'] > 2 else ("OK" if r['sharpe'] > 0 else "FAIL")
        print(f"   {status} {symbol}: Sharpe {r['sharpe']:+.2f}, Return {r['total_return']:+.1f}%")
    
    avg_conservative = np.mean([r['sharpe'] for r in results['conservative'].values()])
    print(f"   Average Sharpe: {avg_conservative:.2f}")
    
    # Original summary
    print()
    print("Original Strategy:")
    for symbol, r in results['original'].items():
        status = "PASS" if r['sharpe'] > 2 else ("OK" if r['sharpe'] > 0 else "FAIL")
        print(f"   {status} {symbol}: Sharpe {r['sharpe']:+.2f}, Return {r['total_return']:+.1f}%")
    
    avg_original = np.mean([r['sharpe'] for r in results['original'].values()])
    print(f"   Average Sharpe: {avg_original:.2f}")
    
    # Conclusion
    print()
    print("=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    
    if avg_conservative > avg_original:
        print()
        print("WINNER: Conservative Strategy")
        print(f"   Conservative Avg Sharpe: {avg_conservative:.2f}")
        print(f"   Original Avg Sharpe: {avg_original:.2f}")
        print("   Recommendation: Use conservative strategy")
    else:
        print()
        print("WINNER: Original Strategy")
        print(f"   Original Avg Sharpe: {avg_original:.2f}")
        print(f"   Conservative Avg Sharpe: {avg_conservative:.2f}")
        print("   Recommendation: Continue with original strategy")
    
    # Save results
    result_path = "/Users/chusungang/workspace/vnpy-strategies/result/crypto"
    os.makedirs(result_path, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    json_path = f"{result_path}/longterm_comparison_{date_str}.json"
    
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print()
    print(f"Results saved: {json_path}")


if __name__ == "__main__":
    run_long_term_backtest()
