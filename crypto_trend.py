#!/usr/bin/env python3
"""
数字货币趋势策略回测
K019 Trend 策略适配数字货币
"""

import sys
import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime

SYMBOLS = [
    {"symbol": "BTCUSDT", "name": "比特币", "weight": 0.40},
    {"symbol": "ETHUSDT", "name": "以太坊", "weight": 0.30},
    {"symbol": "SOLUSDT", "name": "索拉纳", "weight": 0.15},
    {"symbol": "BNBUSDT", "name": "币安币", "weight": 0.10},
    {"symbol": "XRPUSDT", "name": "瑞波币", "weight": 0.05},
]

# K019 Trend 优化参数（数字货币版）
TREND_CONFIG = {
    "ma_fast": 5,
    "ma_slow": 20,
    "ma_trend": 60,        # MA60趋势过滤
    "atr_period": 14,
    "stop_loss": 0.03,     # 3%止损
    "take_profit": 0.08,   # 8%止盈
}


def get_binance_kline(symbol, interval='4h', limit=2000):
    """获取Binance K线数据（4小时周期）"""
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
    if len(df) < 60:
        return None
    
    close = df['close'].iloc[-1]
    ma5 = df['close'].rolling(5).mean().iloc[-1]
    ma20 = df['close'].rolling(20).mean().iloc[-1]
    ma60 = df['close'].rolling(60).mean().iloc[-1]
    atr = df['close'].rolling(14).std().iloc[-1]
    
    return {
        'close': close,
        'ma5': ma5,
        'ma20': ma20,
        'ma60': ma60,
        'atr': atr,
    }


def backtest_trend(df, symbol, config):
    """趋势策略回测"""
    position = 0
    entry_price = 0
    trades = []
    
    for i in range(60, len(df)):
        window = df.iloc[:i+1]
        ind = calculate_indicators(window)
        
        if ind is None:
            continue
        
        close = ind['close']
        ma5 = ind['ma5']
        ma20 = ind['ma20']
        ma60 = ind['ma60']
        
        # 只在多头趋势时买入
        in_uptrend = close > ma60 and ma20 > ma60
        
        signal = "HOLD"
        
        if position > 0:
            # 金叉死叉平仓
            if ma5 < ma20:
                signal = "CLOSE"
            # 止损/止盈
            if close < entry_price * (1 - config['stop_loss']):
                signal = "CLOSE"
            elif close > entry_price * (1 + config['take_profit']):
                signal = "CLOSE"
        else:
            # 金叉 + 多头趋势 = 买入
            if ma5 > ma20 and in_uptrend:
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
    print("📊 数字货币趋势策略回测（K019 Trend）")
    print("=" * 60)
    print()
    
    print("📋 策略参数:")
    print(f"   MA快速: {TREND_CONFIG['ma_fast']}")
    print(f"   MA慢速: {TREND_CONFIG['ma_slow']}")
    print(f"   MA趋势: {TREND_CONFIG['ma_trend']}")
    print(f"   止损: {TREND_CONFIG['stop_loss']*100}%")
    print(f"   止盈: {TREND_CONFIG['take_profit']*100}%")
    print()
    print("📋 交易周期: 4小时")
    print("📋 只在多头趋势时买入")
    print()
    
    all_results = []
    
    for s in SYMBOLS:
        symbol = s['symbol']
        print(f"📊 回测 {symbol}...")
        
        try:
            df = get_binance_kline(symbol, interval='4h', limit=2000)
            trades = backtest_trend(df, symbol, TREND_CONFIG)
            
            if trades:
                pnls = [t.get('pnl', 0) for t in trades if 'pnl' in t]
                total_ret = (1 + sum([(1+p) for p in pnls])) - 1 if pnls else 0
                sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(6*365) if np.std(pnls) > 0 else 0
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
            
            status = "✅" if result['sharpe'] > 0 else "⚠️"
            print(f"   {status} {symbol}: {result['trades']}笔, 胜率: {result['win_rate']*100:.0f}%, 收益: {result['total_return']*100:+.1f}%, 夏普: {result['sharpe']:+.2f}")
            all_results.append(result)
            
        except Exception as e:
            print(f"   ❌ {symbol} 失败: {e}")
    
    # 计算组合
    portfolio_return = sum([r['total_return'] * r['weight'] for r in all_results])
    positive_sharpe = sum(1 for r in all_results if r['sharpe'] > 0)
    
    print()
    print("=" * 60)
    print("📊 回测结果汇总")
    print("=" * 60)
    print()
    print(f"{'品种':<12} {'交易数':>6} {'胜率':>6} {'收益':>10} {'夏普':>8}")
    print("-" * 50)
    
    for r in all_results:
        status = "✅" if r['sharpe'] > 0 else "⚠️"
        print(f"{status} {r['symbol']:<10} {r['trades']:>6} {r['win_rate']*100:>5.0f}% {r['total_return']*100:>+9.1f}% {r['sharpe']:>+7.2f}")
    
    print("-" * 50)
    print(f"📈 组合收益: {portfolio_return*100:+.1f}%")
    print(f"📊 正夏普: {positive_sharpe}/{len(all_results)}")
    print()
    
    # 保存
    result_path = "/Users/chusungang/workspace/vnpy-strategies/result/crypto"
    os.makedirs(result_path, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    json_path = f"{result_path}/crypto_trend_{date_str}.json"
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'date': date_str,
            'config': TREND_CONFIG,
            'symbols': SYMBOLS,
            'results': all_results,
            'portfolio_return': portfolio_return,
        }, f, ensure_ascii=False, indent=2)
    
    print(f"💾 结果已保存: {json_path}")
    
    return all_results


if __name__ == "__main__":
    run_backtest()
