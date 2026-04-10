import pandas as pd
import numpy as np

# ==========================================
# 核心底层引擎：动态连续斜率反推
# ==========================================
def _calculate_continuous_strength(closes, end_idx, direction):
    """
    从给定的结束点 (end_idx) 开始，不断增加窗口向历史K线反推。
    只要线性回归斜率的方向保持不变，就继续往回追溯。
    一旦斜率断裂（变号），立刻停止，返回能达到的最大K线连续数。
    """
    # 至少需要有3根K线的数据才能算起始斜率
    if end_idx < 2:
        return 0
        
    strength = 0
    # 最大可以反推到索引为 0 的那根K线
    max_possible_n = end_idx + 1 
    
    for n in range(3, max_possible_n + 1):
        start_idx = end_idx - n + 1
        y_slice = closes[start_idx : end_idx + 1]
        
        # 使用 numpy 的 polyfit 进行快速一元线性回归求斜率
        x = np.arange(n)
        slope = np.polyfit(x, y_slice, 1)[0]
        
        if direction == 'up' and slope > 0:
            strength = n
        elif direction == 'down' and slope < 0:
            strength = n
        else:
            # 关键：一旦斜率方向被破坏，说明趋势起点到此为止，立即跳出
            break
            
    return strength


# ==========================================
# 2B 模型
# ==========================================
def _2b(df):
    """
    【无上限反推版】2B 2K 模型
    彻底移除固定周期参数。只要发生吞没，就反向测算真实趋势强度。
    """
    if df is None or len(df) < 2:
        return df

    df = df.copy()

    if "signal" not in df.columns:
        df["signal"] = 0
    if "pattern" not in df.columns:
        df["pattern"] = "none"
    if "trend_strength" not in df.columns:
        df["trend_strength"] = 0

    body_high = df[['open', 'close']].max(axis=1)
    body_low  = df[['open', 'close']].min(axis=1)

    prev_body_high = body_high.shift(1)
    prev_body_low  = body_low.shift(1)

    is_bear      = df['close'] < df['open']
    is_bull      = df['close'] > df['open']
    prev_is_bull = df['close'].shift(1) > df['open'].shift(1)
    prev_is_bear = df['close'].shift(1) < df['open'].shift(1)

    # 基础吞没条件
    bear_engulf = is_bear & prev_is_bull & (body_high >= prev_body_high) & (body_low <= prev_body_low)
    bull_engulf = is_bull & prev_is_bear & (body_high >= prev_body_high) & (body_low <= prev_body_low)

    closes = df['close'].values
    
    # 找到所有发生吞没的索引位置
    bear_indices = np.where(bear_engulf)[0]
    bull_indices = np.where(bull_engulf)[0]

    # 遍历做空信号（阴包阳），测量其吞没前（前一根K线）的上涨趋势强度
    for idx in bear_indices:
        if idx >= 1:
            # 以被吞没的K线 (idx - 1) 为终点，向上反推
            strength = _calculate_continuous_strength(closes, idx - 1, 'up')
            # 只要强度存在（>0），我们就记录它
            if strength > 0:
                df.iloc[idx, df.columns.get_loc('signal')] = -100
                df.iloc[idx, df.columns.get_loc('pattern')] = '2B'
                df.iloc[idx, df.columns.get_loc('trend_strength')] = strength

    # 遍历做多信号（阳包阴），测量其吞没前（前一根K线）的下跌趋势强度
    for idx in bull_indices:
        if idx >= 1:
            # 以被吞没的K线 (idx - 1) 为终点，向下反推
            strength = _calculate_continuous_strength(closes, idx - 1, 'down')
            if strength > 0:
                df.iloc[idx, df.columns.get_loc('signal')] = 100
                df.iloc[idx, df.columns.get_loc('pattern')] = '2B'
                df.iloc[idx, df.columns.get_loc('trend_strength')] = strength

    return df


# ==========================================
# 顶底分型 (Fractals) 模型
# ==========================================
def _fractal(df):
    """
    【无上限反推版】顶底分型模型
    彻底移除固定周期参数。
    """
    if df is None or len(df) < 3:
        return df

    df = df.copy()

    if "signal" not in df.columns:
        df["signal"] = 0
    if "pattern" not in df.columns:
        df["pattern"] = "none"
    if "trend_strength" not in df.columns:
        df["trend_strength"] = 0

    h1, l1, o1 = df['high'].shift(2), df['low'].shift(2), df['open'].shift(2)
    h2, l2     = df['high'].shift(1), df['low'].shift(1)
    h3, l3, o3, c3 = df['high'],      df['low'],          df['open'],          df['close']

    # 基础分型条件
    short_cond_base = (h2 > h1) & (h2 > h3) & (l2 >= l1) & (l2 >= l3) & (c3 < o3)
    long_cond_base  = (l2 < l1) & (l2 < l3) & (h2 <= h1) & (h2 <= h3) & (c3 > o3)

    closes = df['close'].values
    
    short_indices = np.where(short_cond_base)[0]
    long_indices  = np.where(long_cond_base)[0]

    # 顶分型做空，测算左边K线之前的上涨趋势
    for idx in short_indices:
        if idx >= 2:
            # 左边K线的索引是 idx - 2
            strength = _calculate_continuous_strength(closes, idx - 2, 'up')
            if strength > 0:
                df.iloc[idx, df.columns.get_loc('signal')] = -100
                df.iloc[idx, df.columns.get_loc('pattern')] = 'Fractal'
                df.iloc[idx, df.columns.get_loc('trend_strength')] = strength

    # 底分型做多，测算左边K线之前的下跌趋势
    for idx in long_indices:
        if idx >= 2:
            strength = _calculate_continuous_strength(closes, idx - 2, 'down')
            if strength > 0:
                df.iloc[idx, df.columns.get_loc('signal')] = 100
                df.iloc[idx, df.columns.get_loc('pattern')] = 'Fractal'
                df.iloc[idx, df.columns.get_loc('trend_strength')] = strength

    return df


# ==========================================
# 测试入口
# ==========================================
if __name__ == "__main__":
    from config import console
    from mt5 import connect_mt5, get_m5_klines, plot_klines, save_chart

    console.print("[bold cyan]===== patterns 测试 (极限反推版) =====[/bold cyan]")

    if not connect_mt5():
        console.print("[red]❌ MT5连接失败[/red]")
    else:
        # 可以大胆取更多数据，因为现在没有20的上限了
        _, df = get_m5_klines(count=100)

        if df is None or df.empty:
            console.print("[red]❌ 获取K线失败[/red]")
        else:
            console.print(f"获取K线: {len(df)}根")

            df_result = _2b(df.copy())
            df_result = _fractal(df_result)

            # 获取所有存在信号的行
            sigs = df_result[df_result['signal'] != 0].copy()
            
            console.print(f"\n捕获的所有形态总数: {len(sigs)}个")
            if not sigs.empty:
                # 为了显示清晰，我们可以在这里由策略层来决定过滤条件。
                # 比如：我们只看趋势强度 >= 6 的极高含金量信号
                high_quality_sigs = sigs[sigs['trend_strength'] >= 6]
                
                console.print(f"\n[green]其中强度 >= 6 的高质量信号有 {len(high_quality_sigs)} 个：[/green]")
                console.print(high_quality_sigs[['time', 'signal', 'pattern', 'trend_strength']].to_string())

            # 保存一张结果图
            fig = plot_klines(df_result, title="2B + Fractal 信号图 (极限反推版)")
            save_chart(fig, title="2B_Fractal")