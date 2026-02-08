# VNPY期货策略库

## 概述
基于Python的期货交易策略库，包含多种策略的回测代码。

## 策略列表

### 1. K019 Simple
- 均线 + OBV + 动态止损止盈
- 适用于日线和60分钟K线

### 2. K019 ML Quick
- ML增强版K019策略
- 使用RandomForest分类器

### 3. Range Trading
- 区间突破策略
- 基于ATR和MA20

### 4. Momentum
- 动量策略
- 追涨杀跌

## 使用方法

```bash
# 安装依赖
pip install pandas numpy scikit-learn

# 运行回测
python k019_simple.py
python all_strategies_comparison.py
```

## 回测结果

| 策略 | 正夏普率 | 平均夏普 |
|------|----------|----------|
| Range Trading | 84.2% | 6.776 |
| K019 Trend | 47.4% | 0.455 |

## 作者
Sam

## License
MIT
