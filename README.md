# VNPY期货策略库

## 概述
基于Python的期货交易策略库，包含多种策略的回测代码。

## 📁 文件结构

```
vnpy-strategies/
├── README.md                     # 总说明
├── k019_simple.md               # K019策略介绍
├── k019_ml_quick.md             # ML增强版介绍
├── backtest_60min_real.md        # 60分钟回测介绍
├── all_strategies_comparison.md  # 策略对比介绍
│
├── k019_simple.py                # K019策略代码
├── k019_ml_quick.py            # ML增强版代码
├── backtest_60min_real.py       # 60分钟回测代码
├── all_strategies_comparison.py  # 策略对比代码
├── sync.sh                      # Git同步脚本
│
└── data_minute/                 # 60分钟数据目录
    └── *_60.csv
```

## 策略列表

### 1. K019 Simple
- 均线 + OBV + 动态止损止盈
- 文档: [k019_simple.md](k019_simple.md)

### 2. K019 ML Quick
- ML增强版K019策略 (RandomForest)
- 文档: [k019_ml_quick.md](k019_ml_quick.md)

### 3. Range Trading ⭐ (最佳)
- 区间突破策略，基于ATR
- 文档: [all_strategies_comparison.md](all_strategies_comparison.md)

### 4. Momentum
- 动量策略，追涨杀跌
- 文档: [all_strategies_comparison.md](all_strategies_comparison.md)

## 回测结果

| 策略 | 正夏普率 | 平均夏普 | 适合人群 |
|------|----------|----------|----------|
| Range Trading | 84.2% | 6.776 | 稳健型 |
| K019 Trend | 47.4% | 0.455 | 平衡型 |
| Momentum | 52.6% | -0.254 | 激进型 |

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/samchuit/vnpy-strategies.git
cd vnpy-strategies

# 2. 安装依赖
pip install pandas numpy scikit-learn

# 3. 运行回测
python k019_simple.py           # K019策略
python k019_ml_quick.py         # ML增强版
python backtest_60min_real.py   # 60分钟回测
python all_strategies_comparison.py  # 所有策略对比

# 4. 查看结果
cat result/*.json
```

## Git同步

```bash
# 同步到GitHub
./sync.sh

# 或手动操作
git add -A
git commit -m "更新说明"
git push origin main
```

## 作者
Sam

## License
MIT
