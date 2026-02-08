#!/usr/bin/env python3
"""
Binance 数字货币自动交易
K019 Trend 策略
"""

import sys
import os
import json
import time
import logging
from datetime import datetime
from typing import Dict, List
from threading import Thread

# Binance API
from binance import Client
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT
from binance.exceptions import BinanceAPIException

# 配置
TRADE_CONFIG = {
    "capital_cny": 10000,        # 总资金 (CNY)
    "leverage": 2,                # 杠杆倍数
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
    "check_interval": 300,        # 检查间隔 (秒)
}

# Binance API 密钥 (需要替换为实际密钥)
from binance_config import API_KEY, API_SECRET, TESTNET

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('binance_trader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BinanceTrader:
    """Binance 交易机器人"""
    
    def __init__(self, api_key, api_secret, testnet=True):
        """初始化"""
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # 连接Binance
        if TESTNET:
            self.client = Client(api_key, api_secret, testnet=True)
            logger.info("🧪 使用Binance Testnet")
        else:
            self.client = Client(api_key, api_secret)
            logger.info("🚀 使用Binance 实盘")
        
        # 账户信息
        self.positions = {}        # 当前持仓
        self.entry_prices = {}     # 开仓价
        self.orders = {}           # 活跃订单
        self.balance = 0           # 账户余额
        
        # 策略状态
        self.ma_data = {}          # MA数据缓存
        self.last_signals = {}     # 上次信号
        
        # 初始化
        for s in TRADE_CONFIG['symbols']:
            self.positions[s['symbol']] = 0
            self.entry_prices[s['symbol']] = 0
            self.ma_data[s['symbol']] = []
            self.last_signals[s['symbol']] = "HOLD"
    
    def get_price(self, symbol):
        """获取当前价格"""
        try:
            ticker = self.client.futures_ticker(symbol=symbol)
            return float(ticker['lastPrice'])
        except Exception as e:
            logger.error(f"获取{symbol}价格失败: {e}")
            return None
    
    def get_klines(self, symbol, interval='4h', limit=100):
        """获取K线数据"""
        try:
            klines = self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
            df = []
            for k in klines:
                df.append({
                    'time': k[0],
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5]),
                })
            
            return df
            
        except Exception as e:
            logger.error(f"获取{symbol}K线失败: {e}")
            return []
    
    def calculate_ma(self, df, period):
        """计算MA"""
        if len(df) < period:
            return df[-1]['close'] if df else 0
        closes = [k['close'] for k in df[-period:]]
        return sum(closes) / len(closes)
    
    def get_position_info(self, symbol):
        """获取持仓信息"""
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            for p in positions:
                if p['symbol'] == symbol:
                    return {
                        'size': float(p['positionAmt']),
                        'entry_price': float(p['entryPrice']),
                        'pnl': float(p['unRealizedProfit']),
                    }
            return {'size': 0, 'entry_price': 0, 'pnl': 0}
        except Exception as e:
            logger.error(f"获取{symbol}持仓失败: {e}")
            return {'size': 0, 'entry_price': 0, 'pnl': 0}
    
    def set_leverage(self, symbol, leverage):
        """设置杠杆"""
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
            logger.info(f"{symbol} 杠杆设置为 {leverage}x")
        except Exception as e:
            logger.error(f"设置{symbol}杠杆失败: {e}")
    
    def calculate_position_size(self, symbol, price, weight):
        """计算仓位大小"""
        # 总资金 (USD)
        total_usd = TRADE_CONFIG['capital_cny'] / 7.2  # 假设汇率 1 USD = 7.2 CNY
        
        # 单品种资金
        symbol_usd = total_usd * weight
        
        # 合约数量 (USDT本位)
        quantity = (symbol_usd * TRADE_CONFIG['leverage']) / price
        
        return round(quantity, 3)
    
    def open_position(self, symbol, side, quantity):
        """开仓"""
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type=ORDER_TYPE_MARKET,
                quantity=quantity,
            )
            
            logger.info(f"🟢 开仓: {symbol} {side} {quantity}")
            return order
            
        except BinanceAPIException as e:
            logger.error(f"开仓失败: {e}")
            return None
    
    def close_position(self, symbol):
        """平仓"""
        try:
            pos_info = self.get_position_info(symbol)
            if pos_info['size'] == 0:
                return None
            
            side = SIDE_SELL if pos_info['size'] > 0 else SIDE_BUY
            
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type=ORDER_TYPE_MARKET,
                quantity=abs(pos_info['size']),
            )
            
            logger.info(f"🔴 平仓: {symbol}")
            return order
            
        except BinanceAPIException as e:
            logger.error(f"平仓失败: {e}")
            return None
    
    def generate_signal(self, symbol):
        """生成交易信号"""
        # 获取K线
        df = self.get_klines(symbol, interval='4h', limit=100)
        if not df:
            return "HOLD"
        
        # 计算MA
        ma_fast = self.calculate_ma(df, TRADE_CONFIG['strategy']['ma_fast'])
        ma_slow = self.calculate_ma(df, TRADE_CONFIG['strategy']['ma_slow'])
        ma_trend = self.calculate_ma(df, TRADE_CONFIG['strategy']['ma_trend'])
        close = df[-1]['close']
        
        # 判断趋势
        in_uptrend = close > ma_trend and ma_slow > ma_trend
        
        pos_info = self.get_position_info(symbol)
        position = pos_info['size']
        
        # 生成信号
        if position > 0:
            # 持有多头，检查平仓
            if ma_fast < ma_slow:
                return "CLOSE"
            # 止损/止盈
            entry = pos_info['entry_price']
            if close < entry * (1 - TRADE_CONFIG['stop_loss']):
                return "CLOSE"
            elif close > entry * (1 + TRADE_CONFIG['take_profit']):
                return "CLOSE"
        else:
            # 开仓信号
            if ma_fast > ma_slow and in_uptrend:
                return "LONG"
        
        return "HOLD"
    
    def run_strategy(self):
        """运行策略"""
        logger.info("=" * 60)
        logger.info("🚀 Binance 自动交易启动")
        logger.info("=" * 60)
        logger.info(f"💰 资金: {TRADE_CONFIG['capital_cny']} CNY")
        logger.info(f"📊 杠杆: {TRADE_CONFIG['leverage']}x")
        logger.info(f"🎯 品种: {[s['symbol'] for s in TRADE_CONFIG['symbols']]}")
        logger.info("=" * 60)
        
        # 设置杠杆
        for s in TRADE_CONFIG['symbols']:
            self.set_leverage(s['symbol'], TRADE_CONFIG['leverage'])
        
        # 主循环
        while True:
            try:
                for s in TRADE_CONFIG['symbols']:
                    symbol = s['symbol']
                    weight = s['weight']
                    
                    # 生成信号
                    signal = self.generate_signal(symbol)
                    
                    if signal != "HOLD" and signal != self.last_signals[symbol]:
                        logger.info(f"📊 {symbol} 信号: {signal}")
                    
                    # 获取持仓
                    pos_info = self.get_position_info(symbol)
                    
                    # 执行交易
                    if signal == "LONG" and pos_info['size'] == 0:
                        # 开仓
                        price = self.get_price(symbol)
                        if price:
                            quantity = self.calculate_position_size(symbol, price, weight)
                            if quantity > 0.001:
                                self.open_position(symbol, SIDE_BUY, quantity)
                    
                    elif signal == "CLOSE" and pos_info['size'] != 0:
                        # 平仓
                        self.close_position(symbol)
                    
                    # 更新信号
                    self.last_signals[symbol] = signal
                
                # 打印状态
                self.print_status()
                
                # 等待
                time.sleep(TRADE_CONFIG['check_interval'])
                
            except KeyboardInterrupt:
                logger.info("🛑 收到停止信号")
                break
            except Exception as e:
                logger.error(f"错误: {e}")
                time.sleep(60)
    
    def print_status(self):
        """打印状态"""
        total_pnl = 0
        
        for s in TRADE_CONFIG['symbols']:
            pos_info = self.get_position_info(s['symbol'])
            if pos_info['size'] != 0:
                pnl_pct = pos_info['pnl'] / (pos_info['size'] * pos_info['entry_price']) * 100
                total_pnl += pos_info['pnl']
                logger.info(f"📊 {s['symbol']}: 持仓 {pos_info['size']} @ {pos_info['entry_price']:.2f} PnL: {pos_info['pnl']:.2f} ({pnl_pct:+.2f}%)")
            else:
                logger.info(f"📊 {s['symbol']}: 无持仓")
        
        logger.info(f"💰 总PnL: {total_pnl:.2f}")
        logger.info("-" * 40)


def main():
    """主函数"""
    # 检查API密钥
    if not API_KEY or not API_SECRET:
        logger.error("❌ 请先配置API密钥!")
        logger.info("设置方法:")
        logger.info("1. 登录 Binance Futures Testnet")
        logger.info("2. 创建 API Key")
        logger.info("3. 修改脚本中的 API_KEY 和 API_SECRET")
        return
    
    # 创建交易机器人
    trader = BinanceTrader(API_KEY, API_SECRET, testnet=True)
    
    # 运行策略
    trader.run_strategy()


if __name__ == "__main__":
    main()
