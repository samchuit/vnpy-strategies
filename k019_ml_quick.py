#!/usr/bin/env python3
"""
K019 ML简化版 - 快速对比
"""

import numpy as np
import pandas as pd
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

DATA_DIR = "/Users/chusungang/workspace/vnpy_strategy/data"
RESULT_DIR = "/Users/chusungang/workspace/vnpy_strategy/result"
os.makedirs(RESULT_DIR, exist_ok=True)


def prepare_features(df):
    """准备特征"""
    if df is None or len(df) < 100:
        return None
    
    df = df.copy()
    
    # 统一日期列
    for col in ['datetime', 'trade_date', 'date']:
        if col in df.columns:
            df['date'] = df[col].astype(str)
            break
    
    if 'close' not in df.columns:
        return None
    
    # 基础特征
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    df['vol_ma5'] = df['vol'].rolling(5).mean() if 'vol' in df.columns else df['close'].rolling(5).mean()
    
    # OBV
    obv = [0]
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['close'].iloc[i-1]:
            obv.append(obv[-1] + df['vol'].iloc[i] if 'vol' in df.columns else obv[-1] + 1)
        elif df['close'].iloc[i] < df['close'].iloc[i-1]:
            obv.append(obv[-1] - df['vol'].iloc[i] if 'vol' in df.columns else obv[-1] - 1)
        else:
            obv.append(obv[-1])
    df['obv'] = obv
    df['obv_ma'] = df['obv'].rolling(5).mean()
    
    return df.dropna()


def run_ml_backtest(df):
    """ML版回测"""
    df = prepare_features(df)
    if df is None or len(df) < 100:
        return None
    
    # 标签：未来5天涨跌
    df['return'] = df['close'].shift(-5) / df['close'] - 1
    df['label'] = (df['return'] > 0).astype(int)
    
    # 特征
    features = ['ma5', 'ma20', 'ma60', 'vol_ma5', 'obv', 'obv_ma']
    X = df[features].values
    y = df['label'].values
    
    # 训练/测试分割
    split = int(len(X) * 0.7)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    
    # 训练模型
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    model = RandomForestClassifier(n_estimators=20, max_depth=5, random_state=42)
    model.fit(X_train_scaled, y_train)
    
    # 回测
    position = 0
    entry_price = 0
    returns = []
    
    for i in range(50, len(df) - 5):
        if i >= len(X_test_scaled):
            break
        
        pred = model.predict([X_test_scaled[i - len(X_test_scaled)]])[0]
        close = df['close'].iloc[i + split]
        
        if position == 0 and pred == 1:
            position = 1
            entry_price = close
        elif position == 1:
            ret = (close - entry_price) / entry_price
            if abs(ret) > 0.05:  # 5%止损
                returns.append(ret)
                position = 0
    
    if not returns:
        return None
    
    returns = np.array(returns)
    total = (1 + returns).prod() - 1
    sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
    
    return {'sharpe': sharpe, 'total': total}


def main():
    """主程序"""
    print("="*60)
    print("K019 ML简化版")
    print("="*60)
    
    results = []
    for f in os.listdir(DATA_DIR)[:20]:  # 只测20个
        if f.endswith('.csv'):
            symbol = f.replace('.csv', '')
            df = pd.read_csv(f"{DATA_DIR}/{f}")
            
            result = run_ml_backtest(df)
            if result:
                result['symbol'] = symbol
                results.append(result)
                print(f"{symbol}: 夏普={result['sharpe']:.2f}, 收益={result['total']*100:.1f}%")
    
    positive = [r for r in results if r['total'] > 0]
    print(f"\n正收益: {len(positive)}/{len(results)}")
    
    with open(f"{RESULT_DIR}/k019_ml_quick_result.json", 'w') as f:
        import json
        json.dump(results, f, indent=2)
    
    print(f"\n结果已保存")


if __name__ == "__main__":
    main()
