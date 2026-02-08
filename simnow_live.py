#!/usr/bin/env python3
"""
Range Trading SimNow 实时交易
使用 vnpy_ctp 连接 SimNow 实时行情和交易
"""

import sys
import os
import json
import time
from datetime import datetime
from typing import Dict
from threading import Thread

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

# 交易品种配置
SYMBOLS = [
    {"symbol": "CU", "vt_symbol": "CU.SHF", "name": "沪铜", "weight": 0.25},
    {"symbol": "HC", "vt_symbol": "HC.SHF", "name": "热卷", "weight": 0.20},
    {"symbol": "ZN", "vt_symbol": "ZN.SHF", "name": "沪锌", "weight": 0.15},
    {"symbol": "J", "vt_symbol": "J.DCE", "name": "焦炭", "weight": 0.15},
    {"symbol": "WR", "vt_symbol": "WR.SHF", "name": "线材", "weight": 0.10},
    {"symbol": "AL", "vt_symbol": "AL.SHF", "name": "沪铝", "weight": 0.10},
    {"symbol": "AU", "vt_symbol": "AU.SHF", "name": "黄金", "weight": 0.05},
]

# Range Trading 策略参数
STRATEGY_CONFIG = {
    "ma_period": 20,
    "atr_period": 14,
    "atr_multiplier": 2.0,
    "stop_loss": 0.03,
    "take_profit": 0.03,
    "trailing_stop": 0.02,
}


class CtpGateway:
    """CTP网关连接"""
    
    def __init__(self):
        self.gateway = None
        self.connected = False
        self.subscribed = set()
        self.bars = {}  # K线数据
        self.last_prices = {}  # 最新价
        self.positions = {}  # 持仓
        self.account = {}  # 账户信息
    
    def connect(self):
        """连接SimNow"""
        try:
            from vnpy.gateway.ctp import CtpGateway as VnpyCtpGateway
            
            self.gateway = VnpyCtpGateway(self)
            self.gateway.connect(
                userid=SIMNOW_CONFIG['用户名'],
                password=SIMNOW_CONFIG['密码'],
                brokerid=SIMNOW_CONFIG['经纪商代码'],
                td_address=SIMNOW_CONFIG['交易服务器'],
                md_address=SIMNOW_CONFIG['行情服务器'],
                appid=SIMNOW_CONFIG['产品名称'],
                authcode=SIMNOW_CONFIG['授权码'],
            )
            
            print(f"✅ CTP网关已启动")
            print(f"📡 交易服务器: {SIMNOW_CONFIG['交易服务器']}")
            print(f"📡 行情服务器: {SIMNOW_CONFIG['行情服务器']}")
            
            return True
            
        except ImportError as e:
            print(f"❌ 导入失败: {e}")
            print("💡 需要安装 vnpy_ctp 的底层库")
            return False
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return False
    
    def subscribe(self, vt_symbol):
        """订阅行情"""
        if vt_symbol not in self.subscribed:
            self.gateway.subscribe(vt_symbol)
            self.subscribed.add(vt_symbol)
    
    def on_tick(self, tick):
        """行情回调"""
        vt_symbol = tick.vt_symbol
        self.last_prices[vt_symbol] = tick.last_price
        
        # 累积K线
        if vt_symbol not in self.bars:
            self.bars[vt_symbol] = []
        
        # 简单的K线合成（实际应该用bar_generator）
        bar = {
            'open': tick.open_price,
            'high': tick.high_price,
            'low': tick.low_price,
            'close': tick.last_price,
            'volume': tick.volume,
            'datetime': tick.datetime,
        }
        self.bars[vt_symbol].append(bar)
    
    def on_order(self, order):
        """委托回调"""
        print(f"📝 委托: {order.vt_symbol} {order.status} {order.offset} {order.direction} @ {order.price}")
    
    def on_trade(self, trade):
        """成交回调"""
        print(f"✅ 成交: {trade.vt_symbol} {trade.offset} {trade.direction} @ {trade.price}")


class RangeTradingStrategy:
    """Range Trading 策略"""
    
    def __init__(self, gateway: CtpGateway):
        self.gateway = gateway
        self.positions = {}  # 持仓
        self.entry_prices = {}  # 开仓价
        self.bars = {}  # K线数据
        self.trades = []  # 交易记录
        
        # 初始化
        for s in SYMBOLS:
            self.positions[s['vt_symbol']] = 0
            self.entry_prices[s['vt_symbol']] = 0
    
    def calculate_indicators(self, vt_symbol):
        """计算技术指标"""
        bars = self.bars.get(vt_symbol, [])
        if len(bars) < STRATEGY_CONFIG['ma_period']:
            return None
        
        closes = [b['close'] for b in bars]
        closes_series = closes[-100:]  # 只用最近100根
        
        import numpy as np
        
        ma20 = np.mean(closes_series[-20:])
        atr = np.std(closes_series[-14:]) if len(closes_series) >= 14 else ma20 * 0.02
        
        return {
            'ma20': ma20,
            'atr': atr,
            'close': closes_series[-1],
        }
    
    def on_bar(self, vt_symbol, bar):
        """K线回调"""
        # 累积K线
        if vt_symbol not in self.bars:
            self.bars[vt_symbol] = []
        self.bars[vt_symbol].append(bar)
        
        # 计算指标
        indicators = self.calculate_indicators(vt_symbol)
        if indicators is None:
            return
        
        close = indicators['close']
        ma20 = indicators['ma20']
        atr = indicators['atr']
        
        # 生成信号
        signal = "HOLD"
        
        # 持有多头，检查平仓
        if self.positions[vt_symbol] > 0:
            if close > ma20 + atr * STRATEGY_CONFIG['atr_multiplier']:
                signal = "CLOSE"
            # 止损/止盈
            entry = self.entry_prices[vt_symbol]
            if close < entry * (1 - STRATEGY_CONFIG['stop_loss']):
                signal = "CLOSE"
            elif close > entry * (1 + STRATEGY_CONFIG['take_profit']):
                signal = "CLOSE"
        else:
            # 开仓信号
            if close < ma20 - atr * STRATEGY_CONFIG['atr_multiplier']:
                signal = "LONG"
        
        # 执行交易
        if signal == "LONG" and self.positions[vt_symbol] == 0:
            self.positions[vt_symbol] = 1
            self.entry_prices[vt_symbol] = close
            self.trades.append({
                'symbol': vt_symbol,
                'type': 'BUY',
                'price': close,
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            print(f"🟢 开多 {vt_symbol} @ {close:.2f}")
            
        elif signal == "CLOSE" and self.positions[vt_symbol] > 0:
            entry = self.entry_prices[vt_symbol]
            pnl = (close - entry) / entry
            self.positions[vt_symbol] = 0
            self.trades.append({
                'symbol': vt_symbol,
                'type': 'SELL',
                'price': close,
                'pnl': pnl,
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            print(f"🔴 平多 {vt_symbol} @ {close:.2f} 盈亏: {pnl*100:.2f}%")
    
    def get_status(self):
        """获取状态"""
        total_pnl = 0
        position_info = []
        
        for s in SYMBOLS:
            vt_symbol = s['vt_symbol']
            pos = self.positions[vt_symbol]
            
            if pos > 0:
                entry = self.entry_prices[vt_symbol]
                current = self.gateway.last_prices.get(vt_symbol, entry)
                pnl = (current - entry) / entry
                total_pnl += pnl * s['weight']
                
                position_info.append({
                    'symbol': s['symbol'],
                    'name': s['name'],
                    'position': pos,
                    'entry_price': entry,
                    'current_price': current,
                    'pnl': pnl * 100,
                    'weight': s['weight'] * 100,
                })
        
        return {
            'positions': position_info,
            'total_pnl': total_pnl * 100,
            'trade_count': len(self.trades),
            'trades': self.trades,
        }


def generate_report(strategy: RangeTradingStrategy):
    """生成每日报告"""
    status = strategy.get_status()
    
    report = {
        "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": STRATEGY_CONFIG,
        **status,
    }
    
    # 保存JSON
    report_path = "/Users/chusungang/workspace/vnpy-strategies/result/simnow_live"
    os.makedirs(report_path, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    json_path = f"{report_path}/live_{date_str}.json"
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    # 生成Markdown
    md_path = f"{report_path}/live_{date_str}.md"
    
    md_content = f"""# Range Trading SimNow 实时交易报告

**生成时间**: {report['report_time']}

## 📊 总体情况

| 指标 | 数值 |
|------|------|
| 总账户盈亏 | {report['total_pnl']:.2f}% |
| 交易次数 | {report['trade_count']} |

## 💼 当前持仓

| 品种 | 名称 | 持仓 | 开仓价 | 当前价 | 盈亏 | 权重 |
|------|------|------|--------|--------|------|------|
"""
    
    for pos in report['positions']:
        md_content += f"| {pos['symbol']} | {pos['name']} | {pos['position']} | {pos['entry_price']:.2f} | {pos['current_price']:.2f} | {pos['pnl']:.2f}% | {pos['weight']:.0f}% |\n"
    
    # 交易记录
    md_content += "\n## 📝 交易记录\n\n"
    for t in report['trades']:
        pnl_str = f"盈亏: {t['pnl']*100:.2f}%" if 'pnl' in t else ""
        md_content += f"- {t['time']} {t['symbol']} {t['type']} @ {t['price']:.2f} {pnl_str}\n"
    
    md_content += "\n---\n*Generated by Range Trading SimNow Live Trader*"
    
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print(f"✅ 报告已保存: {json_path}")
    
    return report


def run_simnow_live():
    """运行SimNow实时交易"""
    print("=" * 60)
    print("🚀 Range Trading SimNow 实时交易")
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
    
    # 创建CTP连接
    gateway = CtpGateway()
    
    print("🔄 连接SimNow...")
    if not gateway.connect():
        print("❌ 连接失败")
        return
    
    print()
    print("📋 交易品种:")
    for s in SYMBOLS:
        print(f"   {s['symbol']:4s} ({s['name']}) - 权重: {s['weight']*100:.0f}%")
    print()
    
    print("📋 订阅品种行情...")
    for s in SYMBOLS:
        gateway.subscribe(s['vt_symbol'])
    
    # 创建策略
    strategy = RangeTradingStrategy(gateway)
    
    print()
    print("✅ SimNow实时交易已启动")
    print("💡 按 Ctrl+C 停止")
    print()
    
    # 主循环
    try:
        while True:
            time.sleep(1)
            
            # 每分钟检查一次状态
            if datetime.now().second == 0:
                status = strategy.get_status()
                print(f"📊 持仓: {len(status['positions'])}个, 盈亏: {status['total_pnl']:.2f}%, 交易: {status['trade_count']}次")
    
    except KeyboardInterrupt:
        print("\n🛑 收到停止信号")
    
    # 生成报告
    print("\n📝 生成最终报告...")
    generate_report(strategy)
    
    print("✅ 停止完成")


def run_demo():
    """演示模式（使用历史数据）"""
    print("=" * 60)
    print("🚀 Range Trading SimNow 演示模式")
    print("=" * 60)
    
    import pandas as pd
    import numpy as np
    
    # 加载数据
    data_path = "/Users/chusungang/workspace/vnpy_strategy/data_minute/"
    
    print("\n📂 加载历史数据...")
    
    for s in SYMBOLS:
        symbol = s['symbol']
        file_path = f"{data_path}{symbol}_60.csv"
        
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            df.columns = [c.lower() for c in df.columns]
            
            # 只用最后100根K线
            df = df.tail(100)
            
            # 运行策略
            print(f"\n📊 {s['symbol']} ({s['name']}) 模拟...")
            
            for i in range(20, len(df)):
                bar = {
                    'open': df.iloc[i]['open'],
                    'high': df.iloc[i]['high'],
                    'low': df.iloc[i]['low'],
                    'close': df.iloc[i]['close'],
                    'volume': df.iloc[i]['vol'] if 'vol' in df.columns else df.iloc[i]['volume'],
                }
                # 这里简化处理，实际应该调用策略
    
    print("\n✅ 演示完成")


def main():
    """主函数"""
    if "--live" in sys.argv:
        run_simnow_live()
    else:
        run_demo()


if __name__ == "__main__":
    main()
