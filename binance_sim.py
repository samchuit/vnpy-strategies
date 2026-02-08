#!/usr/bin/env python3
"""
Binance 模拟交易 - 完整历史数据
"""

import sys
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict

# 配置
TRADE_CONFIG = {
    "capital_cny": 10000,
    "leverage": 2,
    "symbols": [
        {"symbol": "BTCUSDT", "weight": 0.50, "stop_loss": 0.02, "take_profit": 0.08},
        {"symbol": "ETHUSDT", "weight": 0.30, "stop_loss": 0.02, "take_profit": 0.08},
        {"symbol": "SOLUSDT", "weight": 0.20, "stop_loss": 0.02, "take_profit": 0.08},
    ],
    "strategy": {
        "ma_fast": 10,
        "ma_slow": 20,
        "ma_trend": 90,
    },
}


def get_all_klines(symbol, interval='4h'):
    """获取全部历史数据"""
    all_data = []
    
    # 分批获取 (Binance限制1000条)
    for i in range(4):
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=1000&startTime={i*1000*4*3600000}"
        
        try:
            response = requests.get(url, timeout=30)
            data = response.json()
            
            if not data:
                break
            
            all_data.extend(data)
            
        except Exception as e:
            print(f"获取{symbol}批次{i+1}失败: {e}")
            break
    
    # 处理数据
    df = []
    for k in all_data:
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


def run_simulation():
    """运行模拟"""
    print("=" * 60)
    print("🚀 Binance 模拟交易")
    print("=" * 60)
    
    initial_cash = TRADE_CONFIG['capital_cny'] / 7.2
    cash = initial_cash
    total_trades = 0
    wins = 0
    losses = 0
    all_trades = []
    
    for s in TRADE_CONFIG['symbols']:
        symbol = s['symbol']
        weight = s['weight']
        stop_loss = s['stop_loss']
        take_profit = s['take_profit']
        
        print(f"\n📊 模拟 {symbol}...")
        
        # 获取数据
        df = get_all_klines(symbol, interval='4h')
        print(f"   获取 {len(df)} 条数据")
        
        if len(df) < 100:
            print(f"   ❌ 数据不足")
            continue
        
        closes = [k['close'] for k in df]
        
        # 模拟交易
        position = 0
        entry_price = 0
        symbol_cash = cash * weight
        
        for i in range(90, len(closes)):
            close = closes[i]
            
            # 计算MA
            ma_fast = calculate_ma(closes[:i+1], TRADE_CONFIG['strategy']['ma_fast'])
            ma_slow = calculate_ma(closes[:i+1], TRADE_CONFIG['strategy']['ma_slow'])
            ma_trend = calculate_ma(closes[:i+1], TRADE_CONFIG['strategy']['ma_trend'])
            
            in_uptrend = close > ma_trend and ma_slow > ma_trend
            
            # 交易信号
            signal = "HOLD"
            
            if position > 0:
                if ma_fast < ma_slow:
                    signal = "CLOSE"
                elif close < entry_price * (1 - stop_loss):
                    signal = "CLOSE (SL)"
                elif close > entry_price * (1 + take_profit):
                    signal = "CLOSE (TP)"
            else:
                if ma_fast > ma_slow and in_uptrend:
                    signal = "LONG"
            
            # 执行交易
            if signal == "LONG" and position == 0:
                position = 1
                entry_price = close
                
            elif 'CLOSE' in signal and position > 0:
                pnl = (close - entry_price) / entry_price
                cash += pnl * symbol_cash
                total_trades += 1
                
                if pnl > 0:
                    wins += 1
                else:
                    losses += 1
                
                all_trades.append({
                    'symbol': symbol,
                    'type': 'BUY->SELL',
                    'entry': entry_price,
                    'exit': close,
                    'pnl': pnl * 100,
                    'reason': signal,
                })
                
                position = 0
        
        print(f"   交易次数: {all_trades[-10:]}")
    
    # 结果
    total_return = (cash - initial_cash) / initial_cash * 100
    
    print()
    print("=" * 60)
    print("📊 模拟结果")
    print("=" * 60)
    print(f"💰 初始资金: {initial_cash:.2f} USD")
    print(f"💰 最终资金: {cash:.2f} USD")
    print(f"📈 总收益: {total_return:.1f}%")
    print(f"📊 总交易: {total_trades}")
    print(f"   盈利: {wins}")
    print(f"   亏损: {losses}")
    if total_trades > 0:
        print(f"   胜率: {wins/total_trades*100:.0f}%")
    
    print()
    print("📝 交易记录 (最近10笔):")
    print("-" * 60)
    for t in all_trades[-10:]:
        print(f"   {t['symbol']} {t['type']} {t['entry']:.2f}->{t['exit']:.2f} {t['pnl']:+.2f}%")
    
    # 保存
    result = {
        'config': TRADE_CONFIG,
        'initial_cash': initial_cash,
        'final_cash': cash,
        'total_return': total_return,
        'total_trades': total_trades,
        'wins': wins,
        'losses': losses,
        'trades': all_trades,
    }
    
    result_path = "/Users/chusungang/workspace/vnpy-strategies/result/crypto"
    os.makedirs(result_path, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    json_path = f"{result_path}/sim_trade_{date_str}.json"
    
    with open(json_path, 'w') as f:
        json.dump(result, f, indent=2)
    
    print()
    print(f"💾 结果已保存: {json_path}")


if __name__ == "__main__":
    import os
    run_simulation()
