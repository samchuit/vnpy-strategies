#!/usr/bin/env python3
"""
K019 ML 扩大验证
测试更多品种，增加样本外验证
"""

import numpy as np
import pandas as pd
import os
import json
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from typing import Dict, List, Tuple

DATA_DIR = "/Users/chusungang/workspace/vnpy_strategy/data_minute"
RESULT_DIR = "/Users/chusungang/workspace/vnpy_strategy/result"
os.makedirs(RESULT_DIR, exist_ok=True)

# ===============================
# ML配置
# ===============================
ML_CONFIG = {
    # 模型参数
    "n_estimators": 50,
    "max_depth": 5,
    "test_size": 0.3,  # 30%作为测试集
    
    # 特征
    "features": ['ma5', 'ma10', 'ma20', 'ma60', 'obv', 'obv_ma5', 'atr', 'vol_ma5'],
    
    # 标签
    "forward_days": 5,
    "threshold": 0.005,
    
    # 验证参数
    "min_samples": 100,  # 最少样本数
    "min_trades": 5,  # 最少交易次数
}


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """准备特征"""
    df = df.copy()
    
    # 均线
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    
    # OBV
    obv = [0]
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['close'].iloc[i-1]:
            obv.append(obv[-1] + df['vol'].iloc[i])
        elif df['close'].iloc[i] < df['close'].iloc[i-1]:
            obv.append(obv[-1] - df['vol'].iloc[i])
        else:
            obv.append(obv[-1])
    df['obv'] = obv
    df['obv_ma5'] = df['obv'].rolling(5).mean()
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    
    # 成交量均线
    df['vol_ma5'] = df['vol'].rolling(5).mean()
    
    return df.dropna()


def create_labels(df: pd.DataFrame) -> pd.DataFrame:
    """创建标签"""
    df = df.copy()
    
    # 未来5天收益率
    df['future_return'] = df['close'].shift(-ML_CONFIG['forward_days']) / df['close'] - 1
    
    # 标签: 1=上涨, 0=震荡/下跌
    df['label'] = (df['future_return'] > ML_CONFIG['threshold']).astype(int)
    
    return df.dropna()


def train_and_test(df: pd.DataFrame, symbol: str) -> Dict:
    """训练并测试模型"""
    # 准备数据
    df = prepare_features(df)
    df = create_labels(df)
    
    if len(df) < ML_CONFIG['min_samples']:
        return None
    
    features = ML_CONFIG['features']
    X = df[features].values
    y = df['label'].values
    
    # 时序分割
    split = int(len(X) * (1 - ML_CONFIG['test_size']))
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    
    # 标准化
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # 训练模型
    model = RandomForestClassifier(
        n_estimators=ML_CONFIG['n_estimators'],
        max_depth=ML_CONFIG['max_depth'],
        random_state=42
    )
    model.fit(X_train_scaled, y_train)
    
    # 模型评估
    train_score = model.score(X_train_scaled, y_train)
    test_score = model.score(X_test_scaled, y_test)
    
    # 回测
    position = 0
    entry_price = 0
    returns = []
    
    for i in range(len(X_test_scaled)):
        if i >= len(y_test):
            break
        
        pred = model.predict([X_test_scaled[i]])[0]
        close_price = df['close'].iloc[split + i]
        
        if position == 0 and pred == 1:
            position = 1
            entry_price = close_price
        
        elif position == 1:
            ret = (close_price - entry_price) / entry_price
            # 5%止损
            if abs(ret) > 0.05:
                returns.append(ret)
                position = 0
    
    if len(returns) < ML_CONFIG['min_trades']:
        return None
    
    returns = np.array(returns)
    total_ret = (1 + returns).prod() - 1
    
    if len(returns) > 1 and returns.std() > 0:
        sharpe = returns.mean() / returns.std() * np.sqrt(252 * 4)
    else:
        sharpe = 0
    
    win_rate = (returns > 0).mean()
    
    return {
        'symbol': symbol,
        'train_accuracy': train_score,
        'test_accuracy': test_score,
        'total_return': total_ret,
        'sharpe': sharpe,
        'win_rate': win_rate,
        'trades': len(returns),
        'overfitting_risk': train_score - test_score  # 过拟合风险
    }


def run_expanded_validation():
    """运行扩大验证"""
    print("\n" + "=" * 70)
    print("🔬 K019 ML 扩大验证")
    print("=" * 70)
    
    # 获取所有60分钟数据
    all_files = [f.replace('_60.csv', '') for f in os.listdir(DATA_DIR) if f.endswith('_60.csv')]
    
    print(f"\n📂 发现 {len(all_files)} 个品种数据")
    
    # 加载并验证
    results = []
    failed = []
    
    for symbol in all_files:
        file_path = f"{DATA_DIR}/{symbol}_60.csv"
        
        try:
            df = pd.read_csv(file_path)
            result = train_and_test(df, symbol)
            
            if result:
                results.append(result)
                print(f"   ✅ {symbol}: 夏普={result['sharpe']:.2f}, 收益={result['total_return']*100:.1f}%, 测试准确率={result['test_accuracy']:.1%}")
            else:
                failed.append(symbol)
                print(f"   ❌ {symbol}: 样本不足")
                
        except Exception as e:
            failed.append(symbol)
            print(f"   ❌ {symbol}: {str(e)[:50]}")
    
    # 统计结果
    print("\n" + "=" * 70)
    print("📊 验证结果统计")
    print("=" * 70)
    
    if results:
        positive = sum(1 for r in results if r['total_return'] > 0)
        positive_sharpe = sum(1 for r in results if r['sharpe'] > 0)
        avg_sharpe = sum(r['sharpe'] for r in results) / len(results)
        avg_return = sum(r['total_return'] for r in results) / len(results)
        avg_overfit = sum(r['overfitting_risk'] for r in results) / len(results)
        
        print(f"\n总测试品种: {len(results)}")
        print(f"正收益: {positive}/{len(results)} ({positive/len(results)*100:.1f}%)")
        print(f"正夏普: {positive_sharpe}/{len(results)} ({positive_sharpe/len(results)*100:.1f}%)")
        print(f"平均收益: {avg_return*100:.1f}%")
        print(f"平均夏普: {avg_sharpe:.3f}")
        print(f"平均过拟合风险: {avg_overfit:.1%}")
        
        # 风险评估
        print(f"\n⚠️ 风险评估:")
        if avg_overfit > 0.15:
            print(f"   高过拟合风险 ({avg_overfit:.1%})")
            print(f"   建议: 增加正则化或减少模型复杂度")
        elif avg_overfit > 0.05:
            print(f"   中等过拟合风险 ({avg_overfit:.1%})")
            print(f"   建议: 模型表现正常，但需关注")
        else:
            print(f"   低过拟合风险 ({avg_overfit:.1%}) ✅")
            print(f"   建议: 模型表现稳健")
        
        # Top 5
        print(f"\n🏆 Top 5 品种:")
        top5 = sorted(results, key=lambda x: x['sharpe'], reverse=True)[:5]
        for i, r in enumerate(top5, 1):
            risk = "⚠️" if r['overfitting_risk'] > 0.15 else "✅"
            print(f"   {i}. {r['symbol']}: 夏普={r['sharpe']:.2f}, 收益={r['total_return']*100:.1f}% {risk}")
        
        # 避免品种
        print(f"\n🛑 需验证品种:")
        bottom3 = sorted(results, key=lambda x: x['sharpe'])[:3]
        for r in bottom3:
            if r['sharpe'] < 0:
                print(f"   ❌ {r['symbol']}: 夏普={r['sharpe']:.2f}")
        
        # 保存结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = f"{RESULT_DIR}/k019_ml_expanded_{timestamp}.json"
        
        with open(result_file, 'w') as f:
            json.dump({
                'config': ML_CONFIG,
                'results': results,
                'summary': {
                    'total': len(results),
                    'positive': positive,
                    'positive_sharpe': positive_sharpe,
                    'avg_sharpe': avg_sharpe,
                    'avg_return': avg_return,
                    'avg_overfitting_risk': avg_overfit,
                    'failed': failed
                }
            }, f, indent=2, default=str)
        
        print(f"\n💾 结果已保存: {result_file}")
        
    else:
        print("\n❌ 没有有效的验证结果")
    
    return results


def analyze_feature_importance():
    """分析特征重要性"""
    print("\n" + "=" * 70)
    print("📈 特征重要性分析")
    print("=" * 70)
    
    all_files = [f.replace('_60.csv', '') for f in os.listdir(DATA_DIR) if f.endswith('_60.csv')]
    
    feature_importance = {f: 0 for f in ML_CONFIG['features']}
    count = 0
    
    for symbol in all_files[:10]:  # 分析前10个
        file_path = f"{DATA_DIR}/{symbol}_60.csv"
        
        try:
            df = pd.read_csv(file_path)
            df = prepare_features(df)
            df = create_labels(df)
            
            if len(df) < ML_CONFIG['min_samples']:
                continue
            
            features = ML_CONFIG['features']
            X = df[features].values
            y = df['label'].values
            
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            
            model = RandomForestClassifier(
                n_estimators=ML_CONFIG['n_estimators'],
                max_depth=ML_CONFIG['max_depth'],
                random_state=42
            )
            model.fit(X_scaled, y)
            
            for i, f in enumerate(features):
                feature_importance[f] += model.feature_importances_[i]
            
            count += 1
            
        except Exception as e:
            continue
    
    if count > 0:
        print(f"\n分析 {count} 个品种...")
        print(f"\n特征重要性排名:")
        sorted_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)
        
        for i, (feat, imp) in enumerate(sorted_features, 1):
            bar = "█" * int(imp * 50)
            print(f"   {i}. {feat:12s}: {imp:.3f} {bar}")


def main():
    """主程序"""
    print("=" * 70)
    print("🔬 K019 ML 扩大验证")
    print("=" * 70)
    
    print(f"\n📋 验证内容:")
    print(f"   1. 测试所有60分钟数据 ({len(os.listdir(DATA_DIR))} 个品种)")
    print(f"   2. 70%训练 / 30%测试")
    print(f"   3. 时序交叉验证")
    print(f"   4. 过拟合风险评估")
    
    # 运行验证
    results = run_expanded_validation()
    
    # 特征重要性
    analyze_feature_importance()
    
    return results


if __name__ == "__main__":
    main()
