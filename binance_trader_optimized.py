#!/usr/bin/env python3
"""
Binance 数字货币自动交易 - 优化版双边MA策略
直接使用requests替代binance库（避免SSL/代理问题）

优化点:
1. MA10/30 交叉 + MA120 趋势确认
2. ATR移动止损 (3%)
3. 趋势强度过滤 (距离MA > 2% ATR)
4. 动态止盈 (ATR*2)
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

# 交易配置 - 最优参数 (MA15/30/80, 5年回测验证)
TRADE_CONFIG = {
    "capital_usdt": 9000,       # 总资金 (USDT) - 调整为原来的90%
    "leverage": 2,               # 杠杆倍数
    "symbols": [
        {"symbol": "BTCUSDT", "weight": 0.50, "stop_loss": 0.02, "max_qty": 0.035},
        {"symbol": "ETHUSDT", "weight": 0.30, "stop_loss": 0.02, "max_qty": 0.75},
        {"symbol": "SOLUSDT", "weight": 0.20, "stop_loss": 0.02, "max_qty": 12.0},
    ],
    "strategy": {
        "ma_fast": 15,           # 快速MA (最优)
        "ma_slow": 30,           # 慢速MA (最优)
        "ma_trend": 80,           # 趋势MA (最优关键)
        "atr_period": 14,         # ATR周期
        "atr_multiplier": 2.0,    # ATR止盈倍数 (最优)
        "trailing_stop": 0.03,    # 移动止损3% (最优)
        "min_trend_strength": 0.02, # 最小趋势强度2% (最优)
    },
    "check_interval": 60,        # 检查间隔 (1分钟)
}

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('binance_trader_optimized.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BinanceTrader:
    """Binance 交易机器人 (优化版)"""
    
    def __init__(self, api_key, api_secret, testnet=False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # 创建session并使用代理
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.proxies = PROXIES
        
        # 账户信息
        self.positions = {}            # 当前持仓
        self.entry_prices = {}         # 开仓价
        self.trailing_high = {}        # 移动止损高点
        self.trailing_low = {}         # 移动止损低点
        self.balance = 0               # 账户余额
        
        # 策略状态
        self.last_signals = {}         # 上次信号
        
        # 初始化
        for s in TRADE_CONFIG['symbols']:
            symbol = s['symbol']
            self.positions[symbol] = 0
            self.entry_prices[symbol] = 0
            self.trailing_high[symbol] = 0
            self.trailing_low[symbol] = 0
            self.last_signals[symbol] = "HOLD"
    
    def _get_server_time(self):
        """获取 Binance 服务器时间并计算偏差"""
        try:
            # 使用更可靠的 endpoint
            resp = requests.get("https://fapi.binance.com/fapi/v1/time", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if 'serverTime' in data:
                    server_time = data['serverTime']
                    local_time = int(time.time() * 1000)
                    self.time_offset = server_time - local_time
                    logger.info(f"⏰ 时间戳同步: offset={self.time_offset}ms")
                    return server_time
        except Exception as e:
            logger.warning(f"⏰ 时间戳同步失败: {e}")
        return None
    
    def _request(self, method, endpoint, params=None):
        """发送API请求 (带时间戳同步)"""
        base_url = "https://fapi.binance.com"
        headers = {'X-MBX-APIKEY': self.api_key}
        
        # 初始化时间戳偏移
        if not hasattr(self, 'time_offset'):
            self.time_offset = 0
        
        # 请求计数
        if not hasattr(self, '_request_count'):
            self._request_count = 0
        self._request_count += 1
        
        # 每50次请求重新同步时间（更频繁）
        if self._request_count % 50 == 0 or self.time_offset == 0:
            self._get_server_time()
        
        # 使用补偿后的时间戳
        ts = int(time.time() * 1000) + self.time_offset
        
        # Binance API 要求 timestamp 必须在 recvWindow 内
        # 默认 recvWindow = 5000ms，所以 timestamp 误差不能超过 5 秒
        if params:
            params['timestamp'] = ts
            params['recvWindow'] = 10000  # 增加 recvWindow 到 10 秒
            # 过滤None值并排序
            params = {k: str(v) for k, v in sorted(params.items()) if v is not None}
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            params['signature'] = hmac.new(self.api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        else:
            query_string = f"timestamp={ts}&recvWindow=10000"
            signature = hmac.new(self.api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
            params = {'timestamp': ts, 'recvWindow': '10000', 'signature': signature}
        
        try:
            url = f"{base_url}{endpoint}"
            
            if method == 'GET':
                resp = requests.get(url, params=params, headers=headers, timeout=10)
            else:
                resp = requests.post(url, data=params, headers=headers, timeout=10)
            
            if resp.status_code != 200:
                # 如果是时间戳错误，立即重新同步
                if '-1021' in resp.text:
                    logger.warning("⏰ 检测到时间戳错误，重新同步...")
                    self._get_server_time()
                    # 重新计算时间戳
                    ts = int(time.time() * 1000) + getattr(self, 'time_offset', 0)
                    if params:
                        params['timestamp'] = ts
                        params['recvWindow'] = 10000
                        params = {k: str(v) for k, v in sorted(params.items()) if v is not None}
                        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
                        params['signature'] = hmac.new(self.api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
                    
                    # 重试一次
                    if method == 'GET':
                        resp = requests.get(url, params=params, headers=headers, timeout=10)
                    else:
                        resp = requests.post(url, data=params, headers=headers, timeout=10)
                
                if resp.status_code != 200:
                    logger.error(f"API错误: {resp.text[:100]}")
                    return None
            return resp.json()
        except Exception as e:
            logger.error(f"请求失败: {e}")
            return None
    
    def get_price(self, symbol):
        """获取当前价格"""
        data = self._request('GET', '/fapi/v1/ticker/price', {'symbol': symbol})
        return float(data['price']) if data else None
    
    def get_klines(self, symbol, interval='1h', limit=1000):
        """获取K线数据 (1小时)"""
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
    
    def calculate_atr(self, df, period=14):
        """计算ATR"""
        if len(df) < period + 1:
            return 0
        
        tr_list = []
        for i in range(1, len(df)):
            high = df[i]['high']
            low = df[i]['low']
            prev_close = df[i-1]['close']
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_list.append(tr)
        
        return sum(tr_list[-period:]) / period if tr_list else 0
    
    def calculate_trend_strength(self, close, ma_trend, atr):
        """计算趋势强度"""
        if atr == 0:
            return 0
        return abs(close - ma_trend) / atr
    
    def get_current_price(self, symbol):
        """获取当前价格"""
        try:
            data = self._request('GET', '/fapi/v3/ticker/price', {'symbol': symbol})
            if data and 'price' in data:
                return float(data['price'])
        except:
            pass
        return None
    
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
    
    def close_position(self, symbol, side, reason="CLOSE"):
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
            logger.info(f"  平仓 {symbol} {position_side} ({reason})")
            # 重置移动止损
            self.trailing_high[symbol] = 0
            self.trailing_low[symbol] = 0
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
        """
        分析交易信号 - 优化版
        
        规则:
        - 强上升趋势 & MA10>MA30 → 做多
        - 强下降趋势 & MA10<MA30 → 做空
        - 弱趋势 → 不交易
        """
        # 获取1小时数据
        klines = self.get_klines(symbol, interval='1h', limit=1000)
        if len(klines) < 151:  # 需要足够的K线计算MA (排除最后一根)
            return "HOLD", {'atr': 0}, 0
        
        cfg = TRADE_CONFIG['strategy']
        
        # 使用已收盘的K线计算指标 (排除最后一根未收盘的K线)
        # 这样与回测逻辑一致
        closed_klines = klines[:-1]
        
        # 使用已收盘K线的收盘价作为当前价格 (与回测一致)
        # 不使用实时API，避免网络波动和延迟问题
        current_price = closed_klines[-1]['close']
        
        # 计算各项指标 (使用已收盘K线)
        closes = [k['close'] for k in closed_klines]
        ma_fast = self.calculate_ma(closed_klines, cfg['ma_fast'])
        ma_slow = self.calculate_ma(closed_klines, cfg['ma_slow'])
        ma_trend = self.calculate_ma(closed_klines, cfg['ma_trend'])
        atr = self.calculate_atr(closed_klines, cfg['atr_period'])
        
        # 计算趋势强度 (实时价格 vs MA80)
        trend_strength = self.calculate_trend_strength(current_price, ma_trend, atr)
        
        # 判断趋势 (用实时价格比较)
        strong_uptrend = (
            current_price > ma_trend and 
            ma_slow > ma_trend and 
            trend_strength > cfg['min_trend_strength']
        )
        strong_downtrend = (
            current_price < ma_trend and 
            ma_slow < ma_trend and 
            trend_strength > cfg['min_trend_strength']
        )
        
        # 生成信号
        if strong_uptrend and ma_fast > ma_slow:
            signal = "LONG"
        elif strong_downtrend and ma_fast < ma_slow:
            signal = "SHORT"
        else:
            signal = "HOLD"
        
        # 返回信号和指标
        indicators = {
            'ma_fast': ma_fast,
            'ma_slow': ma_slow,
            'ma_trend': ma_trend,
            'atr': atr,
            'trend_strength': trend_strength,
            'uptrend': strong_uptrend,
            'downtrend': strong_downtrend,
        }
        
        return signal, indicators, current_price
    
    def check_stop_conditions(self, symbol, current_price, pos_info, indicators):
        """
        检查止损/止盈条件
        
        返回: (should_close, reason)
        """
        size = pos_info['size']
        entry_price = pos_info['entry_price']
        
        # 从配置获取参数
        cfg_strategy = TRADE_CONFIG['strategy']
        cfg_symbol = next((s for s in TRADE_CONFIG['symbols'] if s['symbol'] == symbol), {})
        
        stop_loss = cfg_symbol.get('stop_loss', TRADE_CONFIG['symbols'][0]['stop_loss'])
        trailing_stop = cfg_strategy['trailing_stop']
        atr_multiplier = cfg_strategy['atr_multiplier']
        atr = indicators['atr']
        
        if size == 0:
            return False, None
        
        # 多头持仓
        if size > 0:
            # 更新移动止损高点
            self.trailing_high[symbol] = max(self.trailing_high[symbol], current_price)
            
            # 止损
            if current_price < entry_price * (1 - stop_loss):
                return True, "SL"
            
            # 移动止损
            trailing_stop_price = self.trailing_high[symbol] * (1 - trailing_stop)
            if trailing_stop_price > entry_price * (1 + stop_loss) and current_price < trailing_stop_price:
                return True, "TS"
            
            # 止盈 (ATR倍数)
            take_profit_price = entry_price * (1 + atr_multiplier * atr / entry_price)
            if current_price >= take_profit_price:
                return True, "TP"
        
        # 空头持仓
        else:
            # 更新移动止损低点
            self.trailing_low[symbol] = min(self.trailing_low[symbol], current_price)
            
            # 止损
            if current_price > entry_price * (1 + stop_loss):
                return True, "SL"
            
            # 移动止损
            trailing_stop_price = self.trailing_low[symbol] * (1 + trailing_stop)
            if trailing_stop_price < entry_price * (1 - stop_loss) and current_price > trailing_stop_price:
                return True, "TS"
            
            # 止盈 (ATR倍数)
            take_profit_price = entry_price * (1 - atr_multiplier * atr / entry_price)
            if current_price <= take_profit_price:
                return True, "TP"
        
        return False, None
    
    def trading_loop(self):
        """交易主循环"""
        logger.info("=" * 70)
        logger.info(f"🚀 优化版 Binance 自动交易启动")
        
        # 先获取初始余额
        self.get_balance()
        logger.info(f"💰 初始资金: {self.balance:.2f} USDT")
        logger.info(f"📊 杠杆: {TRADE_CONFIG['leverage']}x")
        logger.info(f"🎯 品种: {[s['symbol'] for s in TRADE_CONFIG['symbols']]}")
        logger.info("=" * 70)
        
        # 设置杠杆
        for s in TRADE_CONFIG['symbols']:
            self.set_leverage(s['symbol'], TRADE_CONFIG['leverage'])
        
        while True:
            try:
                # 更新余额
                self.get_balance()
                
                # 分析每个品种
                for s in TRADE_CONFIG['symbols']:
                    symbol = s['symbol']
                    
                    # 分析信号
                    signal, indicators, current_price = self.analyze_signal(symbol)
                    pos_info = self.get_position_info(symbol)
                    
                    current_size = pos_info['size']
                    current_signal = "LONG" if current_size > 0 else ("SHORT" if current_size < 0 else "HOLD")
                    
                    # 检查止损/止盈
                    should_close, close_reason = self.check_stop_conditions(
                        symbol, current_price, pos_info, indicators
                    )
                    
                    # 平仓逻辑
                    if should_close:
                        reason_map = {
                            "SL": "止损",
                            "TS": "移动止损",
                            "TP": "止盈"
                        }
                        logger.info(f"🛑 {symbol}: {reason_map.get(close_reason, close_reason)} 平仓")
                        self.close_position(symbol, current_signal, close_reason)
                        current_size = 0
                    
                    # 开仓逻辑
                    if signal != current_signal and current_size == 0:
                        if signal != "HOLD":
                            logger.info(f"🔄 {symbol}: 信号 {current_signal} -> {signal}")
                            
                            # 计算开仓数量 (使用实际余额和配置的较小值)
                            weight = s['weight']
                            leverage = TRADE_CONFIG['leverage']
                            
                            # 目标资金 = 配置的capital_usdt * 杠杆 * 权重
                            target_capital = TRADE_CONFIG['capital_usdt'] * leverage * weight
                            # 可用资金 = 实际余额 * 杠杆 * 权重
                            available_capital = self.balance * leverage * weight
                            
                            # 使用较小值，确保不超过实际余额
                            capital = min(target_capital, available_capital)
                            
                            if capital < 10:
                                logger.warning(f"  ⚠️ {symbol} 资金不足: {capital:.2f} USDT")
                                continue
                            
                            amount = capital / current_price
                            
                            # 确保不超过最大仓位限制
                            max_qty = s.get('max_qty', 999)
                            amount = min(amount, max_qty)
                            
                            # 确保最小数量（根据币种）
                            min_amount = {
                                'BTCUSDT': 0.001,
                                'ETHUSDT': 0.01,
                                'SOLUSDT': 0.1,
                            }.get(symbol, 0.01)
                            
                            # 向上取整到最小单位
                            amount = max(amount, min_amount)
                            
                            # 根据币种设置精度
                            precision = {
                                'BTCUSDT': 3,
                                'ETHUSDT': 3,
                                'SOLUSDT': 2,
                            }.get(symbol, 4)
                            
                            amount = round(amount, precision)
                            
                            # 初始化移动止损
                            if signal == "LONG":
                                self.trailing_high[symbol] = current_price
                            else:
                                self.trailing_low[symbol] = current_price
                            
                            self.open_position(symbol, signal, amount)
                    
                    # 更新信号
                    self.last_signals[symbol] = signal
                
                # 输出状态
                total_pnl = 0
                total_value = 0
                logger.info("-" * 70)
                for s in TRADE_CONFIG['symbols']:
                    symbol = s['symbol']
                    pos_info = self.get_position_info(symbol)
                    size = pos_info['size']
                    pnl = pos_info['pnl']
                    total_pnl += pnl
                    total_value += abs(size * pos_info['entry_price']) if size != 0 else 0
                    
                    signal = self.last_signals[symbol]
                    if size != 0:
                        logger.info(f"📊 {symbol}: {size:.4f} @ {pos_info['entry_price']:.2f} | PnL: {pnl:+.2f}")
                    else:
                        logger.info(f"📊 {symbol}: 无持仓 | 信号: {signal}")
                
                logger.info(f"💰 总PnL: {total_pnl:+.2f} USDT | 仓位: {total_value:.2f}")
                logger.info("-" * 70)
                
                # 等待下次检查
                time.sleep(TRADE_CONFIG['check_interval'])
                
            except KeyboardInterrupt:
                logger.info("🛑 手动停止交易")
                break
            except Exception as e:
                logger.error(f"错误: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(60)


def main():
    """主函数"""
    mode = "Testnet" if TESTNET else "实盘"
    logger.info(f"🚀 Binance 自动交易启动 ({mode})")
    
    trader = BinanceTrader(API_KEY, API_SECRET, testnet=TESTNET)
    trader.trading_loop()


if __name__ == "__main__":
    main()
