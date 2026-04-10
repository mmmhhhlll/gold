"""
护卫机器人 (Guardian) - 黄金大波段抗扫荡版
阶段一：盈利达到1倍止损距离 → 平半仓，推保本损
阶段二：剩下的利润用 1小时(H1) 20EMA 均线追踪止损，让利润奔跑
"""

import schedule
import time as time_module
import pandas_ta as ta

from config import console
from mt5 import connect_mt5, get_tick, disconnect_mt5, get_positions, get_h1_klines
from trading_executor import close_position, close_partial, modify_position

# 防止网络延迟导致同一笔订单被重复发送请求
in_processing_tickets = set()

# ==========================================
# 护卫参数配置
# ==========================================
# 均线追踪参数：使用 H1 (1小时) 的 20 EMA (给黄金史诗级的呼吸空间，吃尽大趋势)
EMA_PERIOD = 20
# 追踪止损的最小修改步长 (黄金建议设 0.5 ~ 1.0 美元)
MIN_SL_STEP = 0.5 


def do_task():
    global in_processing_tickets

    if not connect_mt5():
        return

    # 获取所有持仓
    positions = get_positions()
    if not positions:
        in_processing_tickets.clear()
        return

    # 清理过时的锁
    current_tickets = {pos["ticket"] for pos in positions}
    in_processing_tickets = in_processing_tickets.intersection(current_tickets)

    # 如果有持仓，获取一次 1小时 K线用于均线计算
    # 字典缓存，防止多笔同品种订单重复请求 MT5 数据
    df_h1_dict = {}

    for pos in positions:
        ticket     = pos["ticket"]
        symbol     = pos["symbol"]
        direction  = pos["direction"]
        price_open = pos["price_open"]
        current_sl = pos["sl"]
        volume     = pos["volume"]

        if ticket in in_processing_tickets:
            continue

        # 获取当前价格
        ask, bid, _ = get_tick(symbol)
        if ask is None or bid is None:
            continue

        current_price = bid if direction == "BUY" else ask
        direction_str = "多单" if direction == "BUY" else "空单"
        is_buy        = (direction == "BUY")

        # ==========================================
        # 逻辑一：判断当前处于哪个阶段 (通过止损位置判断)
        # ==========================================
        # 如果多单止损小于开仓价，或者空单止损大于开仓价，说明还是【初始亏损状态】
        is_phase_1 = (is_buy and current_sl < price_open) or (not is_buy and current_sl > price_open)

        if is_phase_1:
            # ------------------------------------------
            # 阶段一防守：寻找 1R，平半仓 + 推保本
            # ------------------------------------------
            initial_risk = (price_open - current_sl) if is_buy else (current_sl - price_open)
            
            # 容错：如果没有设止损，或者止损设错，跳过
            if initial_risk <= 0:
                continue

            target_1r = price_open + initial_risk if is_buy else price_open - initial_risk
            hit_1r    = (is_buy and current_price >= target_1r) or (not is_buy and current_price <= target_1r)

            if hit_1r:
                console.print(f"[bold green]🎯 斩获1R利润！单号:{ticket} | {direction_str} | 现价:{current_price}[/bold green]")
                in_processing_tickets.add(ticket)

                # 1. 止损推至保本
                be_sl = price_open
                modify_res = modify_position(ticket, sl=be_sl)
                if modify_res and modify_res.get("success"):
                    console.print(f"[cyan]🛡️ 止损已推至保本价:{be_sl}[/cyan]")
                else:
                    console.print(f"[red]❌ 保本推损失败[/red]")

                # 2. 平半仓落袋为安
                half_vol = round(volume / 2.0, 2)
                if half_vol >= volume or half_vol <= 0:
                    console.print(f"[dim]手数({volume})太小无法拆分，全平出局。[/dim]")
                    close_position(ticket=ticket)
                else:
                    r = close_partial(ticket=ticket, volume=half_vol)
                    if r["success"]:
                        console.print(f"[cyan]💰 半仓({half_vol}手)已落袋，剩余利润随 H1 均线奔跑！[/cyan]")
                    else:
                        console.print(f"[red]❌ 平半仓失败[/red]")
                
                # 处理完毕，解锁这单，等下一次循环进入阶段二
                in_processing_tickets.discard(ticket)

        else:
            # ------------------------------------------
            # 阶段二防守：无风险状态，H1均线追踪止损 (Trailing with MA)
            # ------------------------------------------
            if symbol not in df_h1_dict:
                # 获取 1 小时 K 线
                _, df = get_h1_klines(symbol=symbol, count=50) 
                df_h1_dict[symbol] = df

            df_h1 = df_h1_dict.get(symbol)
            if df_h1 is None or len(df_h1) < EMA_PERIOD + 2:
                continue

            # 获取上一根已收盘的 1小时 K线计算的 EMA 值
            ema_values = ta.ema(df_h1['close'], length=EMA_PERIOD)
            trailing_ma = ema_values.iloc[-2]

            if is_buy:
                # 多单：当前价格必须在均线之上，且均线已经上移超过了当前的止损位
                if trailing_ma > current_sl + MIN_SL_STEP and current_price > trailing_ma:
                    console.print(f"[dim]📈 H1均线上移，多单({ticket}) 追踪止损 {current_sl} -> {trailing_ma:.2f}[/dim]")
                    modify_position(ticket, sl=trailing_ma)
            else:
                # 空单：当前价格必须在均线之下，且均线已经下移超过了当前的止损位
                if trailing_ma < current_sl - MIN_SL_STEP and current_price < trailing_ma:
                    console.print(f"[dim]📉 H1均线下移，空单({ticket}) 追踪止损 {current_sl} -> {trailing_ma:.2f}[/dim]")
                    modify_position(ticket, sl=trailing_ma)


if __name__ == "__main__":
    console.print("[bold cyan]🛡️ 护卫机器人启动 ！[/bold cyan]")

    while True:
        if connect_mt5():
            console.print("[bold green]✅ 护卫MT5已连接，开始盯盘...[/bold green]")
            break
        time_module.sleep(5)

    do_task()

    schedule.every(10).seconds.do(do_task)

    try:
        while True:
            schedule.run_pending()
            time_module.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]🛑 护卫已退下。[/yellow]")
        disconnect_mt5()