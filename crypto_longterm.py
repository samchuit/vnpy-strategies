#!/usr/bin/env python3
"""
数字货币长期回测 - 2年数据
验证策略稳定性
"""

import sys
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 配置
SYMBOL = "BTCUSDT"
INTERVAL = "4h"  # 4小时周期

# 最佳配置（从优化结果）
BEST_CONFIG = {
    "ma_fast": 10,
    "ma_slow": 20,
    "ma_trend": 90,
    "stop_loss": 0.02,
    "take_profit": 0.08,
}


def get_binance_kline(symbol, interval, limit=1000):
    """获取Binance K线数据"""
    url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
    response = requests.get(url, timeout=30)
    return response.json()


def merge_data(symbol, interval, target_years=2):
    """合并数据以获取更长时间范围"""
    # 4小时K线：1000条 ≈ 7个月
    # 目标2年：需要约 2 * 12 / 7 * 1000 ≈ 3400 条
    # 分批获取
    
    all_data = []
    
    # Binance API限制单次最多1000条
    # 需要分4批获取，每批偏移1000条
    
    print(f"📂 获取 {symbol} {interval} 数据...")
    
    for i in range(4):  # 获取约2.5-3年数据
        try:
            url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=1000&startTime={i*1000*4*3600000}'
            response = requests.get(url, timeout=30)
            data = response.json()
            
            if not data:
                break
            
            all_data.extend(data)
            print(f"   批次 {i+1}: {len(data)} 条")
            
        except Exception as e:
            print(f"   批次 {i+1} 失败: {e}")
            break
    
    print(f"   总计: {len(all_data)} 条数据")
    
    return all_data


def process_data(data):
    """处理数据"""
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


def backtest_2years(df, config):
    """2年回测"""
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
    
    print(f"\n📊 开始回测...")
    print(f"   总K线: {len(df)}")
    print(f"   时间范围: {df.index[0]} ~ {df.index[-1]}")
    
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
                trades.append({
                    'type': 'SELL',
                    'price': close,
                    'pnl': pnl,
                    'time': str(df.index[i]),
                })
                position = 0
            elif close < entry_price * (1 - stop_loss):
                pnl = (close - entry_price) / entry_price
                pnls.append(pnl)
                trades.append({
                    'type': 'SELL (SL)',
                    'price': close,
                    'pnl': pnl,
                    'time': str(df.index[i]),
                })
                position = 0
            elif close > entry_price * (1 + take_profit):
                pnl = (close - entry_price) / entry_price
                pnls.append(pnl)
                trades.append({
                    'type': 'SELL (TP)',
                    'price': close,
                    'pnl': pnl,
                    'time': str(df.index[i]),
                })
                position = 0
        else:
            if ma_fast_val > ma_slow_val and in_uptrend:
                position = 1
                entry_price = close
                trades.append({
                    'type': 'BUY',
                    'price': close,
                    'time': str(df.index[i]),
                })
    
    return trades, pnls


def calculate_metrics(pnls):
    """计算指标"""
    if not pnls:
        return None
    
    total_ret = (1 + sum([(1+p) for p in pnls])) - 1
    
    # 年化夏普 (4小时周期 ≈ 6*365 = 2190根/年)
    if np.std(pnls) > 0:
        sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(6*365)
    else:
        sharpe = 0
    
    win_rate = sum(1 for p in pnls if p > 0) / len(pnls)
    avg_pnl = np.mean(pnls)
    max_pnl = max(pnls)
    min_pnl = min(pnls)
    
    # 最大回撤
    cumulative = [(1 + sum([(1+p) for p in pnls[:i+1]])) - 1 for i in range(len(pnls))]
    max_dd = max([c - max(cumulative[:i+1]) for i, c in enumerate(cumulative)]) if cumulative else 0
    
    return {
        'sharpe': sharpe,
        'total_return': total_ret,
        'annual_return': total_ret / (len(pnls) / 6 / 365) * 365 if pnls else 0,  # 年化收益
        'trades': len(pnls),
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'max_pnl': max_pnl,
        'min_pnl': min_pnl,
        'max_drawdown': max_dd,
    }


def run_long_term_backtest():
    """运行长期回测"""
    print("=" * 70)
    print("📊 数字货币长期回测 - 2年数据")
    print("=" * 70)
    print()
    
    # 获取数据
    raw_data = merge_data(SYMBOL, INTERVAL, target_years=2)
    
    if not raw_data:
        print("❌ 获取数据失败")
        return
    
    df = process_data(raw_data)
    
    # 计算时间范围
    start_date = df.index[0]
    end_date = df.index[-1]
    duration_days = (end_date - start_date).days
    
    print()
    print(f"📅 时间范围: {start_date} ~ {end_date}")
    print(f"📅 持续时间: {duration_days} 天 ({duration_days/365:.1f} 年)")
    print()
    
    # 回测
    trades, pnls = backtest_2years(df, BEST_CONFIG)
    
    # 计算指标
    metrics = calculate_metrics(pnls)
    
    if metrics is None:
        print("❌ 无交易信号")
        return
    
    # 显示结果
    print()
    print("=" * 70)
    print("📊 回测结果")
    print("=" * 70)
    print()
    print(f"📋 策略配置:")
    print(f"   MA({BEST_CONFIG['ma_fast']}/{BEST_CONFIG['ma_slow']}/{BEST_CONFIG['ma_trend']})")
    print(f"   止损: {BEST_CONFIG['stop_loss']*100}%")
    print(f"   止盈: {BEST_CONFIG['take_profit']*100}%")
    print()
    
    print("📈 收益指标:")
    print(f"   总收益: {metrics['total_return']*100:.1f}%")
    print(f"   年化收益: {metrics['annual_return']*100:.1f}%")
    print(f"   夏普比率: {metrics['sharpe']:.2f}")
    print(f"   最大回撤: {metrics['max_drawdown']*100:.1f}%")
    print()
    
    print("📊 交易统计:")
    print(f"   总交易次数: {metrics['trades']}")
    print(f"   胜率: {metrics['win_rate']*100:.0f}%")
    print(f"   平均盈亏: {metrics['avg_pnl']*100:.2f}%")
    print(f"   最大盈利: {metrics['max_pnl']*100:.1f}%")
    print(f"   最大亏损: {metrics['min_pnl']*100:.1f}%")
    print()
    
    # 交易记录
    print("📝 交易记录:")
    print("-" * 70)
    for i, t in enumerate(trades[-20:]):  # 显示最近20笔
        pnl_str = f"{t['pnl']*100:+.2f}%" if 'pnl' in t else ""
        print(f"   {t['time'][:19]} {t['type']:>8} @ {t['price']:.2f} {pnl_str}")
    
    if len(trades) > 20:
        print(f"   ... 共 {len(trades)} 笔交易")
    
    # 保存结果
    result = {
        'symbol': SYMBOL,
        'interval': INTERVAL,
        'period': f"{start_date} ~ {end_date}",
        'duration_days': duration_days,
        'config': BEST_CONFIG,
        'metrics': metrics,
        'trades': trades,
    }
    
    result_path = "/Users/chusungang/workspace/vnpy-strategies/result/crypto"
    os.makedirs(result_path, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    json_path = f"{result_path}/longterm_{SYMBOL}_{date_str}.json"
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print()
    print("=" * 70)
    print(f"💾 结果已保存: {json_path}")
    
    # 稳定性评估
    print()
    print("📊 稳定性评估:")
    
    if metrics['sharpe'] > 5:
        print("   ✅ 夏普 > 5: 策略非常稳定")
    elif metrics['sharpe'] > 2:
        print("   ✅ 夏普 > 2: 策略稳定")
    elif metrics['sharpe'] > 0:
        print("   ⚠️ 夏普 > 0: 策略可用，但需注意")
    else:
        print("   ❌ 夏普 < 0: 策略需要重新优化")
    
    if metrics['trades'] < 30:
        print(f"   ⚠️ 交易次数 {metrics['trades']} 较少，建议继续观察")
    else:
        print(f"   ✅ 交易次数 {metrics['trades']} 足够验证策略")


if __name__ == "__main__":
    import os
    run_long_term_backtest()
