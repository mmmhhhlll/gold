import numpy as np
import pandas as pd
import pandas_ta as ta
from scipy.signal import find_peaks
from mt5 import *

def _get_sr(df, num_bins=50, prominence_factor=0.15):
    """返回距离当前价格最近的支撑和阻力"""
    temp_df = df.copy()
    temp_df['typical_price'] = (temp_df['high'] + temp_df['low'] + temp_df['close']) / 3
    price_bins = np.linspace(temp_df['low'].min(), temp_df['high'].max(), num_bins)

    temp_df['price_bin'] = pd.cut(temp_df['typical_price'], bins=price_bins)
    vp_df = temp_df.groupby('price_bin', observed=False)['tick_volume'].sum().reset_index()

    vp_df['price'] = vp_df['price_bin'].apply(
        lambda x: x.mid if pd.notnull(x) else np.nan
    ).astype(float)
    vp_df['tick_volume'] = vp_df['tick_volume'].fillna(0)

    max_vol = vp_df['tick_volume'].max()
    prominence = max_vol * prominence_factor if max_vol > 0 else 0

    peaks, _ = find_peaks(vp_df['tick_volume'], prominence=prominence)
    all_sr_levels = vp_df.iloc[peaks]['price'].tolist()

    current_price = temp_df['close'].iloc[-1]
    supports    = sorted([l for l in all_sr_levels if l < current_price])
    resistances = sorted([l for l in all_sr_levels if l > current_price])

    return (
        current_price,
        max(supports)    if supports    else np.nan,
        min(resistances) if resistances else np.nan,
    )
def get_sr_zone(df_5m, df_15m, df_1h, tolerance_pct=0.002):
    """
    多周期共振检测，新增三周期共振强度标记
    返回 support_zone, resistance_zone, support_strength, resistance_strength
    strength: 'strong'(三周期共振) / 'normal'(两周期共振) / None
    """
    _,         sup_1h,  res_1h  = _get_sr(df_1h,  num_bins=50, prominence_factor=0.15)
    _,         sup_15m, res_15m = _get_sr(df_15m, num_bins=50, prominence_factor=0.12)
    current_px, sup_5m, res_5m  = _get_sr(df_5m,  num_bins=50, prominence_factor=0.10)

    def is_resonant(p1, p2):
        if pd.isna(p1) or pd.isna(p2):
            return False
        avg = (p1 + p2) / 2
        return abs(p1 - p2) / avg <= tolerance_pct

    # ==========================================
    # 支撑共振判断（三级强度）
    # ==========================================
    strong_support_zone = None
    support_strength = None

    # 最强：三周期共振
    if is_resonant(sup_5m, sup_15m) and is_resonant(sup_15m, sup_1h):
        levels = [sup_5m, sup_15m, sup_1h]
        strong_support_zone = (min(levels), max(levels))
        support_strength = 'strong'

    # 次强：5m + 1h 共振
    elif is_resonant(sup_5m, sup_1h):
        strong_support_zone = (min(sup_5m, sup_1h), max(sup_5m, sup_1h))
        support_strength = 'normal'

    # 普通：5m + 15m 共振
    elif is_resonant(sup_5m, sup_15m):
        strong_support_zone = (min(sup_5m, sup_15m), max(sup_5m, sup_15m))
        support_strength = 'normal'

    # ==========================================
    # 阻力共振判断（三级强度）
    # ==========================================
    strong_res_zone = None
    res_strength = None

    if is_resonant(res_5m, res_15m) and is_resonant(res_15m, res_1h):
        levels = [res_5m, res_15m, res_1h]
        strong_res_zone = (min(levels), max(levels))
        res_strength = 'strong'

    elif is_resonant(res_5m, res_1h):
        strong_res_zone = (min(res_5m, res_1h), max(res_5m, res_1h))
        res_strength = 'normal'

    elif is_resonant(res_5m, res_15m):
        strong_res_zone = (min(res_5m, res_15m), max(res_5m, res_15m))
        res_strength = 'normal'

    return strong_support_zone, strong_res_zone, support_strength, res_strength
def get_sr_line(df_5m, df_15m, df_1h, tolerance_pct=0.005):
    """
    返回支撑阻力区间和强度，保留区间而不是取中点
    """
    sup_zone, res_zone, sup_strength, res_strength = get_sr_zone(
        df_5m, df_15m, df_1h, tolerance_pct=tolerance_pct
    )
    return sup_zone, res_zone, sup_strength, res_strength


if __name__ == "__main__":
    _, df_1h  = get_h1_klines()
    _, df_15m = get_m15_klines()
    _, df_5m  = get_m5_klines()

    # 此处假设 df 已经成功获取
    aaaa = get_sr_line(df_5m, df_15m, df_1h)
    
    # 修复笔误：第二个输出改为“阻力带”
    print(aaaa)

    # # 调用修复后的函数
    # sup_line, res_line = get_sr_line(df_5m, df_15m, df_1h)
    # plot_klines(df_5m, title="K线图", support=sup_line, resistance=res_line)
    # print(f"支撑线: {sup_line} | 阻力线: {res_line}") 
    