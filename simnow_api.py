#!/usr/bin/env python3
"""
Range Trading SimNow 模拟实盘 (HTTP API版本)
使用SimNow REST API获取行情和交易
"""

import sys
import os
import json
import time
import requests
from datetime import datetime
from typing import Dict, List
from threading import Thread
import pandas as pd
import numpy as np

# 配置
SIMNOW_CONFIG = {
    "用户名": "17274709735",
    "密码": "a12345678",
    "经纪商代码": "9999",
    "交易服务器": "180.168.146.187:10101",
    "行情服务器": "180.168.146.187:10111",
    "产品名称": "simnow_client",
    "授权码": "255103",
}

SYMBOLS = [
    {"symbol": "CU", "vt_symbol": "CU.SHF", "name": "沪铜", "weight": 0.25},
    {"symbol": "HC", "vt_symbol": "HC.SHF", "name": "热卷", "weight": 0.20},
    {"symbol": "ZN", "vt_symbol": "ZN.SHF", "name": "沪锌", "weight": 0.15},
    {"symbol": "J", "vt_symbol": "J.DCE", "name": "焦炭", "weight": 0.15},
    {"symbol": "WR", "vt_symbol": "WR.SHF", "name": "线材", "weight": 0.10},
    {"symbol": "AL", "vt_symbol": "AL.SHF", "name": "沪铝", "weight": 0.10},
    {"symbol": "AU", "vt_symbol": "AU.SHF", "name": "黄金", "weight": 0.05},
]

STRATEGY_CONFIG = {
    "ma_period": 20,
    "atr_period": 14,
    "atr_multiplier": 2.0,
    "stop_loss": 0.03,
    "take_profit": 0.03,
}


class SimNowAPIClient:
    """SimNow API客户端"""
    
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.base_url = "https://api.simnow.com.cn"
    
    def login(self):
        """登录获取token"""
        try:
            # SimNow API登录
            url = f"{self.base_url}/api/v1/login"
            data = {
                "userid": SIMNOW_CONFIG['用户名'],
                "password": SIMNOW_CONFIG['密码'],
                "brokerid": SIMNOW_CONFIG['经纪商代码'],
            }
            response = self.session.post(url, json=data, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    self.token = result.get('token')
                    print(f"✅ SimNow API登录成功")
                    return True
            
            print(f"⚠️ SimNow API登录失败: {response.text}")
            return False
            
        except Exception as e:
            print(f"❌ SimNow API连接失败: {e}")
            return False
    
    def get_quote(self, symbol):
        """获取行情"""
        try:
            # 使用akshare获取实时行情
            import akshare as ak
            
            if symbol == "CU":
                df = ak.futures_zh_mini_sina(symbol="cu2409")
            elif symbol == "HC":
                df = ak.futures_zh_mini_sina(symbol="hc2409")
            elif symbol == "ZN":
                df = ak.futures_zh_mini_sina(symbol="zn2409")
            elif symbol == "J":
                df = ak.futures_zh_mini_sina(symbol="j2409")
            elif symbol == "WR":
                df = ak.futures_zh_mini_sina(symbol="wr2409")
            elif symbol == "AL":
                df = ak.futures_zh_mini_sina(symbol="al2409")
            elif symbol == "AU":
                df = ak.futures_zh_mini_sina(symbol="au2408")
            else:
                return None
            
            if df is not None and len(df) > 0:
                return {
                    'symbol': symbol,
                    'price': float(df.iloc[0]['最新价']),
                    'open': float(df.iloc[0]['开盘价']),
                    'high': float(df.iloc[0]['最高价']),
                    'low': float(df.iloc[0]['最低价']),
                    'volume': int(df.iloc[0]['成交量']),
                    'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            
        except Exception as e:
            print(f"⚠️ 获取{symbol}行情失败: {e}")
        
        return None


class RangeTradingStrategy:
    """Range Trading 策略"""
    
    def __init__(self):
        self.positions = {}  # 持仓
        self.entry_prices = {}  # 开仓价
        self.bars = {}  # K线数据
        self.trades = []  # 交易记录
        self.last_prices = {}  # 最新价
        
        for s in SYMBOLS:
            self.positions[s['symbol']] = 0
            self.entry_prices[s['symbol']] = 0
            self.bars[s['symbol']] = []
    
    def add_bar(self, symbol, bar):
        """添加K线"""
        self.bars[symbol].append(bar)
        self.last_prices[symbol] = bar['close']
    
    def calculate_indicators(self, symbol):
        """计算指标"""
        bars = self.bars.get(symbol, [])
        if len(bars) < STRATEGY_CONFIG['ma_period']:
            return None
        
        closes = [b['close'] for b in bars[-100:]]
        
        ma20 = np.mean(closes[-20:])
        atr = np.std(closes[-14:]) if len(closes) >= 14 else ma20 * 0.02
        
        return {
            'ma20': ma20,
            'atr': atr,
            'close': closes[-1],
        }
    
    def on_tick(self, symbol, tick):
        """行情回调"""
        # 简化的K线（实际应该用真实K线合成）
        if symbol not in self.last_prices:
            self.last_prices[symbol] = tick['price']
            return
        
        # 模拟K线更新
        bar = {
            'open': self.last_prices[symbol],
            'high': max(self.last_prices[symbol], tick['price']),
            'low': min(self.last_prices[symbol], tick['price']),
            'close': tick['price'],
            'volume': tick.get('volume', 0),
        }
        self.add_bar(symbol, bar)
        
        # 生成信号
        indicators = self.calculate_indicators(symbol)
        if indicators is None:
            return
        
        close = indicators['close']
        ma20 = indicators['ma20']
        atr = indicators['atr']
        
        signal = "HOLD"
        
        # 持有多头
        if self.positions[symbol] > 0:
            entry = self.entry_prices[symbol]
            if close > ma20 + atr * STRATEGY_CONFIG['atr_multiplier']:
                signal = "CLOSE"
            elif close < entry * (1 - STRATEGY_CONFIG['stop_loss']):
                signal = "CLOSE"
            elif close > entry * (1 + STRATEGY_CONFIG['take_profit']):
                signal = "CLOSE"
        else:
            if close < ma20 - atr * STRATEGY_CONFIG['atr_multiplier']:
                signal = "LONG"
        
        # 执行交易
        if signal == "LONG" and self.positions[symbol] == 0:
            self.positions[symbol] = 1
            self.entry_prices[symbol] = close
            self.trades.append({
                'symbol': symbol,
                'type': 'BUY',
                'price': close,
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'status': 'OPENED'
            })
            print(f"🟢 {symbol} 开多 @ {close:.2f}")
        
        elif signal == "CLOSE" and self.positions[symbol] > 0:
            entry = self.entry_prices[symbol]
            pnl = (close - entry) / entry
            self.positions[symbol] = 0
            self.trades.append({
                'symbol': symbol,
                'type': 'SELL',
                'price': close,
                'pnl': pnl,
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'status': 'CLOSED'
            })
            print(f"🔴 {symbol} 平多 @ {close:.2f} 盈亏: {pnl*100:.2f}%")
    
    def get_status(self):
        """获取状态"""
        total_pnl = 0
        position_info = []
        
        for s in SYMBOLS:
            symbol = s['symbol']
            pos = self.positions[symbol]
            
            if pos > 0:
                entry = self.entry_prices[symbol]
                current = self.last_prices.get(symbol, entry)
                pnl = (current - entry) / entry
                total_pnl += pnl * s['weight']
                
                position_info.append({
                    'symbol': symbol,
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
    """生成报告"""
    status = strategy.get_status()
    
    report = {
        "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **status,
    }
    
    report_path = "/Users/chusungang/workspace/vnpy-strategies/result/simnow_api"
    os.makedirs(report_path, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    json_path = f"{report_path}/api_{date_str}.json"
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 报告已保存: {json_path}")
    return report


def run_realtime():
    """运行实时模拟"""
    print("=" * 60)
    print("🚀 Range Trading SimNow 实时模拟")
    print("=" * 60)
    print()
    
    print("📋 配置:")
    print(f"   用户名: {SIMNOW_CONFIG['用户名']}")
    print(f"   品种: {[s['symbol'] for s in SYMBOLS]}")
    print()
    
    # 创建策略
    strategy = RangeTradingStrategy()
    
    # 加载历史数据初始化
    print("📂 加载历史数据...")
    data_path = "/Users/chusungang/workspace/vnpy_strategy/data_minute/"
    
    for s in SYMBOLS:
        file_path = f"{data_path}{s['symbol']}_60.csv"
        if os.path.exists(file_path):
            df = pd.read_csv(file_path)
            df.columns = [c.lower() for c in df.columns]
            
            # 只用最后50根K线初始化
            for i in range(-50, 0):
                if abs(i) <= len(df):
                    bar = {
                        'open': df.iloc[i]['open'],
                        'high': df.iloc[i]['high'],
                        'low': df.iloc[i]['low'],
                        'close': df.iloc[i]['close'],
                        'volume': df.iloc[i]['vol'],
                    }
                    strategy.add_bar(s['symbol'], bar)
    
    print(f"✅ 初始化完成")
    print()
    print("💡 使用akshare获取实时行情...")
    print("💡 按 Ctrl+C 停止")
    print()
    
    # 创建API客户端
    api_client = SimNowAPIClient()
    
    try:
        while True:
            # 获取所有品种行情
            for s in SYMBOLS:
                tick = api_client.get_quote(s['symbol'])
                if tick:
                    strategy.on_tick(s['symbol'], tick)
            
            # 每30秒显示状态
            if datetime.now().second == 0:
                status = strategy.get_status()
                print(f"📊 {datetime.now().strftime('%H:%M:%S')} | 持仓: {len(status['positions'])} | 盈亏: {status['total_pnl']:.2f}% | 交易: {status['trade_count']}次")
            
            time.sleep(5)  # 5秒更新一次
    
    except KeyboardInterrupt:
        print("\n🛑 停止")
    
    # 生成报告
    print("\n📝 生成报告...")
    generate_report(strategy)
    print("✅ 完成")


def main():
    run_realtime()


if __name__ == "__main__":
    main()
