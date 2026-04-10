"""
风险管理模块
负责交易前的所有检查和下单参数计算
（已解耦，不直接依赖 MetaTrader5）
"""
from datetime import datetime, time
import pandas as pd
import pandas_ta as ta

from config import *
from indicators import get_sr_line
from mt5 import (
    connect_mt5, get_tick,
    get_account_info, get_positions_count, get_symbol_info
)


# ==========================================
# 1. 时间检查
# ==========================================
def check_time():
    """
    交易时间检查
    有效交易窗口：15:00 - 24:00（共9小时）
    返回 (bool, str, str) → (是否可交易, 原因, 时段质量)
    """
    now          = datetime.now()
    current_time = now.time()
    weekday      = now.weekday()
    month        = now.month
    is_summer    = 4 <= month <= 10

    if weekday >= 5:
        return False, "周末休市", "无"

    if weekday == 0 and current_time < time(15, 0):
        return False, "周一观望，等欧盘开盘", "无"

    if weekday == 4 and current_time >= time(22, 0):
        return False, "周五收盘前机构平仓，无理波动不做", "无"

    if time(0, 0) <= current_time < time(4, 0):
        return False, "纽约盘后期动力衰竭", "无"

    if time(4, 0) <= current_time < time(9, 0):
        return False, "极低流动性，点差过大", "无"

    if time(9, 0) <= current_time < time(15, 0):
        return False, "亚洲盘波动小，超短线不适合", "无"

    if is_summer:
        news_points = [time(20, 0), time(20, 30)]
    else:
        news_points = [time(21, 0), time(21, 30)]

    fomc_point      = time(2, 0)
    all_news_points = news_points + [fomc_point]

    for news_time in all_news_points:
        news_dt = datetime.combine(now.date(), news_time)
        now_dt  = datetime.combine(now.date(), current_time)
        diff    = abs((now_dt - news_dt).total_seconds())
        if diff <= 1800:
            return False, "重大数据前后30分钟，滑点风险不做", "无"

    change_point = datetime.combine(now.date(), time(20, 0))
    now_dt       = datetime.combine(now.date(), current_time)
    if abs((now_dt - change_point).total_seconds()) <= 1800:
        return False, "变盘前后30分钟，高度怀疑不做", "无"

    if time(15, 0) <= current_time < time(17, 0):
        return True, "欧盘开盘，趋势开始", "普通"

    if time(17, 0) <= current_time < time(19, 30):
        return True, "欧盘吃饭时段，信号要求更严格", "谨慎"

    if time(20, 30) <= current_time < time(22, 0):
        return True, "欧美重叠黄金期，最佳交易时段", "黄金"

    if time(22, 0) <= current_time <= time(23, 59):
        return True, "美盘后期，动力开始减弱", "普通"

    return False, "当前不在交易时段", "无"


# ==========================================
# 2. 支撑阻力位置检查
# ==========================================
def check_near_sr(price, df_5m, df_15m, df_1h, threshold=0.8):
    """
    检查当前价格是否在支撑或阻力区间附近
    返回 (bool, str, str) → (是否附近, 原因, 强度)
    """
    sup_zone, res_zone, sup_strength, res_strength = get_sr_line(df_5m, df_15m, df_1h)

    if sup_zone is None and res_zone is None:
        return False, "无法识别支撑阻力，不开仓", None

    results = []

    if sup_zone is not None:
        sup_low, sup_high = sup_zone
        if sup_low - threshold <= price <= sup_high + threshold:
            results.append({
                'type'    : 'support',
                'zone'    : sup_zone,
                'strength': sup_strength,
                'msg'     : f"价格在支撑区间 {sup_low:.2f}-{sup_high:.2f} 附近，强度:{sup_strength}"
            })

    if res_zone is not None:
        res_low, res_high = res_zone
        if res_low - threshold <= price <= res_high + threshold:
            results.append({
                'type'    : 'resistance',
                'zone'    : res_zone,
                'strength': res_strength,
                'msg'     : f"价格在阻力区间 {res_low:.2f}-{res_high:.2f} 附近，强度:{res_strength}"
            })

    if not results:
        distances = []
        if sup_zone:
            distances.append(('支撑', sup_zone[1], abs(price - sup_zone[1])))
        if res_zone:
            distances.append(('阻力', res_zone[0], abs(price - res_zone[0])))
        nearest = min(distances, key=lambda x: x[2])
        return False, f"价格不在支撑阻力附近，最近{nearest[0]} {nearest[1]:.2f} 距离 {nearest[2]:.2f} 美元", None

    best = sorted(results, key=lambda x: 0 if x['strength'] == 'strong' else 1)[0]
    return True, best['msg'], best['strength']


# ==========================================
# 3. 止损距离检查 (已使用美元绝对值修复)
# ==========================================
def check_sl_distance(sl_points, symbol=None, min_usd=5.0, max_usd=12.0):
    """
    动态止损距离检查（基于美元绝对值，自动适应平台精度）
    min_usd: 最小止损距离（美元），默认0.3美元
    max_usd: 最大止损距离（美元），默认4美元
    返回 (bool, str)
    """
    if sl_points is None or sl_points <= 0:
        return False, "止损距离无效"

    symbol_info = get_symbol_info(symbol)
    if symbol_info is None:
        return False, "无法获取品种精度信息"

    point_value = symbol_info["point"]
    sl_usd_distance = sl_points * point_value

    if sl_usd_distance < min_usd:
        return False, f"止损距离太近: {sl_points:.0f}points ({sl_usd_distance:.2f}美元)，最小需{min_usd}美元"

    if sl_usd_distance > max_usd:
        return False, f"止损距离太远: {sl_points:.0f}points ({sl_usd_distance:.2f}美元)，超过{max_usd}美元不做"

    return True, f"止损距离合理: {sl_points:.0f}points ({sl_usd_distance:.2f}美元)"


# ==========================================
# 4. 账户风控检查
# ==========================================
def check_daily_loss(max_loss_pct=0.01):
    """
    检查今日亏损是否超限
    返回 (bool, str)
    """
    try:
        account = get_account_info()
        if account is None:
            return False, "无法获取账户信息"

        balance        = account["balance"]
        equity         = account["equity"]
        daily_loss     = balance - equity
        max_daily_loss = balance * max_loss_pct

        if daily_loss >= max_daily_loss:
            return False, f"今日亏损 {daily_loss:.2f} 已达上限 {max_daily_loss:.2f}，停止交易"

        remaining = max_daily_loss - daily_loss
        return True, f"今日亏损 {daily_loss:.2f}，剩余额度 {remaining:.2f}"

    except Exception as e:
        return False, f"检查每日亏损异常: {str(e)}"


def check_position_count(max_positions=2):
    """
    检查当前持仓数量是否超限
    返回 (bool, str)
    """
    count = get_positions_count()
    if count >= max_positions:
        return False, f"当前持仓{count}单，已达上限{max_positions}单，不开新仓"

    return True, f"当前持仓{count}单，可以开仓"

# ==========================================
# 独立风控模块：大级别趋势审查
# ==========================================
def check_macro_trend(signal, df_1h, min_slope_threshold=0.0001):
    """
    检查宏观大趋势（H1级别），确保只做顺风局。
    
    参数:
    signal (int): 100 为做多，-100 为做空
    df_1h (DataFrame): 1小时级别的 K 线数据
    min_slope_threshold (float): 容错斜率，允许在微弱倾斜/近乎走平的状态下试错
    
    返回:
    bool, str: (是否顺势, 拦截原因/放行提示)
    """
    if df_1h is None or len(df_1h) < 25:
        console.print("[yellow]⚠️ H1 K线数据不足，跳过风控检查[/yellow]")
        return False, "H1数据不足"

    # 核心铁律：必须使用 iloc[-2] (上一根已彻底走完的1小时K线)
    # pandas-ta: linreg(slope=True) 等效于 talib.LINEARREG_SLOPE
    h1_slopes = ta.linreg(df_1h['close'], length=20, slope=True)
    last_closed_h1_slope = h1_slopes.iloc[-2]

    if pd.isna(last_closed_h1_slope):
        return False, "H1斜率计算中"

    if signal == 100:  # 计划做多
        # 如果 H1 斜率明显向下，说明处于 1小时级别的下跌波段
        if last_closed_h1_slope < -min_slope_threshold:
            console.print(f"[yellow]🚫 [大势逆风] H1处于下跌趋势 (斜率:{last_closed_h1_slope:.5f})，禁止做多接飞刀！[/yellow]")
            return False, "H1大趋势向下"
            
    elif signal == -100:  # 计划做空
        # 如果 H1 斜率明显向上，说明处于 1小时级别的上涨波段
        if last_closed_h1_slope > min_slope_threshold:
            console.print(f"[yellow]🚫 [大势逆风] H1处于上涨趋势 (斜率:{last_closed_h1_slope:.5f})，禁止做空摸顶！[/yellow]")
            return False, "H1大趋势向上"

    return True, "H1趋势顺风"


# ==========================================
# 5. 计算下单参数
# ==========================================
def calculate_sl_points(signal, df, pattern=None, symbol=None):
    """
    根据形态类型计算止损位置
    """
    symbol_info = get_symbol_info(symbol)
    if symbol_info is None:
        return None, None

    point  = symbol_info["point"]
    buffer = 30 * point  # 0.3美元缓冲

    ask, bid, _ = get_tick(symbol)
    if ask is None:
        return None, None

    if pattern == "Fractal":
        sl_candle = df.iloc[-3]
        console.print(f"[dim]📍 Fractal止损参考K: 中间K(iloc[-3]) high={sl_candle['high']:.2f} low={sl_candle['low']:.2f}[/dim]")
    elif pattern == "2B":
        sl_candle = df.iloc[-3]
        console.print(f"[dim]📍 2B止损参考K: 被吞没K(iloc[-3]) high={sl_candle['high']:.2f} low={sl_candle['low']:.2f}[/dim]")
    else:
        sl_candle = df.iloc[-2]

    if signal == 100:  
        entry_price = ask
        sl_price    = sl_candle['low'] - buffer
        sl_points   = abs(entry_price - sl_price) / point

    elif signal == -100:  
        entry_price = bid
        sl_price    = sl_candle['high'] + buffer
        sl_points   = abs(entry_price - sl_price) / point

    else:
        return None, None

    console.print(f"[dim]📍 入场价:{entry_price:.2f} 止损价:{round(sl_price,2)} 距离:{round(sl_points,0):.0f}points[/dim]")
    return round(sl_points, 0), round(sl_price, 2)
    
def calculate_tp_price(signal, entry_price, sl_points, ratio=1.5, symbol=None):
    """
    根据止损距离和盈亏比计算止盈价
    """
    symbol_info = get_symbol_info(symbol)
    if symbol_info is None:
        return None

    point       = symbol_info["point"]
    tp_distance = sl_points * ratio * point

    if signal == 100:
        tp_price = entry_price + tp_distance
    elif signal == -100:
        tp_price = entry_price - tp_distance
    else:
        return None

    return round(tp_price, 2)


def calculate_lot(sl_points, risk_pct=0.005, symbol=None):
    """
    根据止损距离反推手数
    """
    account = get_account_info()
    if account is None:
        logger.error("无法获取账户信息")
        return None

    symbol_info = get_symbol_info(symbol)
    if symbol_info is None:
        logger.error("无法获取品种信息")
        return None

    balance     = account["balance"]
    point       = symbol_info["point"]
    tick_value  = symbol_info["trade_tick_value"]
    tick_size   = symbol_info["trade_tick_size"]
    
    point_value = tick_value / tick_size * point
    risk_amount = balance * risk_pct
    lot         = risk_amount / (sl_points * point_value)

    step = symbol_info["volume_step"]
    lot  = round(lot / step) * step
    lot  = max(symbol_info["volume_min"], lot)
    lot  = min(symbol_info["volume_max"], lot)

    logger.info(f"手数计算: 余额={balance:.2f} 风险={risk_amount:.2f} 止损={sl_points:.0f}points → {lot}手")
    return round(lot, 2)


# ==========================================
# 6. 总入口：所有条件检查
# ==========================================
def can_trade(signal, entry_price, df_5m, df_20m, df_1h, sl_points):
    """
    所有风控条件检查，全部通过才返回True
    """
    # ok, reason, quality = check_time()
    # if not ok:
    #     console.print(f"[yellow]⏰ 时间过滤: {reason}[/yellow]")
    #     return False, reason

    # ok, reason = check_position_count()
    # if not ok:
    #     console.print(f"[yellow]📊 持仓过滤: {reason}[/yellow]")
    #     return False, reason

    # ok, reason = check_daily_loss()
    # if not ok:
    #     console.print(f"[red]💰 风控过滤: {reason}[/red]")
    #     return False, reason


    is_trend_ok, trend_msg = check_macro_trend(signal, df_20m)
    if not is_trend_ok:
        # 如果大趋势不符合，直接拦截返回
        return False, trend_msg

    ok, reason = check_sl_distance(sl_points)
    if not ok:
        console.print(f"[yellow]📏 止损过滤: {reason}[/yellow]")
        return False, reason

    console.print(f"[green]✅ 所有风控通过 | 止损:{sl_points:.0f}points[/green]")
    return True, "可以交易"


# ==========================================
# 测试入口
# ==========================================
if __name__ == "__main__":
    from rich.console import Console
    console = Console()
    console.print("[bold cyan]===== risk_manager 测试 =====[/bold cyan]")

    if not connect_mt5():
        console.print("[red]❌ MT5连接失败，退出测试[/red]")
    else:
        # 1. 时间检查
        console.print("\n[cyan]--- 1. 时间检查 ---[/cyan]")
        ok, reason, quality = check_time()
        console.print(f"结果: {'✅' if ok else '❌'} | {reason} | 时段:{quality}")

        # 2. 止损距离检查
        console.print("\n[cyan]--- 2. 止损距离检查 ---[/cyan]")
        for pts in [200, 3000, 5000]:  # 换成了更适配3位小数的数值测试
            ok, reason = check_sl_distance(pts)
            console.print(f"止损{pts}points → {'✅' if ok else '❌'} | {reason}")

        # 3. 账户风控
        console.print("\n[cyan]--- 3. 账户风控 ---[/cyan]")
        ok, reason = check_daily_loss()
        console.print(f"每日亏损: {'✅' if ok else '❌'} | {reason}")

        ok, reason = check_position_count()
        console.print(f"持仓数量: {'✅' if ok else '❌'} | {reason}")

        # 4. 手数计算
        console.print("\n[cyan]--- 4. 手数计算 ---[/cyan]")
        for sl_pts in [500, 1000, 2000]:
            lot = calculate_lot(sl_pts)
            console.print(f"止损{sl_pts}points → 手数:{lot}")

        # 5. check_macro_trend（验证 pandas-ta linreg slope 可正常调用）
        console.print("\n[cyan]--- 5. 大级别趋势检查 (pandas-ta) ---[/cyan]")
        from mt5 import get_h1_klines
        _, df_1h = get_h1_klines(count=60)
        if df_1h is not None and not df_1h.empty:
            for sig, label in [(100, "做多"), (-100, "做空")]:
                ok, reason = check_macro_trend(sig, df_1h)
                console.print(f"{label} → {'✅' if ok else '❌'} | {reason}")
        else:
            console.print("[yellow]⚠️ H1数据获取失败，跳过趋势测试[/yellow]")

        console.print("\n[bold cyan]===== 测试完成 =====[/bold cyan]")