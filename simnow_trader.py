#!/usr/bin/env python3
"""
Range Trading SimNow 模拟实盘
- 连接SimNow实时行情
- 自动执行交易策略
- 每日收盘生成报告
"""

import sys
import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List
from collections import defaultdict

# 添加项目路径
sys.path.insert(0, '/Users/chusungang/workspace/vnpy-strategies')

# SimNow CTP 配置
SIMNOW_CONFIG = {
    "用户名": "17274709735",
    "密码": "a12345678",
    "经纪商代码": "9999",
    "交易服务器": "180.168.146.187:10101",
    "行情服务器": "180.168.146.187:10111",
    "产品名称": "simnow_client",
    "授权码": "255103",
}

# Range Trading 策略配置
STRATEGY_CONFIG = {
    "ma_period": 20,
    "atr_period": 14,
    "atr_multiplier": 2.0,
    "stop_loss": 0.03,
    "take_profit": 0.03,
}

# 交易品种
SYMBOLS = [
    {"symbol": "CU", "name": "沪铜", "weight": 0.25},
    {"symbol": "HC", "name": "热卷", "weight": 0.20},
    {"symbol": "ZN", "name": "沪锌", "weight": 0.15},
    {"symbol": "J", "name": "焦炭", "weight": 0.15},
    {"symbol": "WR", "name": "线材", "weight": 0.10},
    {"symbol": "AL", "name": "沪铝", "weight": 0.10},
    {"symbol": "AU", "name": "黄金", "weight": 0.05},
]

class SimNowTrader:
    """SimNow模拟交易"""
    
    def __init__(self):
        self.positions = {}  # 持仓
        self.entry_prices = {}  # 开仓价
        self.trades = []  # 交易记录
        self.daily_pnl = defaultdict(float)  # 每日盈亏
        self.last_prices = {}  # 最新价格
        self.running = False
        
    def load_historical_data(self):
        """加载历史数据用于初始化"""
        import pandas as pd
        data_path = "/Users/chusungang/workspace/vnpy_strategy/data_minute/"
        data = {}
        
        for s in SYMBOLS:
            symbol = s["symbol"]
            # 查找历史数据文件 (格式: CU_60.csv)
            possible_files = [
                f"{data_path}{symbol}_60.csv",
                f"{data_path}{symbol}_60min.csv",
                f"{data_path}{symbol}.csv",
            ]
            
            for f in possible_files:
                if os.path.exists(f):
                    try:
                        df = pd.read_csv(f)
                        # 标准化列名
                        if 'close' in df.columns or 'Close' in df.columns:
                            df.columns = [c.lower() for c in df.columns]
                            data[symbol] = df
                            print(f"✅ 加载 {symbol}: {len(df)} 条")
                            break
                    except Exception as e:
                        print(f"⚠️ 加载 {symbol} 失败: {e}")
        
        return data
    
    def calculate_indicators(self, df):
        """计算技术指标"""
        close = df['close'].iloc[-1] if 'close' in df.columns else df.iloc[-1]['close']
        high = df['high'].iloc[-1] if 'high' in df.columns else close
        low = df['low'].iloc[-1] if 'low' in df.columns else close
        volume = df['volume'].iloc[-1] if 'volume' in df.columns else 0
        
        # MA
        ma20 = df['close'].rolling(20).mean().iloc[-1] if len(df) >= 20 else close
        
        # ATR
        atr = df['close'].rolling(14).std().iloc[-1] if len(df) >= 14 else close * 0.02
        
        return {
            'close': close,
            'ma20': ma20,
            'atr': atr,
            'high': high,
            'low': low,
            'volume': volume
        }
    
    def generate_signal(self, symbol, indicators):
        """生成交易信号"""
        close = indicators['close']
        ma20 = indicators['ma20']
        atr = indicators['atr']
        
        if symbol in self.positions and self.positions[symbol] > 0:
            # 持有多头，检查是否需要平仓
            if close > ma20 + atr:  # 突破上沿
                return "CLOSE"
        
        # 开仓信号
        if close < ma20 - atr:  # 突破下沿
            return "LONG"
        
        return "HOLD"
    
    def on_tick(self, symbol, price, timestamp=None):
        """行情回调"""
        self.last_prices[symbol] = price
        
        if symbol not in self.positions:
            self.positions[symbol] = 0
            self.entry_prices[symbol] = 0
        
        # 计算当前盈亏
        if self.positions[symbol] > 0 and self.entry_prices[symbol] > 0:
            pnl = (price - self.entry_prices[symbol]) / self.entry_prices[symbol]
            self.daily_pnl[symbol] = pnl
    
    def on_bar(self, symbol, df):
        """K线回调（每分钟）"""
        if len(df) < 20:
            return
        
        indicators = self.calculate_indicators(df)
        signal = self.generate_signal(symbol, indicators)
        
        price = indicators['close']
        
        # 执行交易
        if signal == "LONG" and self.positions.get(symbol, 0) == 0:
            self.positions[symbol] = 1
            self.entry_prices[symbol] = price
            self.trades.append({
                'symbol': symbol,
                'type': 'BUY',
                'price': price,
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'status': 'OPENED'
            })
            print(f"🟢 {symbol} 开多仓 @ {price:.2f}")
        
        elif signal == "CLOSE" and self.positions.get(symbol, 0) > 0:
            entry = self.entry_prices[symbol]
            pnl = (price - entry) / entry
            self.trades.append({
                'symbol': symbol,
                'type': 'SELL',
                'price': price,
                'pnl': pnl,
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'status': 'CLOSED'
            })
            self.positions[symbol] = 0
            self.entry_prices[symbol] = 0
            print(f"🔴 {symbol} 平多仓 @ {price:.2f}, 盈亏: {pnl*100:.2f}%")
    
    def get_position_info(self):
        """获取持仓信息"""
        info = []
        total_pnl = 0
        
        for s in SYMBOLS:
            symbol = s["symbol"]
            pos = self.positions.get(symbol, 0)
            
            if pos > 0:
                entry = self.entry_prices[symbol]
                current = self.last_prices.get(symbol, entry)
                pnl = (current - entry) / entry
                weight = s["weight"]
                total_pnl += pnl * weight
                
                info.append({
                    'symbol': symbol,
                    'name': s["name"],
                    'position': pos,
                    'entry_price': entry,
                    'current_price': current,
                    'pnl': pnl * 100,
                    'weight': weight * 100
                })
        
        return info, total_pnl * 100
    
    def generate_daily_report(self):
        """生成每日报告"""
        positions, total_pnl = self.get_position_info()
        
        report = {
            "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "positions": positions,
            "total_pnl": total_pnl,
            "trade_count": len(self.trades),
            "closed_pnl": sum([t.get('pnl', 0) for t in self.trades if t.get('status') == 'CLOSED']),
            "open_trades": [t for t in self.trades if t.get('status') == 'OPENED'],
            "closed_trades": [t for t in self.trades if t.get('status') == 'CLOSED']
        }
        
        return report
    
    def save_daily_report(self):
        """保存每日报告"""
        report = self.generate_daily_report()
        
        # 保存为JSON
        report_path = "/Users/chusungang/workspace/vnpy-strategies/result/simnow_daily"
        os.makedirs(report_path, exist_ok=True)
        
        date_str = datetime.now().strftime("%Y%m%d")
        json_path = f"{report_path}/report_{date_str}.json"
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        # 生成Markdown报告
        md_path = f"{report_path}/report_{date_str}.md"
        
        md_content = f"""# Range Trading SimNow 每日报告

**生成时间**: {report['report_time']}

## 📊 总体情况

| 指标 | 数值 |
|------|------|
| 总账户盈亏 | {report['total_pnl']:.2f}% |
| 交易次数 | {report['trade_count']} |
| 平仓盈亏 | {report['closed_pnl']*100:.2f}% |

## 💼 当前持仓

| 品种 | 名称 | 持仓 | 开仓价 | 当前价 | 盈亏 | 权重 |
|------|------|------|--------|--------|------|------|
"""
        
        for pos in report['positions']:
            md_content += f"| {pos['symbol']} | {pos['name']} | {pos['position']} | {pos['entry_price']:.2f} | {pos['current_price']:.2f} | {pos['pnl']:.2f}% | {pos['weight']:.0f}% |\n"
        
        # 交易记录
        md_content += """
## 📝 今日交易记录

"""
        
        if report['open_trades']:
            md_content += "### 🟢 开仓\n\n"
            for t in report['open_trades']:
                md_content += f"- {t['time']} {t['symbol']} {t['type']} @ {t['price']:.2f}\n"
        
        if report['closed_trades']:
            md_content += "\n### 🔴 平仓\n\n"
            for t in report['closed_trades']:
                md_content += f"- {t['time']} {t['symbol']} {t['type']} @ {t['price']:.2f} 盈亏: {t['pnl']*100:.2f}%\n"
        
        md_content += f"""
---
*Generated by Range Trading SimNow Trader*
"""
        
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        print(f"✅ 报告已保存: {json_path}")
        print(f"✅ Markdown报告: {md_path}")
        
        return report
    
    def run_simulation(self, use_live_data=False):
        """运行模拟交易"""
        print("=" * 60)
        print("🚀 Range Trading SimNow 模拟实盘")
        print("=" * 60)
        print()
        
        print("📋 SimNow配置:")
        print(f"   用户名: {SIMNOW_CONFIG['用户名']}")
        print(f"   交易服务器: {SIMNOW_CONFIG['交易服务器']}")
        print(f"   行情服务器: {SIMNOW_CONFIG['行情服务器']}")
        print()
        
        print("📋 策略配置:")
        print(f"   MA周期: {STRATEGY_CONFIG['ma_period']}")
        print(f"   ATR周期: {STRATEGY_CONFIG['atr_period']}")
        print(f"   ATR倍数: {STRATEGY_CONFIG['atr_multiplier']}")
        print(f"   止损: {STRATEGY_CONFIG['stop_loss']*100}%")
        print(f"   止盈: {STRATEGY_CONFIG['take_profit']*100}%")
        print()
        
        print("📋 交易品种:")
        for s in SYMBOLS:
            print(f"   {s['symbol']:4s} ({s['name']}) - 权重: {s['weight']*100:.0f}%")
        print()
        
        if not use_live_data:
            print("📂 使用历史数据进行模拟...")
            historical_data = self.load_historical_data()
            
            # 模拟回测
            print("\n🔄 运行模拟...")
            for s in SYMBOLS:
                symbol = s["symbol"]
                if symbol in historical_data:
                    df = historical_data[symbol]
                    # 只用最后100根K线模拟
                    df_tail = df.tail(100)
                    
                    for i in range(20, len(df_tail)):
                        window = df_tail.iloc[:i+1]
                        self.on_bar(symbol, window)
            
            # 生成报告
            report = self.save_daily_report()
            
            print("\n" + "=" * 60)
            print("📊 模拟结果")
            print("=" * 60)
            print(f"总盈亏: {report['total_pnl']:.2f}%")
            print(f"交易次数: {report['trade_count']}")
            print(f"平仓盈亏: {report['closed_pnl']*100:.2f}%")
        
        else:
            # 连接SimNow实时行情（需要vnpy_ctp）
            print("🔄 连接SimNow实时行情...")
            # TODO: 实现实时行情连接
            print("⚠️ 实时行情功能需要安装vnpy_ctp")


def main():
    """主函数"""
    trader = SimNowTrader()
    
    # 检查参数
    use_live = "--live" in sys.argv
    
    # 运行模拟
    trader.run_simulation(use_live_data=use_live)


if __name__ == "__main__":
    main()
