#!/usr/bin/env python3
"""
Binance 数字货币自动交易 - K019 Trend 策略
直接使用requests替代binance库（避免SSL/代理问题）
"""

import sys
import os
import json
import time
import logging
import requests
import hmac
import hashlib
import urllib3
from datetime import datetime
from typing import Dict, List
from threading import Thread

# Binance API 密钥
from binance_config import API_KEY, API_SECRET, TESTNET

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 代理配置
PROXIES = {
    'http': None,
    'https': None,
}

# 交易配置
TRADE_CONFIG = {
    "capital_cny": 10000,        # 总资金 (CNY)
    "leverage": 2,               # 杠杆倍数
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
    """Binance 交易机器人 (直接使用requests)"""
    
    def __init__(self, api_key, api_secret, testnet=False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # 创建session禁用环境变量代理
        self.session = requests.Session()
        self.session.trust_env = False
        
        # 账户信息
        self.positions = {}        # 当前持仓
        self.entry_prices = {}     # 开仓价
        self.orders = {}           # 活跃订单
        self.balance = 0          # 账户余额
        
        # 策略状态
        self.ma_data = {}          # MA数据缓存
        self.last_signals = {}     # 上次信号
        
        # 初始化
        for s in TRADE_CONFIG['symbols']:
            self.positions[s['symbol']] = 0
            self.entry_prices[s['symbol']] = 0
            self.ma_data[s['symbol']] = []
            self.last_signals[s['symbol']] = "HOLD"
    
    def _request(self, method, endpoint, params=None):
        """发送API请求"""
        url = f"https://fapi.binance.com{endpoint}"
        headers = {'X-MBX-APIKEY': self.api_key}
        
        ts = int(time.time() * 1000)
        
        if params:
            params['timestamp'] = ts
            # 签名时包含所有参数
            query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
            params['signature'] = hmac.new(self.api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        else:
            # 无参数时只用时间戳签名
            params = {'timestamp': ts, 'signature': hmac.new(self.api_secret.encode('utf-8'), f'timestamp={ts}'.encode('utf-8'), hashlib.sha256).hexdigest()}
        
        try:
            if method == 'GET':
                resp = self.session.get(url, params=params, headers=headers, proxies=PROXIES, verify=False, timeout=10)
            else:
                # POST使用data而不是json，确保表单格式
                resp = self.session.post(url, data=params, headers=headers, proxies=PROXIES, verify=False, timeout=10)
            
            if resp.status_code != 200:
                logger.error(f"API错误: {resp.text}")
                return None
            return resp.json()
        except Exception as e:
            logger.error(f"请求失败: {e}")
            return None
    
    def get_price(self, symbol):
        """获取当前价格"""
        data = self._request('GET', '/fapi/v1/ticker/price', {'symbol': symbol})
        return float(data['price']) if data else None
    
    def get_klines(self, symbol, interval='4h', limit=100):
        """获取K线数据"""
        data = self._request('GET', '/fapi/v1/klines', {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        })
        if not data:
            return []
        
        df = []
        for k in data:
            df.append({
                'time': k[0],
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
            })
        return df
    
    def calculate_ma(self, df, period):
        """计算MA"""
        if len(df) < period:
            return df[-1]['close'] if df else 0
        closes = [k['close'] for k in df[-period:]]
        return sum(closes) / len(closes)
    
    def get_balance(self):
        """查询USDT余额"""
        data = self._request('GET', '/fapi/v2/balance')
        if data:
            for asset in data:
                if asset['asset'] == 'USDT':
                    self.balance = float(asset['balance'])
                    return self.balance
        return 0
    
    def set_leverage(self, symbol, leverage):
        """设置杠杆"""
        data = self._request('POST', '/fapi/v1/leverage', {'symbol': symbol, 'leverage': leverage})
        if data:
            logger.info(f"  {symbol} 杠杆设置为 {leverage}x")
            return True
        return False
    
    def get_position_info(self, symbol):
        """查询持仓"""
        data = self._request('GET', '/fapi/v2/positionRisk', {'symbol': symbol})
        if data:
            for p in data:
                if p['symbol'] == symbol:
                    return {
                        'size': float(p['positionAmt']),
                        'entry_price': float(p['entryPrice']),
                        'pnl': float(p['unRealizedProfit']),
                    }
        return {'size': 0, 'entry_price': 0, 'pnl': 0}
    
    def close_position(self, symbol, side):
        """平仓"""
        pos_info = self.get_position_info(symbol)
        if pos_info['size'] == 0:
            return True
        
        # 判断平仓方向
        position_side = 'LONG' if pos_info['size'] > 0 else 'SHORT'
        side_map = {'LONG': 'SELL', 'SHORT': 'BUY'}
        
        data = self._request('POST', '/fapi/v1/order', {
            'symbol': symbol,
            'side': side_map[position_side],
            'type': 'MARKET',
            'quantity': abs(pos_info['size']),
            'reduceOnly': 'true'
        })
        
        if data:
            logger.info(f"  平仓 {symbol} {position_side}")
            return True
        return False
    
    def open_position(self, symbol, side, amount):
        """开仓"""
        if amount <= 0:
            return True
        
        side_map = {'LONG': 'BUY', 'SHORT': 'SELL'}
        data = self._request('POST', '/fapi/v1/order', {
            'symbol': symbol,
            'side': side_map[side],
            'type': 'MARKET',
            'quantity': amount
        })
        
        if data:
            logger.info(f"  开仓 {symbol} {side} {amount}")
            return True
        return False
    
    def analyze_signal(self, symbol):
        """分析交易信号"""
        klines = self.get_klines(symbol, interval='4h', limit=150)
        if len(klines) < 100:
            return "HOLD"
        
        ma_fast = self.calculate_ma(klines, TRADE_CONFIG['strategy']['ma_fast'])
        ma_slow = self.calculate_ma(klines, TRADE_CONFIG['strategy']['ma_slow'])
        ma_trend = self.calculate_ma(klines, TRADE_CONFIG['strategy']['ma_trend'])
        
        current_price = klines[-1]['close']
        
        # 趋势判断：比较短期均线和长期均线
        ma_trend_50 = self.calculate_ma(klines[-50:], TRADE_CONFIG['strategy']['ma_trend']) if len(klines) >= 50 else ma_trend
        trend_up = current_price > ma_trend_50  # 价格在 MA90 均线上方 = 上升趋势
        
        # 信号判断：MA 金叉/死叉 + 趋势确认
        if ma_fast > ma_slow and trend_up:
            return "LONG"
        elif ma_fast < ma_slow and not trend_up:
            return "SHORT"
        else:
            return "HOLD"
    
    def trading_loop(self):
        """交易主循环"""
        logger.info("=" * 60)
        logger.info(f"💰 资金: {self.get_balance():.2f} USDT")
        logger.info(f"📊 杠杆: {TRADE_CONFIG['leverage']}x")
        logger.info(f"🎯 品种: {[s['symbol'] for s in TRADE_CONFIG['symbols']]}")
        logger.info("=" * 60)
        
        # 设置杠杆
        for s in TRADE_CONFIG['symbols']:
            self.set_leverage(s['symbol'], TRADE_CONFIG['leverage'])
        
        while True:
            try:
                # 获取余额
                self.get_balance()
                
                # 分析每个品种
                for s in TRADE_CONFIG['symbols']:
                    symbol = s['symbol']
                    signal = self.analyze_signal(symbol)
                    pos_info = self.get_position_info(symbol)
                    
                    current_size = pos_info['size']
                    current_signal = "LONG" if current_size > 0 else ("SHORT" if current_size < 0 else "HOLD")
                    
                    # 交易逻辑
                    if signal != current_signal:
                        logger.info(f"🔄 {symbol}: 信号变化 {current_signal} -> {signal}")
                        
                        # 先平仓
                        if current_size != 0:
                            self.close_position(symbol, current_signal)
                        
                        # 再开新仓
                        if signal != "HOLD":
                            # 计算开仓数量 (基于资金配置和权重)
                            weight = s['weight']  # 该币种的资金权重
                            leverage = TRADE_CONFIG['leverage']
                            capital = self.balance * leverage * weight  # 可用资金 * 杠杆 * 权重
                            amount = capital / current_price  # 按数量开仓
                            # 保留2位小数，避免太小
                            amount = round(amount, 2)
                            self.open_position(symbol, signal, amount)
                    
                    # 更新状态
                    self.last_signals[symbol] = signal
                
                # 输出状态
                total_pnl = 0
                logger.info("-" * 60)
                for s in TRADE_CONFIG['symbols']:
                    symbol = s['symbol']
                    pos_info = self.get_position_info(symbol)
                    size = pos_info['size']
                    pnl = pos_info['pnl']
                    total_pnl += pnl
                    
                    if size != 0:
                        logger.info(f"📊 {symbol}: {size} @ {pos_info['entry_price']:.2f} | PnL: {pnl:.2f}")
                    else:
                        logger.info(f"📊 {symbol}: 无持仓 | 信号: {self.last_signals[symbol]}")
                
                logger.info(f"💰 总PnL: {total_pnl:.2f} USDT")
                logger.info("-" * 60)
                
                # 等待下次检查
                time.sleep(TRADE_CONFIG['check_interval'])
                
            except KeyboardInterrupt:
                logger.info("🛑 手动停止交易")
                break
            except Exception as e:
                logger.error(f"错误: {e}")
                time.sleep(10)


def main():
    """主函数"""
    mode = "Testnet" if TESTNET else "实盘"
    logger.info(f"🚀 Binance 自动交易启动 ({mode})")
    
    trader = BinanceTrader(API_KEY, API_SECRET, testnet=TESTNET)
    trader.trading_loop()


if __name__ == "__main__":
    main()
