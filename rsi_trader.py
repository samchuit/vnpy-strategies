#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSI + ATR止损策略 - 期货合约交易
📊 策略参数:
  - RSI(6), oversold=30, overbought=70
  - ATR(14) 2.5倍止损
  - 2倍杠杆, 单品种30%仓位
  - 只在15分钟K线收盘时操作

🔧 配置说明:
  复制本文件为 binance_config.py，并填入你的API密钥:
  
  API_KEY = "your_api_key"
  API_SECRET = "your_api_secret"
  TESTNET = False  # False=实盘, True=测试网
"""

import os
import sys
import time
import hmac
import logging
import requests
import urllib3
import psutil
from datetime import datetime
from typing import Dict, List

# 导入配置（确保已创建binance_config.py）
try:
    from binance_config import API_KEY, API_SECRET, TESTNET
except ImportError:
    print("⚠️  请创建 binance_config.py 文件并填入API密钥")
    print("📄 参考: https://github.com/samchuit/vnpy-strategies/blob/main/binance_config_example.py")
    sys.exit(1)

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============== 策略参数 ==============
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
LEVERAGE = 2  # Binance期货只支持整数杠杆
POSITION_PCT = 0.3  # 单品种30%仓位
RSI_PERIOD = 6
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
ATR_PERIOD = 14
ATR_MULT = 2.5  # ATR止损倍数
FEE = 0.0005  # Taker手续费
KLINE_INTERVAL = 15  # 15分钟K线
CHECK_INTERVAL = 300  # 5分钟检查一次

# 各品种数量精度
QTY_PRECISION = {
    'BTCUSDT': 3,
    'ETHUSDT': 3,
    'SOLUSDT': 2,
}

# 期货API
if TESTNET:
    BASE_URL = "https://testnet.binancefuture.com"
else:
    BASE_URL = "https://fapi.binance.com"

# 日志配置
LOG_FILE = '/Users/chusungang/workspace/vnpy-strategies/rsi_trader.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_server_time():
    """获取服务器时间"""
    try:
        resp = requests.get(f"{BASE_URL}/fapi/v1/time", timeout=5)
        if resp.status_code == 200:
            return resp.json()['serverTime']
    except Exception as e:
        logger.error(f"获取服务器时间失败: {e}")
    return None


def get_klines(symbol: str, interval: str = '15m', limit: int = 100) -> List:
    """获取K线数据"""
    for _ in range(3):
        try:
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            resp = requests.get(f"{BASE_URL}/fapi/v1/klines", params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"获取{symbol} K线失败: {e}")
            time.sleep(1)
    return []


def calculate_rsi(prices: List, period: int = 6) -> float:
    """计算RSI"""
    if len(prices) < period + 1:
        return 50.0
    
    delta = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gain = [d if d > 0 else 0 for d in delta]
    loss = [-d if d < 0 else 0 for d in delta]
    
    avg_gain = sum(gain[-period:]) / period
    avg_loss = sum(loss[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_atr(highs: List, lows: List, closes: List, period: int = 14) -> float:
    """计算ATR"""
    if len(highs) < period + 1:
        return 0.0
    
    tr = []
    for i in range(1, len(highs)):
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        ))
    
    atr = sum(tr[-period:]) / period
    return atr


def get_market_data(symbol: str) -> Dict:
    """获取市场数据"""
    klines = get_klines(symbol, '15m', 50)
    if not klines:
        return None
    
    opens = [float(k[1]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    closes = [float(k[4]) for k in klines]
    
    closes_20 = closes[-20:]
    closes_60 = closes[-60:]
    
    ma20 = sum(closes_20) / len(closes_20)
    ma60 = sum(closes_60) / len(closes_60)
    
    trend = "多" if closes[-1] > ma20 else "空"
    
    rsi = calculate_rsi(closes, RSI_PERIOD)
    atr = calculate_atr(highs, lows, closes, ATR_PERIOD)
    
    return {
        'price': closes[-1],
        'rsi': rsi,
        'atr': atr,
        'atr_pct': atr / closes[-1] * 100,
        'sl_price': closes[-1] - ATR_MULT * atr,
        'ma20': ma20,
        'ma60': ma60,
        'trend': trend,
    }


def get_signal(rsi: float) -> str:
    """生成信号"""
    if rsi < RSI_OVERSOLD:
        return "🟢 LONG"
    elif rsi > RSI_OVERBOUGHT:
        return "🔴 CLOSE"
    return "🟡 HOLD"


class BinanceClient:
    def __init__(self):
        self.api_key = API_KEY
        self.api_secret = API_SECRET
        self.time_offset = 0
        self.session = requests.Session()
        self.session.trust_env = False
        self._sync_time()
    
    def _sync_time(self):
        """同步服务器时间"""
        server_time = get_server_time()
        if server_time:
            self.time_offset = server_time - int(time.time() * 1000)
    
    def _sign(self, params: Dict) -> str:
        """生成签名"""
        query = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
        return hmac.new(
            self.api_secret.encode(),
            query.encode(),
            'sha256'
        ).hexdigest()
    
    def _request(self, method: str, endpoint: str, params: Dict = None) -> Dict:
        """发送请求"""
        headers = {'X-MBX-APIKEY': self.api_key}
        
        ts = int(time.time() * 1000) + self.time_offset
        
        if params:
            params['timestamp'] = ts
        else:
            params = {'timestamp': ts}
        
        params['signature'] = self._sign(params)
        
        try:
            if method == 'GET':
                resp = self.session.get(
                    f"{BASE_URL}{endpoint}",
                    params=params,
                    headers=headers,
                    timeout=10
                )
            else:
                resp = self.session.post(
                    f"{BASE_URL}{endpoint}",
                    params=params,
                    headers=headers,
                    timeout=10
                )
            
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error(f"API错误: {resp.text}")
                return {}
        except Exception as e:
            logger.error(f"请求异常: {e}")
            return {}
    
    def balance(self) -> float:
        """获取账户余额"""
        data = self._request('GET', '/fapi/v2/balance')
        for item in data:
            if item['asset'] == 'USDT':
                return float(item['balance'])
        return 0.0
    
    def position(self, symbol: str) -> Dict:
        """获取持仓"""
        data = self._request('GET', '/fapi/v2/positionRisk', {'symbol': symbol})
        if data:
            return {
                'amt': float(data[0]['positionAmt']),
                'entry': float(data[0]['entryPrice']),
                'pnl': float(data[0]['unRealizedProfit']),
                'liq': float(data[0]['liquidationPrice']),
            }
        return {'amt': 0, 'entry': 0, 'pnl': 0, 'liq': 0}
    
    def leverage(self, symbol: str, lev: int):
        """设置杠杆"""
        self._request('POST', '/fapi/v1/leverage', {
            'symbol': symbol,
            'leverage': lev
        })
    
    def buy_market(self, symbol: str, qty: float) -> Dict:
        """市价买入"""
        return self._request('POST', '/fapi/v1/order', {
            'symbol': symbol,
            'side': 'BUY',
            'type': 'MARKET',
            'quantity': f"{qty:.}"
        })
    
    def sell_market(self, symbol: str, qty: float) -> Dict:
        """市价卖出"""
        return self._request('POST', '/fapi/v1/order', {
            'symbol': symbol,
            'side': 'SELL',
            'type': 'MARKET',
            'quantity': f"{qty:.}"
        })
    
    def set_sl(self, symbol: str, qty: float, sl_price: float):
        """设置止损单"""
        self._request('POST', '/fapi/v1/order', {
            'symbol': symbol,
            'side': 'SELL',
            'type': 'STOP_MARKET',
            'quantity': f"{qty:.}",
            'stopPrice': f"{sl_price:.}",
            'reduceOnly': 'true'
        })


def main():
    """主函数"""
    logger.info("="*60)
    logger.info("🚀 RSI策略启动")
    logger.info(f"📊 参数: RSI({RSI_PERIOD}), oversold={RSI_OVERSOLD}, overbought={RSI_OVERBOUGHT}")
    logger.info(f"📉 止损: ATR({ATR_PERIOD})×{ATR_MULT}")
    logger.info("="*60)
    
    client = BinanceClient()
    
    while True:
        try:
            balance = client.balance()
            logger.info(f"\n💰 余额: {balance:.2f} USDT")
            
            for symbol in SYMBOLS:
                md = get_market_data(symbol)
                if not md:
                    continue
                
                pos = client.position(symbol)
                signal = get_signal(md['rsi'])
                
                logger.info(f"{symbol}: 价格={md['price']:.2f}, RSI={md['rsi']:.1f}, "
                           f"ATR%={md['atr_pct']:.1f}%, 信号={signal}, 持仓={pos['amt']}")
                
                # 开仓
                if pos['amt'] == 0 and signal == "🟢 LONG":
                    precision = QTY_PRECISION.get(symbol, 3)
                    tradable = balance * POSITION_PCT * 0.8
                    qty = round(tradable * LEVERAGE / md['price'], precision)
                    
                    if qty > 0:
                        logger.info(f"🟢 {symbol} 开多: qty={qty}")
                        client.leverage(symbol, LEVERAGE)
                        client.buy_market(symbol, qty)
                        client.set_sl(symbol, qty, md['sl_price'])
                
                # 平仓
                elif pos['amt'] > 0 and signal == "🔴 CLOSE":
                    logger.info(f"🔴 {symbol} 平多: pnl={pos['pnl']:.2f}")
                    client.sell_market(symbol, pos['amt'])
            
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("\n🛑 策略已停止")
            break
        except Exception as e:
            logger.error(f"异常: {e}")
            time.sleep(60)


if __name__ == '__main__':
    main()
