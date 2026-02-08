#!/usr/bin/env python3
"""
Range Trading 策略 - SimNow模拟实盘
基于ATR和MA20的区间突破策略
"""

import sys
import os
import time
import json
from datetime import datetime
from typing import Dict, List
import pandas as pd
import numpy as np

# ===============================
# SimNow CTP配置
# ===============================
CTP_CONFIG = {
    "用户名": "17274709735",
    "密码": "131421Cimmy!",
    "经纪商代码": "9999",
    "交易服务器": "180.168.146.187:10101",
    "行情服务器": "180.168.146.187:10111",
    "产品名称": "simnow_client",
    "授权码": "255103",
}

# ===============================
# 策略配置
# ===============================
STRATEGY_CONFIG = {
    # 策略参数
    "lookback_ma": 20,
    "atr_period": 14,
    "atr_multiplier": 2.0,
    "stop_loss": 0.03,
    "take_profit": 0.03,
    
    # 交易品种 (使用通用名称，与数据文件名对应)
    "symbols": [
        "CU",   # 沪铜
        "HC",   # 热卷
        "ZN",   # 沪锌
        "WR",   # 线材
        "J",    # 焦炭
        "AL",   # 沪铝
        "AU",   # 黄金
        "AG",   # 白银
        "RU",   # 橡胶
        "FU",   # 燃油
        "RB",   # 螺纹
        "JM",   # 焦煤
        "BU",   # 沥青
        "I",    # 铁矿石
        "M",    # 豆粕
        "Y",    # 豆油
        "C",    # 玉米
    ],
    
    # 仓位配置
    "positions": {
        "CU": 0.25,
        "HC": 0.20,
        "ZN": 0.15,
        "WR": 0.15,
        "J": 0.15,
        "AL": 0.10,
        "AU": 0.05,
        "AG": 0.05,
        "RU": 0.05,
        "FU": 0.05,
        "RB": 0.10,
        "JM": 0.10,
        "BU": 0.05,
    },
    
    # 风控
    "max_positions": 5,        # 最多同时持仓
    "max_loss_per_trade": 0.02,  # 单笔最大亏损
    "daily_loss_limit": 0.05,     # 日亏损限额
}

class RangeTradingSimulator:
    """Range Trading模拟器 (用于测试策略逻辑)"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.positions = {}  # 当前持仓
        self.entry_prices = {}  # 开仓价格
        self.trades = []  # 交易记录
        self.daily_pnl = {}  # 每日盈亏
        
    def calculate_indicators(self, data) -> Dict:
        """计算技术指标"""
        # 支持DataFrame或list
        if hasattr(data, 'close'):
            closes = data['close'].values
            highs = data['high'].values
            lows = data['low'].values
        else:
            closes = [d['close'] for d in data]
            highs = [d['high'] for d in data]
            lows = [d['low'] for d in data]
        
        n = self.config['lookback_ma']
        atr_n = self.config['atr_period']
        
        # MA20
        ma20 = sum(closes[-n:]) / n if len(closes) >= n else closes[-1]
        
        # ATR
        tr_list = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_list.append(tr)
        atr = sum(tr_list[-atr_n:]) / atr_n if len(tr_list) >= atr_n else (tr_list[-1] if tr_list else 0)
        
        return {
            'ma20': ma20,
            'atr': atr,
            'close': closes[-1],
            'high': highs[-1],
            'low': lows[-1],
        }
    
    def generate_signal(self, symbol: str, data) -> str:
        """生成交易信号"""
        if len(data) < 25:
            return "HOLD"
        
        ind = self.calculate_indicators(data)
        
        upper = ind['ma20'] + self.config['atr_multiplier'] * ind['atr']
        lower = ind['ma20'] - self.config['atr_multiplier'] * ind['atr']
        
        current_price = ind['close']
        
        # 买入信号: 价格跌破下轨
        if current_price < lower:
            return "LONG"
        
        # 卖出信号: 价格涨回MA20 或 达到止盈止损
        if symbol in self.positions and self.positions[symbol] > 0:
            entry_price = self.entry_prices[symbol]
            ret = (current_price - entry_price) / entry_price
            
            if current_price > ind['ma20'] or ret > self.config['take_profit'] or ret < -self.config['stop_loss']:
                return "CLOSE"
        
        return "HOLD"
    
    def run_backtest(self, data: Dict[str, pd.DataFrame]) -> Dict:
        """运行回测"""
        print("\n" + "=" * 60)
        print("📊 Range Trading 回测 (SimNow配置)")
        print("=" * 60)
        
        results = []
        
        for symbol, df in data.items():
            if symbol not in self.config['symbols']:
                continue
            
            print(f"\n{symbol} 回测...")
            
            self.positions[symbol] = 0
            self.entry_prices[symbol] = 0
            returns = []
            
            for i in range(25, len(df)):
                window = df.iloc[:i+1]  # DataFrame切片
                signal = self.generate_signal(symbol, window)
                
                current_price = df['close'].iloc[i]
                
                if signal == "LONG" and self.positions.get(symbol, 0) == 0:
                    self.positions[symbol] = 1
                    self.entry_prices[symbol] = current_price
                    self.trades.append({
                        'symbol': symbol,
                        'type': 'BUY',
                        'price': current_price,
                        'time': str(df['date'].iloc[i]) if 'date' in df.columns else f'tick_{i}'
                    })
                
                elif signal == "CLOSE" and self.positions.get(symbol, 0) > 0:
                    entry = self.entry_prices[symbol]
                    ret = (current_price - entry) / entry
                    returns.append(ret)
                    self.trades.append({
                        'symbol': symbol,
                        'type': 'SELL',
                        'price': current_price,
                        'return': ret,
                        'time': str(df['date'].iloc[i]) if 'date' in df.columns else f'tick_{i}'
                    })
                    self.positions[symbol] = 0
            
            if returns:
                total_ret = (1 + sum([(1+r) for r in returns])) - 1
                import numpy as np
                sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252 * 4) if np.std(returns) > 0 else 0
                win_rate = sum(1 for r in returns if r > 0) / len(returns)
                
                results.append({
                    'symbol': symbol,
                    'total_return': total_ret,
                    'sharpe': sharpe,
                    'win_rate': win_rate,
                    'trades': len(returns)
                })
                print(f"   交易{len(returns)}次, 收益{total_ret*100:.1f}%, 夏普{sharpe:.2f}")
        
        # 统计
        positive = sum(1 for r in results if r['total_return'] > 0)
        positive_sharpe = sum(1 for r in results if r['sharpe'] > 0)
        
        print(f"\n{'='*60}")
        print("📊 回测结果")
        print(f"{'='*60}")
        print(f"测试品种: {len(results)}")
        print(f"正收益: {positive}/{len(results)}")
        print(f"正夏普: {positive_sharpe}/{len(results)}")
        
        avg_return = sum(r['total_return'] for r in results) / len(results) if results else 0
        avg_sharpe = sum(r['sharpe'] for r in results) / len(results) if results else 0
        
        print(f"平均收益: {avg_return*100:.1f}%")
        print(f"平均夏普: {avg_sharpe:.3f}")
        
        # 保存结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = f"result/range_trading_simnow_{timestamp}.json"
        os.makedirs("result", exist_ok=True)
        
        with open(result_file, 'w') as f:
            json.dump({
                'config': self.config,
                'results': results,
                'summary': {
                    'total': len(results),
                    'positive': positive,
                    'positive_sharpe': positive_sharpe,
                    'avg_return': avg_return,
                    'avg_sharpe': avg_sharpe
                }
            }, f, indent=2, default=str)
        
        print(f"\n💾 结果已保存: {result_file}")
        
        return results


def main():
    """主程序"""
    print("=" * 60)
    print("🚀 Range Trading SimNow 模拟实盘")
    print("=" * 60)
    print(f"\n📡 SimNow配置:")
    for key, value in CTP_CONFIG.items():
        if key != "密码":
            print(f"   {key}: {value}")
    
    print(f"\n📋 策略配置:")
    print(f"   MA周期: {STRATEGY_CONFIG['lookback_ma']}")
    print(f"   ATR周期: {STRATEGY_CONFIG['atr_period']}")
    print(f"   ATR倍数: {STRATEGY_CONFIG['atr_multiplier']}")
    print(f"   止损: {STRATEGY_CONFIG['stop_loss']*100}%")
    print(f"   止盈: {STRATEGY_CONFIG['take_profit']*100}%")
    
    # 检查是否有60分钟数据
    data_dir = "/Users/chusungang/workspace/vnpy_strategy/data_minute"
    if os.path.exists(data_dir):
        print(f"\n📂 发现60分钟数据，使用现有数据回测...")
        
        # 品种映射: 文件名 -> 策略名
        symbol_map = {
            'AL': 'AL',
            'CU': 'CU',
            'ZN': 'ZN',
            'WR': 'WR',
            'J': 'J',
            'AU': 'AU',
            'AG': 'AG',
            'RU': 'RU',
            'FU': 'FU',
            'HC': 'HC',
            'RB': 'RB',
            'JM': 'JM',
            'BU': 'BU',
            'I': 'I',
            'M': 'M',
            'Y': 'Y',
            'C': 'C',
            'CF': 'CF',
            'SR': 'SR',
            'MA': 'MA',
        }
        
        data = {}
        for f in os.listdir(data_dir):
            if f.endswith('_60.csv'):
                filename = f.replace('_60.csv', '')
                if filename in symbol_map:
                    symbol = symbol_map[filename]
                    import pandas as pd
                    df = pd.read_csv(f"{data_dir}/{f}")
                    data[symbol] = df  # 保存DataFrame
                    print(f"   加载: {symbol} ({len(df)} 条)")
        
        if data:
            simulator = RangeTradingSimulator(STRATEGY_CONFIG)
            results = simulator.run_backtest(data)
        else:
            print("\n❌ 未找到匹配的数据")
    else:
        print("\n⚠️ 未找到60分钟数据")
        print("请先配置SimNow实盘连接...")
    
    print("\n" + "=" * 60)
    print("📝 下一步")
    print("=" * 60)
    print("""
1. 在SimNow创建模拟账户:
   https://www.simnow.com.cn/

2. 安装vnpy实盘环境:
   pip install vnpy[ctp]

3. 连接实盘:
   python run_simnow.py

4. 启用自动交易:
   在MainEngine中启用Range Trading策略
""")


if __name__ == "__main__":
    main()
