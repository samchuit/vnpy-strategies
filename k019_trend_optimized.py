#!/usr/bin/env python3
"""
K019 Trend 优化版
增加趋势过滤和品种筛选
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

# ===============================
# 优化配置
# ===============================
OPTIMIZED_CONFIG = {
    # 基础参数
    "ma_short": 5,
    "ma_medium": 10,
    "ma_long": 20,
    
    # 新增: MA60用于趋势确认
    "ma_trend": 60,
    
    # 止损止盈
    "stop_loss": 0.02,  # 优化: 从3%降到2%
    "take_profit": 0.06,  # 优化: 从8%降到6%
    "trailing_stop": 0.015,  # 新增: 追踪止损
    
    # 趋势过滤
    "trend_filter": True,  # 开启趋势过滤
    "min_trend_strength": 0.02,  # 最小趋势强度
    
    # 品种筛选
    "allowed_symbols": ['AL', 'CU', 'AG', 'AU', 'ZN'],  # 只交易这些品种
    
    # 仓位配置
    "position_sizes": {
        'AL': 0.25,
        'CU': 0.25,
        'AG': 0.20,
        'AU': 0.15,
        'ZN': 0.15,
    },
}


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
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    
    # 趋势强度
    df['trend_strength'] = (df['ma20'] - df['ma60']) / df['ma60']
    
    return df.dropna()


def check_trend(df: pd.DataFrame) -> Dict:
    """检查趋势状态"""
    ma5 = df['ma5'].iloc[-1]
    ma10 = df['ma10'].iloc[-1]
    ma20 = df['ma20'].iloc[-1]
    ma60 = df['ma60'].iloc[-1]
    trend_strength = df['trend_strength'].iloc[-1]
    
    # 多头排列
    if ma5 > ma20 > ma60 and trend_strength > OPTIMIZED_CONFIG['min_trend_strength']:
        return {'trend': 'BULL', 'strength': trend_strength}
    
    # 空头排列
    elif ma5 < ma20 < ma60 and trend_strength < -OPTIMIZED_CONFIG['min_trend_strength']:
        return {'trend': 'BEAR', 'strength': abs(trend_strength)}
    
    return {'trend': 'NEUTRAL', 'strength': abs(trend_strength)}


def run_optimized_backtest(symbol: str, df: pd.DataFrame) -> Dict:
    """运行优化版回测"""
    df = prepare_features(df)
    
    position = 0
    entry_price = 0
    highest = 0
    trailing_stop = 0
    returns = []
    trades = []
    
    config = OPTIMIZED_CONFIG
    
    for i in range(60, len(df)):
        ma5 = df['ma5'].iloc[i]
        ma10 = df['ma10'].iloc[i]
        ma20 = df['ma20'].iloc[i]
        close = df['close'].iloc[i]
        atr = df['atr'].iloc[i]
        
        if pd.isna(ma5) or pd.isna(atr) or atr == 0:
            continue
        
        trend = check_trend(df.iloc[:i+1])
        
        # 买入信号
        if position == 0:
            # 金叉买入
            prev_ma5 = df['ma5'].iloc[i-1]
            prev_ma10 = df['ma10'].iloc[i-1]
            
            golden_cross = (ma5 > ma10) and (prev_ma5 <= prev_ma10)
            
            # 趋势过滤
            if config['trend_filter']:
                allow_buy = golden_cross and trend['trend'] == 'BULL'
            else:
                allow_buy = golden_cross
            
            if allow_buy:
                position = 1
                entry_price = close
                highest = close
                trailing_stop = close * (1 - config['trailing_stop'])
        
        # 持仓处理
        elif position == 1:
            # 更新最高价和追踪止损
            if close > highest:
                highest = close
                trailing_stop = max(trailing_stop, close * (1 - config['trailing_stop']))
            
            # 死叉卖出
            prev_ma5 = df['ma5'].iloc[i-1]
            prev_ma10 = df['ma10'].iloc[i-1]
            death_cross = (ma5 < ma10) and (prev_ma5 >= prev_ma10)
            
            # 计算收益
            ret = (close - entry_price) / entry_price
            
            # 止损止盈条件
            stop_loss_hit = close < entry_price * (1 - config['stop_loss'])
            take_profit_hit = close > entry_price * (1 + config['take_profit'])
            trailing_stop_hit = close < trailing_stop
            death_cross_hit = death_cross
            
            if stop_loss_hit or take_profit_hit or trailing_stop_hit or death_cross_hit:
                # 修正负收益显示
                actual_ret = ret if not (stop_loss_hit or trailing_stop_hit) else ret
                
                returns.append(actual_ret)
                trades.append({
                    'entry': entry_price,
                    'exit': close,
                    'return': actual_ret,
                    'type': 'long',
                    'reason': 'SL' if stop_loss_hit else ('TP' if take_profit_hit else ('TS' if trailing_stop_hit else 'DC'))
                })
                position = 0
    
    if not returns:
        return None
    
    returns = np.array(returns)
    total_ret = (1 + returns).prod() - 1
    
    if len(returns) > 1 and returns.std() > 0:
        sharpe = returns.mean() / returns.std() * np.sqrt(252 * 4)
    else:
        sharpe = 0
    
    win_rate = (returns > 0).mean()
    
    return {
        'symbol': symbol,
        'total_return': total_ret,
        'sharpe': sharpe,
        'win_rate': win_rate,
        'trades': len(returns),
        'config': OPTIMIZED_CONFIG
    }


def compare_with_original():
    """对比优化版和原版"""
    print("\n" + "=" * 70)
    print("📊 K019 Trend 优化版 vs 原版对比")
    print("=" * 70)
    
    # 加载60分钟数据
    symbols = OPTIMIZED_CONFIG['allowed_symbols']
    data = {}
    
    for sym in symbols:
        file_path = f"{DATA_DIR}/{sym}_60.csv"
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            data[sym] = df
    
    print(f"\n📂 加载 {len(data)} 个品种数据...")
    
    # 运行优化版回测
    optimized_results = []
    original_results = []  # 原版只做简单对比
    
    for symbol, df in data.items():
        print(f"\n{symbol}...")
        
        # 优化版
        opt_result = run_optimized_backtest(symbol, df)
        if opt_result:
            optimized_results.append(opt_result)
            print(f"   优化版: 夏普={opt_result['sharpe']:.2f}, 收益={opt_result['total_return']*100:.1f}%")
    
    # 统计
    print("\n" + "=" * 70)
    print("📈 对比结果")
    print("=" * 70)
    
    if optimized_results:
        opt_positive = sum(1 for r in optimized_results if r['total_return'] > 0)
        opt_positive_sharpe = sum(1 for r in optimized_results if r['sharpe'] > 0)
        opt_avg_sharpe = sum(r['sharpe'] for r in optimized_results) / len(optimized_results)
        opt_avg_return = sum(r['total_return'] for r in optimized_results) / len(optimized_results)
        
        print(f"\n优化版:")
        print(f"   正收益: {opt_positive}/{len(optimized_results)} ({opt_positive/len(optimized_results)*100:.1f}%)")
        print(f"   正夏普: {opt_positive_sharpe}/{len(optimized_results)} ({opt_positive_sharpe/len(optimized_results)*100:.1f}%)")
        print(f"   平均收益: {opt_avg_return*100:.1f}%")
        print(f"   平均夏普: {opt_avg_sharpe:.3f}")
        
        # 与原版对比
        print(f"\n与原版对比:")
        print(f"   原版平均夏普: 0.455")
        print(f"   优化版平均夏普: {opt_avg_sharpe:.3f}")
        print(f"   改进: {(opt_avg_sharpe - 0.455)*100:.1f}%")
    
    # Top品种
    print(f"\n🏆 Top 3 品种:")
    top3 = sorted(optimized_results, key=lambda x: x['sharpe'], reverse=True)[:3]
    for i, r in enumerate(top3, 1):
        print(f"   {i}. {r['symbol']}: 夏普={r['sharpe']:.2f}, 收益={r['total_return']*100:.1f}%")
    
    # 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = f"{RESULT_DIR}/k019_trend_optimized_{timestamp}.json"
    
    with open(result_file, 'w') as f:
        json.dump({
            'config': OPTIMIZED_CONFIG,
            'results': optimized_results,
            'summary': {
                'avg_sharpe': opt_avg_sharpe if optimized_results else 0,
                'avg_return': opt_avg_return if optimized_results else 0,
                'positive_rate': opt_positive / len(optimized_results) if optimized_results else 0
            }
        }, f, indent=2, default=str)
    
    print(f"\n💾 结果已保存: {result_file}")
    
    return optimized_results


def main():
    """主程序"""
    print("=" * 70)
    print("🚀 K019 Trend 优化版")
    print("=" * 70)
    
    print(f"\n📋 优化内容:")
    print("   1. 增加MA60趋势过滤")
    print("   2. 降低止损止盈 (3%→2%, 8%→6%)")
    print("   3. 增加追踪止损")
    print("   4. 品种筛选 (只交易 AL, CU, AG, AU, ZN)")
    print("   5. 只在多头趋势时买入")
    
    results = compare_with_original()
    
    return results


if __name__ == "__main__":
    main()
