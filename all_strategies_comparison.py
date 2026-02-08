#!/usr/bin/env python3
"""
所有策略统一回测对比
使用迅投60分钟真实数据
"""

import numpy as np
import pandas as pd
import os
import json
from datetime import datetime
from typing import Dict, List

DATA_DIR = "/Users/chusungang/workspace/vnpy_strategy/data_minute"
RESULT_DIR = "/Users/chusungang/workspace/vnpy_strategy/result"
os.makedirs(RESULT_DIR, exist_ok=True)

# 策略结果存储
STRATEGY_RESULTS = {}


def load_data(symbol: str) -> pd.DataFrame:
    """加载60分钟数据"""
    file_path = os.path.join(DATA_DIR, f"{symbol}_60.csv")
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        return df
    return None


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """准备技术指标"""
    df = df.copy()
    
    # 均线
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    
    # OBV
    obv = [0]
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['close'].iloc[i-1]:
            obv.append(obv[-1] + df['vol'].iloc[i])
        elif df['close'].iloc[i] < df['close'].iloc[i-1]:
            obv.append(obv[-1] - df['vol'].iloc[i])
        else:
            obv.append(obv[-1])
    df['obv'] = obv
    df['obv_ma5'] = df['obv'].rolling(5).mean()
    df['obv_ma10'] = df['obv'].rolling(10).mean()
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    
    # 收益率
    df['return'] = df['close'].pct_change()
    
    return df.dropna()


def calc_stats(returns: List[float]) -> Dict:
    """计算统计指标"""
    if not returns:
        return None
    
    returns = np.array(returns)
    total = (1 + returns).prod() - 1
    win_rate = (returns > 0).mean()
    
    if len(returns) > 1 and returns.std() > 0:
        sharpe = returns.mean() / returns.std() * np.sqrt(252 * 4)
    else:
        sharpe = 0
    
    return {
        'total_return': total,
        'sharpe': sharpe,
        'win_rate': win_rate,
        'trades': len(returns),
        'avg_return': returns.mean(),
        'std_return': returns.std()
    }


# ============ 策略1: K019 Simple ============
def strategy_k019_simple(symbol: str, df: pd.DataFrame) -> Dict:
    """K019: MA + OBV + 止损止盈"""
    df = prepare_features(df)
    
    position = 0
    entry_price = 0
    returns = []
    
    for i in range(50, len(df)):
        ma5, ma20 = df['ma5'].iloc[i], df['ma20'].iloc[i]
        obv, obv_ma = df['obv'].iloc[i], df['obv_ma5'].iloc[i]
        close = df['close'].iloc[i]
        
        if pd.isna(ma5) or pd.isna(obv_ma):
            continue
        
        # 买入信号
        if position == 0:
            if obv > obv_ma and ma5 > ma20:
                position = 1
                entry_price = close
        
        # 卖出
        elif position == 1:
            ret = (close - entry_price) / entry_price
            if ret < -0.03 or ret > 0.08:
                returns.append(ret)
                position = 0
    
    return calc_stats(returns)


# ============ 策略2: K019 Trend ============
def strategy_k019_trend(symbol: str, df: pd.DataFrame) -> Dict:
    """K019趋势版: MA金叉死叉"""
    df = prepare_features(df)
    
    position = 0
    entry_price = 0
    returns = []
    
    for i in range(60, len(df)):
        ma5, ma20 = df['ma5'].iloc[i], df['ma20'].iloc[i]
        prev_ma5, prev_ma20 = df['ma5'].iloc[i-1], df['ma20'].iloc[i-1]
        close = df['close'].iloc[i]
        
        if pd.isna(ma5):
            continue
        
        # 金叉买入
        if position == 0:
            if ma5 > ma20 and prev_ma5 <= prev_ma20:
                position = 1
                entry_price = close
        
        # 死叉卖出
        elif position == 1:
            if ma5 < ma20 and prev_ma5 >= prev_ma20:
                ret = (close - entry_price) / entry_price
                returns.append(ret)
                position = 0
    
    return calc_stats(returns)


# ============ 策略3: K019 Aggressive ============
def strategy_k019_aggressive(symbol: str, df: pd.DataFrame) -> Dict:
    """K019激进版: 更短周期MA"""
    df = prepare_features(df)
    
    position = 0
    entry_price = 0
    returns = []
    
    for i in range(20, len(df)):
        ma5, ma10 = df['ma5'].iloc[i], df['ma10'].iloc[i]
        obv, obv_ma = df['obv'].iloc[i], df['obv_ma10'].iloc[i]
        close = df['close'].iloc[i]
        
        if pd.isna(ma5) or pd.isna(obv_ma):
            continue
        
        if position == 0:
            if obv > obv_ma and ma5 > ma10:
                position = 1
                entry_price = close
        
        elif position == 1:
            ret = (close - entry_price) / entry_price
            if ret < -0.05 or ret > 0.12:
                returns.append(ret)
                position = 0
    
    return calc_stats(returns)


# ============ 策略4: Momentum ============
def strategy_momentum(symbol: str, df: pd.DataFrame) -> Dict:
    """动量策略: 追涨杀跌"""
    df = prepare_features(df)
    
    position = 0
    entry_price = 0
    returns = []
    
    for i in range(20, len(df)):
        close = df['close'].iloc[i]
        ma5 = df['ma5'].iloc[i]
        ret = df['return'].iloc[i]
        
        if pd.isna(ma5):
            continue
        
        # 买入: 价格在MA上方且动量为正
        if position == 0:
            if close > ma5 and ret > 0:
                position = 1
                entry_price = close
        
        # 卖出: 价格跌破MA或动量为负
        elif position == 1:
            if close < ma5 or ret < -0.01:
                ret = (close - entry_price) / entry_price
                returns.append(ret)
                position = 0
    
    return calc_stats(returns)


# ============ 策略5: Range Trading ============
def strategy_range(symbol: str, df: pd.DataFrame) -> Dict:
    """区间交易: 高抛低吸"""
    df = prepare_features(df)
    
    position = 0  # 0:空仓, 1:多, -1:空
    entry_price = 0
    returns = []
    
    for i in range(20, len(df)):
        close = df['close'].iloc[i]
        ma20 = df['ma20'].iloc[i]
        atr = df['atr'].iloc[i]
        
        if pd.isna(ma20) or pd.isna(atr) or atr == 0:
            continue
        
        # 计算波动区间
        upper = ma20 + 2 * atr
        lower = ma20 - 2 * atr
        
        # 买入
        if position == 0:
            if close < lower:
                position = 1
                entry_price = close
        
        # 卖出多头
        elif position == 1:
            ret = (close - entry_price) / entry_price
            if close > ma20 or ret > 0.03 or ret < -0.03:
                returns.append(ret)
                position = 0
    
    return calc_stats(returns)


# ============ 主程序 ============
def run_all_strategies():
    """运行所有策略对比"""
    print("=" * 80)
    print("📊 所有策略60分钟回测对比")
    print("=" * 80)
    
    strategies = {
        'K019 Simple': strategy_k019_simple,
        'K019 Trend': strategy_k019_trend,
        'K019 Aggressive': strategy_k019_aggressive,
        'Momentum': strategy_momentum,
        'Range Trading': strategy_range,
    }
    
    # 加载数据
    symbols = []
    for f in os.listdir(DATA_DIR):
        if f.endswith('_60.csv'):
            symbols.append(f.replace('_60.csv', ''))
    
    print(f"\n📂 加载 {len(symbols)} 个品种数据...")
    
    data = {}
    for sym in symbols:
        df = load_data(sym)
        if df is not None and len(df) > 100:
            data[sym] = df
    
    print(f"✅ 有效品种: {len(data)}")
    
    # 运行每个策略
    all_results = {}
    
    for name, func in strategies.items():
        print(f"\n{'='*60}")
        print(f"🚀 运行策略: {name}")
        print(f"{'='*60}")
        
        results = []
        for sym, df in data.items():
            try:
                result = func(sym, df)
                if result:
                    result['symbol'] = sym
                    results.append(result)
                    print(f"  {sym}: 夏普={result['sharpe']:.2f}, 收益={result['total_return']*100:.1f}%")
            except Exception as e:
                print(f"  ❌ {sym}: {e}")
        
        all_results[name] = results
        
        # 统计
        if results:
            positive = sum(1 for r in results if r['total_return'] > 0)
            positive_sharpe = sum(1 for r in results if r['sharpe'] > 0)
            avg_return = sum(r['total_return'] for r in results) / len(results)
            avg_sharpe = sum(r['sharpe'] for r in results) / len(results)
            
            print(f"\n📊 {name} 统计:")
            print(f"   正收益: {positive}/{len(results)}")
            print(f"   正夏普: {positive_sharpe}/{len(results)}")
            print(f"   平均收益: {avg_return*100:.1f}%")
            print(f"   平均夏普: {avg_sharpe:.3f}")
    
    # 生成对比报告
    print("\n" + "=" * 80)
    print("📈 策略对比总结")
    print("=" * 80)
    
    summary = []
    for name, results in all_results.items():
        if not results:
            continue
        
        positive = sum(1 for r in results if r['total_return'] > 0)
        positive_sharpe = sum(1 for r in results if r['sharpe'] > 0)
        avg_return = sum(r['total_return'] for r in results) / len(results)
        avg_sharpe = sum(r['sharpe'] for r in results) / len(results)
        
        summary.append({
            'strategy': name,
            'count': len(results),
            'positive': positive,
            'positive_rate': positive / len(results),
            'positive_sharpe': positive_sharpe,
            'avg_return': avg_return,
            'avg_sharpe': avg_sharpe,
            'best': max(results, key=lambda x: x['sharpe']) if results else None,
        })
    
    # 按夏普排序
    summary = sorted(summary, key=lambda x: x['avg_sharpe'], reverse=True)
    
    print(f"\n{'策略':<20} {'品种':<8} {'正收益':<10} {'正夏普':<10} {'平均收益':<12} {'平均夏普':<10}")
    print("-" * 80)
    
    for s in summary:
        print(f"{s['strategy']:<20} {s['count']:<8} {s['positive']}/{s['count']:<6} {s['positive_sharpe']}/{s['count']:<6} {s['avg_return']*100:>8.1f}%   {s['avg_sharpe']:>8.3f}")
    
    # 最佳策略
    best = summary[0] if summary else None
    if best:
        print(f"\n🏆 最佳策略: {best['strategy']}")
        print(f"   平均夏普: {best['avg_sharpe']:.3f}")
        print(f"   正夏普率: {best['positive_sharpe']}/{best['count']} ({best['positive_sharpe']/best['count']*100:.1f}%)")
        
        if best['best']:
            print(f"\n   最佳品种: {best['best']['symbol']}")
            print(f"   收益: {best['best']['total_return']*100:.1f}%")
            print(f"   夏普: {best['best']['sharpe']:.2f}")
    
    # 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = f"{RESULT_DIR}/all_strategies_comparison_{timestamp}.json"
    
    output = {
        'timestamp': timestamp,
        'data': all_results,
        'summary': summary
    }
    
    with open(result_file, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\n💾 结果已保存: {result_file}")
    
    return all_results


if __name__ == "__main__":
    run_all_strategies()
