#!/usr/bin/env python3
"""
K019策略: OBV能量 + 多均线 + 动态止损止盈

策略逻辑:
1. OBV (能量潮) - 判断资金流向
2. 多均线 (5/20/60) - 确认趋势方向
3. 动态止损止盈 - 保护收益
"""

import sys, os, json
import numpy as np
import pandas as pd
from datetime import datetime

# 配置
DATA_DIR = "/Users/chusungang/workspace/vnpy_strategy/data"
RESULT_DIR = "/Users/chusungang/workspace/vnpy_strategy/result"
os.makedirs(RESULT_DIR, exist_ok=True)


def prepare_data(df):
    """准备数据"""
    if df is None or len(df) < 100:
        return df
    
    df = df.copy()
    df['ma5'] = df['close'].rolling(5).mean()
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
    df['obv_ma'] = df['obv'].rolling(10).mean()
    
    return df


def get_trend(df):
    """获取趋势"""
    ma5 = df['ma5'].iloc[-1]
    ma20 = df['ma20'].iloc[-1]
    ma60 = df['ma60'].iloc[-1]
    
    if pd.isna(ma5) or pd.isna(ma20) or pd.isna(ma60):
        return 'mixed'
    
    if ma5 > ma20 > ma60:
        return 'up'
    elif ma5 < ma20 < ma60:
        return 'down'
    return 'mixed'


def get_obv_signal(df):
    """OBV信号"""
    obv = df['obv'].iloc
    obv_ma = df['obv_ma'].iloc
    
    # 金叉
    if obv[-1] > obv_ma[-1] and obv[-2] < obv_ma[-2]:
        return 1
    # 死叉
    if obv[-1] < obv_ma[-1] and obv[-2] > obv_ma[-2]:
        return -1
    return 0


def run_backtest(symbol, df, config):
    """运行回测"""
    df = prepare_data(df)
    
    if df is None or len(df) < 100:
        return None
    
    # 参数
    stop_loss = config.get('stop_loss', 0.05)
    take_profit = config.get('take_profit', 0.10)
    trailing_stop = config.get('trailing_stop', 0.03)
    
    position = 0
    entry_price = 0
    highest = 0
    lowest = float('inf')
    
    trades = []
    signals = []
    returns = []
    
    for i in range(70, len(df)):
        current_price = df['close'].iloc[i]
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]
        
        # 更新高低价
        if position == 1:
            highest = max(highest, current_high)
        elif position == -1:
            lowest = min(lowest, current_low)
        
        # 止损止盈
        if position != 0:
            closed = False
            
            if position == 1:
                if current_price < entry_price * (1 - stop_loss):
                    closed = True; reason = 'stop'
                elif current_price > entry_price * (1 + take_profit):
                    closed = True; reason = 'profit'
                elif highest > entry_price:
                    if current_price < highest * (1 - trailing_stop):
                        closed = True; reason = 'trailing'
            
            else:
                if current_price > entry_price * (1 + stop_loss):
                    closed = True; reason = 'stop'
                elif current_price < entry_price * (1 - take_profit):
                    closed = True; reason = 'profit'
                elif lowest < entry_price:
                    if current_price > lowest * (1 + trailing_stop):
                        closed = True; reason = 'trailing'
            
            if closed:
                ret = (current_price - entry_price) / entry_price if position == 1 else (entry_price - current_price) / entry_price
                trades.append({'type': 'long' if position == 1 else 'short', 'return': ret, 'reason': reason})
                returns.append(ret)
                position = 0
        
        # 信号
        if position == 0:
            trend = get_trend(df.iloc[:i+1])
            obv_sig = get_obv_signal(df.iloc[:i+1])
            
            if trend == 'up' and obv_sig == 1:
                position = 1
                entry_price = current_price
                highest = current_high
                signals.append({'type': 'buy', 'price': current_price})
            elif trend == 'down' and obv_sig == -1:
                position = -1
                entry_price = current_price
                lowest = current_low
                signals.append({'type': 'sell', 'price': current_price})
    
    if not returns:
        return None
    
    returns = np.array(returns)
    total = (1 + returns).prod() - 1
    years = len(df) / 252
    annual = (1 + total) ** (1/years) - 1 if years > 0 and total > -1 else 0
    vol = returns.std() * np.sqrt(252) if len(returns) > 1 else 0
    sharpe = (annual - 0.02) / vol if vol > 0 else 0
    win = (returns > 0).mean()
    
    cum = np.cumprod(1 + returns)
    dd = np.min((cum - np.maximum.accumulate(cum)) / np.maximum.accumulate(cum))
    
    return {
        'symbol': symbol,
        'total_return': total,
        'annual_return': annual,
        'sharpe_ratio': sharpe,
        'win_rate': win,
        'max_drawdown': dd,
        'trades': len(returns)
    }


def load_data():
    """加载数据"""
    data = {}
    for f in os.listdir(DATA_DIR):
        if f.endswith('.csv'):
            symbol = f.replace('.csv', '')
            try:
                df = pd.read_csv(f"{DATA_DIR}/{f}")
                if 'date' not in df.columns:
                    df['date'] = df['trade_date'].astype(str)
                df = df.drop_duplicates('date').sort_values('date')
                data[symbol] = df
            except:
                pass
    return data


def main():
    print("="*60)
    print("K019策略: OBV + 多均线 + 动态止损止盈")
    print("="*60)
    
    data = load_data()
    print(f"\n✅ 加载 {len(data)} 个品种")
    
    if not data:
        print("❌ 无数据")
        return
    
    # 策略参数
    config = {
        'stop_loss': 0.05,
        'take_profit': 0.10,
        'trailing_stop': 0.03
    }
    
    results = []
    
    for symbol, df in data.items():
        print(f"\n{symbol}...", end=" ")
        r = run_backtest(symbol, df, config)
        if r:
            results.append(r)
            print(f"夏普={r['sharpe_ratio']:.2f}, 收益={r['total_return']:.2%}")
    
    if results:
        results.sort(key=lambda x: x['sharpe_ratio'], reverse=True)
        
        print("\n" + "="*60)
        print("📊 回测结果")
        print("="*60)
        print(f"{'品种':<10} {'总收益':>10} {'年化':>10} {'夏普':>8} {'胜率':>8} {'交易':>6}")
        print("-"*60)
        
        for r in results:
            print(f"{r['symbol']:<10} {r['total_return']:>9.2%} "
                  f"{r['annual_return']:>9.2%} {r['sharpe_ratio']:>8.2f} "
                  f"{r['win_rate']:>7.2%} {r['trades']:>6}")
        
        # 统计
        positive = sum(1 for r in results if r['total_return'] > 0)
        sharpe_positive = sum(1 for r in results if r['sharpe_ratio'] > 0)
        
        print("\n" + "="*60)
        print("📈 综合统计")
        print("="*60)
        print(f"   正收益品种: {positive}/{len(results)}")
        print(f"   夏普>0品种: {sharpe_positive}/{len(results)}")
        
        # 保存
        result_file = f"{RESULT_DIR}/k019_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(result_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n💾 结果已保存: {result_file}")


if __name__ == "__main__":
    main()
