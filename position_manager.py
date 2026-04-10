import time as time_module
from config import console, MT5_CONFIG
from mt5 import get_symbol_info

def get_position_phase(direction, price_open, current_sl):
    if current_sl == 0.0: return "PHASE_1"
    if direction == "BUY": return "PHASE_1" if current_sl < price_open else "PHASE_3"
    if direction == "SELL": return "PHASE_1" if current_sl > price_open else "PHASE_3"
    return "PHASE_1"

def check_missing_sl(ticket, direction, price_open, current_sl, open_time_timestamp):
    if current_sl != 0.0: return False, "止损正常"
    held_minutes = (time_module.time() - open_time_timestamp) / 60
    if held_minutes > 5: return True, f"订单{ticket}持仓{held_minutes:.0f}分钟无止损"
    return False, "止损正常"

def check_timeout_close(open_time_timestamp, current_profit, max_hold_minutes=60):
    held_minutes = (time_module.time() - open_time_timestamp) / 60
    if held_minutes > max_hold_minutes and current_profit <= 0:
        return True, f"持仓已达 {held_minutes:.0f} 分钟且未盈利，时间止损出场"
    return False, "安全"

def check_phase2_trigger(direction, price_open, current_price, current_sl, current_volume, symbol):
    info = get_symbol_info(symbol)
    if not info:
        return False, 0.0, 0.0

    point  = info["point"]
    digits = info["digits"]
    step   = info["volume_step"]
    v_min  = info["volume_min"]

    # 防止重复推保本
    if direction == "BUY" and current_sl >= price_open: return False, 0.0, 0.0
    if direction == "SELL" and current_sl <= price_open: return False, 0.0, 0.0

    # 修复Bug3: 如果没设止损，默认给一个 300 points(3美元) 的心理预期，防止死锁
    if current_sl != 0.0:
        original_sl_points = abs(price_open - current_sl) / point
    else:
        original_sl_points = 300 

    profit_points = (current_price - price_open) / point if direction == "BUY" else (price_open - current_price) / point

    # 盈利不够，不触发
    if profit_points < original_sl_points:
        return False, 0.0, 0.0

    # 修复Bug2: 使用品种真实步长计算平仓手数
    raw_half_vol = current_volume / 2
    half_volume  = round(raw_half_vol / step) * step
    half_volume  = max(half_volume, v_min)

    # 如果平一半后剩下的连最小手数都不够，就干脆全平
    if current_volume - half_volume < v_min:
        half_volume = current_volume

    buffer = 30 * point
    new_sl = round(price_open + buffer, digits) if direction == "BUY" else round(price_open - buffer, digits)

    return True, half_volume, new_sl

def calc_trailing_sl(direction, price_open, current_price, current_sl, symbol, step_points=100):
    info = get_symbol_info(symbol)
    if not info: return False, 0.0

    point, digits = info["point"], info["digits"]

    if current_sl != 0.0:
        original_sl_points = abs(price_open - current_sl) / point
        trail_points = max(original_sl_points, 150)
    else:
        trail_points = 200

    if direction == "BUY":
        theoretical_sl = current_price - (trail_points * point)
        if theoretical_sl >= current_sl + (step_points * point) and theoretical_sl > price_open:
            return True, round(theoretical_sl, digits)

    elif direction == "SELL":
        theoretical_sl = current_price + (trail_points * point)
        if theoretical_sl <= current_sl - (step_points * point) and theoretical_sl < price_open:
            return True, round(theoretical_sl, digits)

    return False, 0.0