#!/usr/bin/env python3
"""
Binance 实盘监控与汇报系统
每4小时汇报运行情况
"""

import sys
import os
import json
import logging
from datetime import datetime
from binance_config import API_KEY, API_SECRET, TESTNET
from binance import Client

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_positions():
    """获取所有持仓"""
    client = Client(API_KEY, API_SECRET, testnet=False)
    
    positions = []
    total_pnl = 0
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    
    for symbol in symbols:
        try:
            info = client.futures_position_information(symbol=symbol)
            for p in info:
                if float(p['positionAmt']) != 0:
                    entry_price = float(p['entryPrice'])
                    mark_price = float(client.futures_ticker(symbol=symbol)['markPrice'])
                    pnl = float(p['unRealizedProfit'])
                    size = abs(float(p['positionAmt']))
                    
                    pnl_pct = (mark_price - entry_price) / entry_price * 100 if entry_price > 0 else 0
                    
                    positions.append({
                        'symbol': symbol,
                        'size': size,
                        'entry_price': entry_price,
                        'mark_price': mark_price,
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                    })
                    
                    total_pnl += pnl
                    
        except Exception as e:
            logger.error(f"获取{symbol}持仓失败: {e}")
    
    return positions, total_pnl


def get_account_info():
    """获取账户信息"""
    client = Client(API_KEY, API_SECRET, testnet=False)
    
    try:
        balance = client.futures_account_balance()
        for b in balance:
            if b['asset'] == 'USDT':
                return float(b['balance']), float(b['availableBalance'])
    except Exception as e:
        logger.error(f"获取账户信息失败: {e}")
    
    return 0, 0


def get_market_status():
    """获取市场状态"""
    client = Client(API_KEY, API_SECRET, testnet=False)
    
    market_info = {}
    
    for symbol in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
        try:
            ticker = client.futures_ticker(symbol=symbol)
            klines = client.futures_klines(symbol=symbol, interval='4h', limit=50)
            
            # 计算MA
            closes = [float(k[4]) for k in klines]
            ma10 = sum(closes[-10:]) / 10
            ma20 = sum(closes[-20:]) / 20
            ma90 = sum(closes[-90:]) / 90 if len(closes) >= 90 else ma20
            
            current_price = float(ticker['lastPrice'])
            
            # 判断趋势
            in_uptrend = current_price > ma90 and ma20 > ma90
            
            market_info[symbol] = {
                'price': current_price,
                'ma10': ma10,
                'ma20': ma20,
                'ma90': ma90,
                'in_uptrend': in_uptrend,
                '24h_change': float(ticker['priceChangePercent']),
            }
            
        except Exception as e:
            logger.error(f"获取{symbol}市场信息失败: {e}")
    
    return market_info


def generate_report():
    """生成汇报报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    balance, available = get_account_info()
    positions, total_pnl = get_positions()
    market = get_market_status()
    
    # 生成报告
    report = {
        'report_time': now,
        'account': {
            'balance': balance,
            'available': available,
            'total_pnl': total_pnl,
        },
        'positions': positions,
        'market': market,
    }
    
    # 打印报告
    print()
    print("=" * 70)
    print(f"📊 Binance 实盘运行报告 - {now}")
    print("=" * 70)
    
    print()
    print("💰 账户状态:")
    print(f"   总资产: {balance:.2f} USDT ({balance*7.2:.0f} CNY)")
    print(f"   可用资金: {available:.2f} USDT")
    print(f"   总浮动盈亏: {total_pnl:.2f} USDT")
    
    print()
    print("💼 当前持仓:")
    if positions:
        for p in positions:
            pnl_emoji = "🟢" if p['pnl'] > 0 else "🔴"
            print(f"   {pnl_emoji} {p['symbol']}: {p['size']:.4f} @ {p['entry_price']:.2f}")
            print(f"      当前: {p['mark_price']:.2f}, PnL: {p['pnl']:.2f} ({p['pnl_pct']:+.2f}%)")
    else:
        print("   无持仓")
    
    print()
    print("📈 市场状态 (4小时周期):")
    for symbol, info in market.items():
        trend_emoji = "🟢" if info['in_uptrend'] else "🔴"
        print(f"   {trend_emoji} {symbol}: {info['price']:.2f}")
        print(f"      MA10: {info['ma10']:.2f}, MA20: {info['ma20']:.2f}, MA90: {info['ma90']:.2f}")
        print(f"      24h涨跌: {info['24h_change']:+.2f}%, 趋势: {'多头' if info['in_uptrend'] else '空头'}")
    
    print()
    print("=" * 70)
    
    # 保存报告
    report_path = "/Users/chusungang/workspace/vnpy-strategies/result/crypto"
    os.makedirs(report_path, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d_%H")
    json_path = f"{report_path}/daily_report_{date_str}.json"
    
    with open(json_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"💾 报告已保存: {json_path}")
    
    return report


def check_anomalies(report):
    """检查异常"""
    anomalies = []
    
    # 检查大额亏损
    for p in report['positions']:
        if p['pnl_pct'] < -5:
            anomalies.append({
                'type': 'LARGE_LOSS',
                'symbol': p['symbol'],
                'pnl_pct': p['pnl_pct'],
                'message': f"{p['symbol']}亏损超过5%: {p['pnl_pct']:.2f}%"
            })
    
    # 检查余额异常
    if report['account']['balance'] < 100:
        anomalies.append({
            'type': 'LOW_BALANCE',
            'balance': report['account']['balance'],
            'message': f"余额过低: {report['account']['balance']:.2f} USDT"
        })
    
    return anomalies


def main():
    """主函数"""
    print("📊 生成运行报告...")
    
    report = generate_report()
    
    # 检查异常
    anomalies = check_anomalies(report)
    
    if anomalies:
        print()
        print("⚠️ 发现异常:")
        for a in anomalies:
            print(f"   ❌ {a['message']}")
    else:
        print()
        print("✅ 无异常")
    
    return report, anomalies


if __name__ == "__main__":
    import os
    main()
