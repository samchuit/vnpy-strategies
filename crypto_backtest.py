#!/usr/bin/env python3
"""
数字货币策略回测
基于现有Range Trading和K019策略
"""

import sys
import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List

# 配置
SYMBOLS = [
    {"symbol": "BTCUSDT", "name": "比特币", "weight": 0.40},
    {"symbol": "ETHUSDT", "name": "以太坊", "weight": 0.30},
    {"symbol": "SOLUSDT", "name": "索拉纳", "weight": 0.15},
    {"symbol": "BNBUSDT", "name": "币安币", "weight": 0.10},
    {"symbol": "XRPUSDT", "name": "瑞波币", "weight": 0.05},
]

# Range Trading 参数
RANGE_CONFIG = {
    "ma_period": 20,
    "atr_period": 14,
    "atr_multiplier": 2.0,
    "stop_loss": 0.03,
    "take_profit": 0.06,
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


class CryptoRangeTrading:
    """数字货币Range Trading策略"""
    
    def __init__(self, config=RANGE_CONFIG):
        self.config = config
        self.positions = {}
        self.entry_prices = {}
        self.trades = []
        
    def calculate_indicators(self, df):
        """计算技术指标"""
        close = df['close'].iloc[-1]
        ma20 = df['close'].rolling(20).mean().iloc[-1]
        atr = df['close'].rolling(14).std().iloc[-1]
        
        return {
            'close': close,
            'ma20': ma20,
            'atr': atr,
        }
    
    def generate_signal(self, df):
        """生成交易信号"""
        if len(df) < 20:
            return "HOLD"
        
        ind = self.calculate_indicators(df)
        close = ind['close']
        ma20 = ind['ma20']
        atr = ind['atr']
        
        # 持有多头，检查平仓
        if self.current_position > 0:
            if close > ma20 + atr * self.config['atr_multiplier']:
                return "CLOSE"
            # 止损/止盈
            entry = self.entry_price
            if close < entry * (1 - self.config['stop_loss']):
                return "CLOSE"
            elif close > entry * (1 + self.config['take_profit']):
                return "CLOSE"
        else:
            # 开仓信号
            if close < ma20 - atr * self.config['atr_multiplier']:
                return "LONG"
        
        return "HOLD"
    
    def backtest(self, df, symbol):
        """回测"""
        self.current_position = 0
        self.entry_price = 0
        self.trades = []
        
        for i in range(20, len(df)):
            window = df.iloc[:i+1]
            signal = self.generate_signal(window)
            price = df['close'].iloc[i]
            
            if signal == "LONG" and self.current_position == 0:
                self.current_position = 1
                self.entry_price = price
                self.trades.append({
                    'symbol': symbol,
                    'type': 'BUY',
                    'price': price,
                    'time': str(df.index[i]),
                })
            
            elif signal == "CLOSE" and self.current_position > 0:
                entry = self.entry_price
                pnl = (price - entry) / entry
                self.trades.append({
                    'symbol': symbol,
                    'type': 'SELL',
                    'price': price,
                    'pnl': pnl,
                    'time': str(df.index[i]),
                })
                self.current_position = 0
        
        return self.trades


def run_crypto_backtest():
    """运行数字货币回测"""
    print("=" * 60)
    print("📊 数字货币策略回测")
    print("=" * 60)
    print()
    
    print(f"📋 交易品种: {[s['symbol'] for s in SYMBOLS]}")
    print(f"📋 策略: Range Trading")
    print(f"📋 数据来源: Binance")
    print()
    
    strategy = CryptoRangeTrading()
    all_results = []
    
    for s in SYMBOLS:
        symbol = s['symbol']
        print(f"📊 回测 {symbol}...")
        
        try:
            df = get_binance_kline(symbol, interval='1h', limit=1000)
            trades = strategy.backtest(df, symbol)
            
            # 计算指标
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
                    'win_rate': win_rate,
                    'total_return': total_ret,
                    'sharpe': sharpe,
                    'trades_detail': trades,
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
            
            print(f"   ✅ {symbol}: {result['trades']}笔交易, 收益: {result['total_return']*100:.1f}%, 夏普: {result['sharpe']:.2f}")
            all_results.append(result)
            
        except Exception as e:
            print(f"   ❌ {symbol} 失败: {e}")
    
    # 计算组合收益
    portfolio_return = sum([r['total_return'] * r['weight'] for r in all_results])
    
    print()
    print("=" * 60)
    print("📊 回测结果汇总")
    print("=" * 60)
    
    for r in all_results:
        print(f"   {r['symbol']:10s} ({r['name']}): {r['trades']:3d}笔, 收益: {r['total_return']*100:+6.1f}%, 夏普: {r['sharpe']:+.2f}")
    
    print()
    print(f"📈 组合预期收益: {portfolio_return*100:.1f}%")
    print()
    
    # 保存结果
    result_path = "/Users/chusungang/workspace/vnpy-strategies/result/crypto"
    os.makedirs(result_path, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    json_path = f"{result_path}/crypto_backtest_{date_str}.json"
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'date': date_str,
            'config': RANGE_CONFIG,
            'symbols': SYMBOLS,
            'results': all_results,
            'portfolio_return': portfolio_return,
        }, f, ensure_ascii=False, indent=2)
    
    print(f"💾 结果已保存: {json_path}")
    
    return all_results


def main():
    run_crypto_backtest()


if __name__ == "__main__":
    main()
