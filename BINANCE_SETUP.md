# Binance 自动交易设置指南

## 📋 步骤

### 1. 注册 Binance Futures Testnet

1. 访问: https://testnet.binancefuture.com
2. 注册账号
3. 登录后进入 "API Management"

### 2. 创建 API 密钥

1. 点击 "Create API Key"
2. 填写名称 (例如: "OpenClawTrader")
3. 勾选权限:
   - ✅ Trade
   - ✅ Position
4. 保存 **API Key** 和 **Secret Key**

### 3. 配置脚本

编辑 `binance_trader.py`:

```python
API_KEY = "你的API Key"
API_SECRET = "你的Secret Key"
```

### 4. 运行模拟交易 (推荐)

```bash
conda activate vnpy
cd /Users/chusungang/workspace/vnpy-strategies
python binance_sim.py
```

### 5. 运行实盘交易

```bash
python binance_trader.py
```

---

## 💰 资金分配

| 品种 | 权重 | 金额 (CNY) |
|------|------|------------|
| BTC | 50% | ¥5,000 |
| ETH | 30% | ¥3,000 |
| SOL | 20% | ¥2,000 |
| **合计** | 100% | **¥10,000** |

---

## 🎛️ 策略参数

| 参数 | 值 |
|------|-----|
| MA快线 | 10 |
| MA慢线 | 20 |
| MA趋势 | 90 |
| 止损 | 2% |
| 止盈 | 8% |
| 杠杆 | 2x |
| 周期 | 4小时 |

---

## ⚠️ 风险提示

1. **只用 Testnet 测试** - 熟悉后再切换实盘
2. **设置止损** - 永远不要让单笔亏损超过 2%
3. **小仓位开始** - 建议先用 ¥1000 验证
4. **监控运行** - 首次运行请密切关注

---

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| `binance_trader.py` | 实盘交易脚本 (需要API密钥) |
| `binance_sim.py` | 模拟交易 (无需API密钥) |
| `result/crypto/sim_trade_*.json` | 模拟结果 |

---

## 🚀 快速开始

```bash
# 1. 运行模拟
python binance_sim.py

# 2. 配置API密钥
# 编辑 binance_trader.py

# 3. 测试网运行
python binance_trader.py

# 4. 确认无误后切换实盘
# 修改 binance_trader.py 中的 testnet=False
```
