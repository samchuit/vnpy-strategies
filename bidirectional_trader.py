#!/usr/bin/env python3
"""
Binance 双边交易策略 (做多做空)
- 多头趋势：做多
- 空头趋势：做空
- 震荡行情：休息
"""

import sys
import os
import json
import logging
from datetime import datetime
from typing import Dict, List
from binance_config import API_KEY, API_SECRET, TESTNET
from binance import Client
from binance.enums import SIDE_BUY, SIDE_SELL

# 配置
TRADE_CONFIG = {
    "capital_cny": 10000,
    "leverage": 2,
    "symbols": [
        {"symbol": "BTCUSDT", "weight": 0.50, "stop_loss": 0.02, "take_profit": 0.08},
        {"symbol": "ETHUSDT", "weight": 0.30, "stop_loss": 0.02, "take_profit": 0.08},
        {"symbol": "SOLUSDT", "weight": 0.20, "stop_loss": 0.02, "take_profit": 0.08},
    ],
    "strategy": {
        "ma_fast": 10,
        "ma_slow": 20,
        "ma_trend": 90,
    },
}

# 日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bidirectional_trader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BidirectionalTrader:
    """双边交易策略"""
    
    def __init__(self):
        self.client = Client(API_KEY, API_SECRET, testnet=False)
        self.positions = {}  # position > 0: 多头, < 0: 空头
        self.entry_prices = {}
        
        for s in TRADE_CONFIG['symbols']:
            self.positions[s['symbol']] = 0
            self.entry_prices[s['symbol']] = 0
    
    def get_klines(self, symbol, interval='4h', limit=100):
        """获取K线"""
        try:
            klines = self.client.futures_klines(symbol=symbol, interval=interval, limit=limit)
            df = []
            for k in klines:
                df.append({
                    'close': float(k[4]),
                })
            return df
        except Exception as e:
            logger.error(f"获取{symbol}数据失败: {e}")
            return []
    
    def calculate_ma(self, df, period):
        """计算MA"""
        if len(df) < period:
            return df[-1]['close'] if df else 0
        closes = [k['close'] for k in df[-period:]]
        return sum(closes) / len(closes)
    
    def get_position_info(self, symbol):
        """获取持仓"""
        try:
            info = self.client.futures_position_information(symbol=symbol)
            for p in info:
                if p['symbol'] == symbol:
                    return {
                        'size': float(p['positionAmt']),
                        'entry_price': float(p['entryPrice']),
                    }
            return {'size': 0, 'entry_price': 0}
        except Exception as e:
            return {'size': 0, 'entry_price': 0}
    
    def set_leverage(self, symbol):
        """设置杠杆"""
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=TRADE_CONFIG['leverage'])
        except Exception as e:
            logger.warning(f"设置{symbol}杠杆失败: {e}")
    
    def generate_signal(self, symbol):
        """
        生成交易信号
        
        多头趋势：
        - 价格 > MA90
        - MA20 > MA90
        - MA10 > MA20 → 做多
        
        空头趋势：
        - 价格 < MA90
        - MA20 < MA90
        - MA10 < MA20 → 做空
        
        震荡：MA10和MA20在MA90两侧 → 不交易
        """
        df = self.get_klines(symbol)
        if not df:
            return "HOLD", {}
        
        close = df[-1]['close']
        ma10 = self.calculate_ma(df, TRADE_CONFIG['strategy']['ma_fast'])
        ma20 = self.calculate_ma(df, TRADE_CONFIG['strategy']['ma_slow'])
        ma90 = self.calculate_ma(df, TRADE_CONFIG['strategy']['ma_trend'])
        
        # 判断趋势
        in_uptrend = close > ma90 and ma20 > ma90  # 多头
        in_downtrend = close < ma90 and ma20 < ma90  # 空头
        in_range = not in_uptrend and not in_downtrend  # 震荡
        
        pos_info = self.get_position_info(symbol)
        position = pos_info['size']
        
        # 已有持仓，检查平仓
        if position > 0:  # 多头持仓
            if ma10 < ma20:  # 死叉
                return "CLOSE_LONG", {'close': close, 'reason': '死叉'}
            elif close < self.entry_prices[symbol] * (1 - TRADE_CONFIG['stop_loss']):
                return "CLOSE_LONG", {'close': close, 'reason': '止损'}
            elif close > self.entry_prices[symbol] * (1 + TRADE_CONFIG['take_profit']):
                return "CLOSE_LONG", {'close': close, 'reason': '止盈'}
        
        elif position < 0:  # 空头持仓
            if ma10 > ma20:  # 金叉
                return "CLOSE_SHORT", {'close': close, 'reason': '金叉'}
            elif close > self.entry_prices[symbol] * (1 + TRADE_CONFIG['stop_loss']):
                return "CLOSE_SHORT", {'close': close, 'reason': '止损'}
            elif close < self.entry_prices[symbol] * (1 - TRADE_CONFIG['take_profit']):
                return "CLOSE_SHORT", {'close': close, 'reason': '止盈'}
        
        # 无持仓，检查开仓
        if position == 0:
            if in_uptrend and ma10 > ma20:
                return "OPEN_LONG", {'close': close, 'ma10': ma10, 'ma20': ma20, 'ma90': ma90}
            elif in_downtrend and ma10 < ma20:
                return "OPEN_SHORT", {'close': close, 'ma10': ma10, 'ma20': ma20, 'ma90': ma90}
        
        return "HOLD", {'close': close, 'ma10': ma10, 'ma20': ma20, 'ma90': ma90, 'trend': 'up' if in_uptrend else ('down' if in_downtrend else 'range')}
    
    def run(self):
        """运行策略"""
        logger.info("=" * 60)
        logger.info("🚀 双边交易策略启动")
        logger.info("=" * 60)
        logger.info(f"💰 资金: {TRADE_CONFIG['capital_cny']} CNY")
        logger.info(f"📊 模式: 做多做空")
        logger.info("=" * 60)
        
        # 设置杠杆
        for s in TRADE_CONFIG['symbols']:
            self.set_leverage(s['symbol'])
        
        # 主循环
        import time
        while True:
            try:
                for s in TRADE_CONFIG['symbols']:
                    symbol = s['symbol']
                    
                    signal, info = self.generate_signal(symbol)
                    
                    # 获取持仓
                    pos_info = self.get_position_info(symbol)
                    position = pos_info['size']
                    self.entry_prices[symbol] = pos_info['entry_price']
                    
                    # 执行交易
                    if signal == "OPEN_LONG" and position == 0:
                        # 做多
                        quantity = 0.001  # 简化
                        self.client.futures_create_order(
                            symbol=symbol, side=SIDE_BUY, type='MARKET',
                            quantity=quantity
                        )
                        logger.info(f"🟢 {symbol} 做多 @ {info['close']}")
                    
                    elif signal == "OPEN_SHORT" and position == 0:
                        # 做空
                        quantity = 0.001
                        self.client.futures_create_order(
                            symbol=symbol, side=SIDE_SELL, type='MARKET',
                            quantity=quantity
                        )
                        logger.info(f"🔴 {symbol} 做空 @ {info['close']}")
                    
                    elif "CLOSE" in signal and position != 0:
                        side = SIDE_SELL if position > 0 else SIDE_BUY
                        self.client.futures_create_order(
                            symbol=symbol, side=side, type='MARKET',
                            quantity=abs(position)
                        )
                        logger.info(f"⚪ {symbol} 平仓 @ {info['close']} ({info['reason']})")
                    
                    elif signal == "HOLD":
                        trend = info.get('trend', 'unknown')
                        trend_emoji = "🟢" if trend == 'up' else ("🔴" if trend == 'down' else "🟡")
                        logger.info(f"{trend_emoji} {symbol}: 趋势{trend}, 无信号")
                
                time.sleep(300)  # 5分钟检查一次
                
            except KeyboardInterrupt:
                logger.info("🛑 停止")
                break
            except Exception as e:
                logger.error(f"错误: {e}")
                time.sleep(60)


def simulate_trend_check():
    """模拟检测趋势"""
    client = Client(API_KEY, API_SECRET, testnet=False)
    
    print("=" * 60)
    print("📊 双边策略趋势检测")
    print("=" * 60)
    
    for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
        try:
            klines = client.futures_klines(symbol=symbol, interval='4h', limit=100)
            closes = [float(k[4]) for k in klines]
            
            ma10 = sum(closes[-10:]) / 10
            ma20 = sum(closes[-20:]) / 20
            ma90 = sum(closes[-90:]) / 90 if len(closes) >= 90 else ma20
            close = closes[-1]
            
            in_uptrend = close > ma90 and ma20 > ma90
            in_downtrend = close < ma90 and ma20 < ma90
            
            print()
            print(f"📊 {symbol}:")
            print(f"   当前价: {close:.2f}")
            print(f"   MA10: {ma10:.2f}, MA20: {ma20:.2f}, MA90: {ma90:.2f}")
            
            if in_uptrend:
                print(f"   🟢 多头趋势 → 可做多")
            elif in_downtrend:
                print(f"   🔴 空头趋势 → 可做空")
            else:
                print(f"   🟡 震荡 → 不交易")
            
        except Exception as e:
            print(f"❌ {symbol}: {e}")


if __name__ == "__main__":
    # 先检测趋势
    simulate_trend_check()
    
    # 询问是否启动实盘
    print()
    print("=" * 60)
    print("要启动双边交易策略吗? (y/n)")
    print("=" * 60)
    
    # 直接运行
    # trader = BidirectionalTrader()
    # trader.run()
