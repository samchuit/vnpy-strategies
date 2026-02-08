#!/usr/bin/env python3
"""
60分钟K线真实回测
使用迅投下载的60分钟数据
"""

import numpy as np
import pandas as pd
import os
from datetime import datetime

DATA_DIR = "/Users/chusungang/workspace/vnpy_strategy/data_minute"
RESULT_DIR = "/Users/chusungang/workspace/vnpy_strategy/result"
os.makedirs(RESULT_DIR, exist_ok=True)


def prepare_data(df):
    """准备数据"""
    if df is None or len(df) < 100:
        return None
    
    df = df.copy()
    
    # 计算均线
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    
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
    df['obv_ma'] = df['obv'].rolling(5).mean()
    
    return df


def run_backtest(symbol, df, config):
    """运行回测"""
    df = prepare_data(df)
    if df is None or len(df) < 100:
        return None
    
    # 参数
    stop_loss = config.get('stop_loss', 0.03)
    take_profit = config.get('take_profit', 0.08)
    
    position = 0
    entry_price = 0
    trades = []
    returns = []
    
    for i in range(50, len(df)):
        ma5 = df['ma5'].iloc[i]
        ma20 = df['ma20'].iloc[i]
        obv = df['obv'].iloc[i]
        obv_ma = df['obv_ma'].iloc[i]
        close = df['close'].iloc[i]
        
        if pd.isna(ma5) or pd.isna(ma20) or pd.isna(obv_ma):
            continue
        
        # 买入信号
        if position == 0:
            if obv > obv_ma and ma5 > ma20:
                position = 1
                entry_price = close
        
        # 卖出信号
        elif position == 1:
            ret = (close - entry_price) / entry_price
            
            # 止损或止盈
            if ret < -stop_loss or ret > take_profit:
                trades.append({
                    'entry': entry_price,
                    'exit': close,
                    'return': ret,
                    'type': 'long'
                })
                returns.append(ret)
                position = 0
    
    if not trades:
        return None
    
    returns = np.array(returns)
    total_ret = (1 + returns).prod() - 1
    
    # 计算夏普 (年化)
    if len(returns) > 1:
        sharpe = returns.mean() / returns.std() * np.sqrt(252 * 4)  # 60分钟线每年约1000根
    else:
        sharpe = 0
    
    win_rate = (returns > 0).mean()
    
    return {
        'symbol': symbol,
        'total_return': total_ret,
        'sharpe': sharpe,
        'win_rate': win_rate,
        'trades': len(trades),
        'data_points': len(df)
    }


def main():
    """主程序"""
    print("=" * 60)
    print("📊 60分钟K线真实回测")
    print("=" * 60)
    print(f"数据目录: {DATA_DIR}")
    
    # 默认配置
    config = {
        'stop_loss': 0.03,
        'take_profit': 0.08
    }
    
    # 加载60分钟数据
    results = []
    count = 0
    
    for f in os.listdir(DATA_DIR):
        if f.endswith('_60.csv'):
            symbol = f.replace('_60.csv', '')
            file_path = os.path.join(DATA_DIR, f)
            
            try:
                df = pd.read_csv(file_path)
                result = run_backtest(symbol, df, config)
                
                if result:
                    results.append(result)
                    count += 1
                    
                    if count <= 10:  # 只打印前10个
                        print(f"{symbol}: 夏普={result['sharpe']:.2f}, 收益={result['total_return']*100:.1f}%, 交易={result['trades']}")
            except Exception as e:
                print(f"❌ {symbol}: {e}")
    
    if count > 10:
        print(f"... 共 {count} 个品种")
    
    # 统计
    positive = [r for r in results if r['total_return'] > 0]
    positive_sharpe = [r for r in results if r['sharpe'] > 0]
    
    print(f"\n{'='*60}")
    print("📊 回测统计")
    print(f"{'='*60}")
    print(f"总品种: {len(results)}")
    print(f"正收益: {len(positive)}/{len(results)} ({len(positive)/len(results)*100:.1f}%)")
    print(f"正夏普: {len(positive_sharpe)}/{len(results)} ({len(positive_sharpe)/len(results)*100:.1f}%)")
    
    if results:
        avg_return = sum(r['total_return'] for r in results) / len(results)
        valid_sharpe = [r['sharpe'] for r in results if -5 < r['sharpe'] < 50]
        avg_sharpe = sum(valid_sharpe) / len(valid_sharpe) if valid_sharpe else 0
        print(f"平均收益: {avg_return*100:.1f}%")
        print(f"平均夏普(有效): {avg_sharpe:.3f}")
    
    # Top 5 (排除异常值)
    valid_results = [r for r in results if -10 < r['sharpe'] < 100]
    top5 = sorted(valid_results, key=lambda x: x['sharpe'], reverse=True)[:5]
    print(f"\n🏆 Top 5 品种:")
    for i, r in enumerate(top5, 1):
        print(f"  {i}. {r['symbol']}: 夏普={r['sharpe']:.2f}, 收益={r['total_return']*100:.1f}%")
    
    # 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = f"{RESULT_DIR}/minute60_backtest_{timestamp}.json"
    
    with open(result_file, 'w') as f:
        import json
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 结果已保存: {result_file}")
    
    return results


if __name__ == "__main__":
    main()
