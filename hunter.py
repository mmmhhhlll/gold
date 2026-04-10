import schedule
import time as time_module
from datetime import datetime

from config import *
from mt5 import *
from indicators import get_sr_line
from risk_manager import can_trade, calculate_sl_points, calculate_tp_price, calculate_lot
from signal_manager import process_signals
from trading_executor import execute_order
from messager import send_notification


# ==========================================
# 主任务：每次轮询执行
# ==========================================
def do_task():
    now = datetime.now()
    console.print(f"\n[cyan]⏰ {now.strftime('%H:%M:%S')} 开始扫描...[/cyan]")

    # ==========================================
    # 第一步：检查MT5连接状态
    # ==========================================
    if not connect_mt5():
        console.print("[red]❌ 重连失败，跳过本次扫描[/red]")
        return

    # ==========================================
    # 第二步：获取K线数据
    # ==========================================
    _, df_1h  = get_h1_klines()
    _, df_20m = get_m20_klines()
    _, df_5m  = get_m5_klines(count=100)

    if df_5m is None or df_5m.empty:
        console.print("[red]❌ 获取K线失败，跳过本次扫描[/red]")
        return

    # ==========================================
    # 第三步：信号管家判断
    # ==========================================
    trade_context = process_signals(df_5m)

    if trade_context is None:
        return

    # ==========================================
    # 第四步：拿到确认信号
    # ==========================================
    signal         = trade_context["direction"]
    pattern        = trade_context["pattern"]
    entry_price    = trade_context["entry_price"]
    entry_time     = trade_context["entry_time"]
    df_result      = trade_context["df_result"]
    trend_strength = trade_context.get("trend_strength", 0) # ★ 新增：提取趋势强度
    direction      = "做多" if signal == 100 else "做空"

    # ★ 优化：在终端日志中打印出强度
    console.print(f"[cyan]📶 信号确认 | 形态:{pattern} | 方向:{direction} | 强度:{trend_strength} | 价格:{entry_price}[/cyan]")

    # ==========================================
    # 第五步：计算止损
    # ==========================================
    sl_points, sl_price = calculate_sl_points(signal, df_result, pattern=pattern)

    if sl_points is None:
        console.print("[red]❌ 止损计算失败，跳过[/red]")
        return

    # ==========================================
    # 第六步：综合风控检查
    # 这里统一调用 can_trade，它内部会进行时间、持仓、亏损、止损距离等所有检查
    # ==========================================
    ok, _ = can_trade(signal, entry_price, df_5m, df_20m, df_1h, sl_points)
    if not ok:
        # can_trade 内部已经打印了具体的拦截原因，这里只需拦截即可
        console.print(f"[yellow]🚫 风控拦截，取消开仓[/yellow]")
        return

    # ==========================================
    # 第七步：计算手数和止盈
    # ==========================================
    lot      = calculate_lot(sl_points)
    tp_price = calculate_tp_price(signal, entry_price, sl_points)

    if lot is None or tp_price is None:
        console.print("[red]❌ 手数或止盈计算失败，跳过[/red]")
        return

    console.print(f"[dim]📊 手数:{lot} 止损:{sl_price} 止盈:{tp_price}[/dim]")

    # ==========================================
    # 第八步：执行下单
    # ==========================================
    result = execute_order(signal=signal, volume=lot, sl=sl_price, tp=tp_price,
                           pattern=pattern, entry_time=entry_time)

    if result["success"]:
        console.print(f"[green]✅ 下单成功 | 订单号:{result['order']} | 成交价:{result['price']}[/green]")
        order_no     = result['order']
        real_price   = result['price']
        order_status = "下单成功"
    else:
        console.print(f"[red]❌ 下单失败: {result['message']}[/red]")
        order_no     = "N/A"
        real_price   = entry_price
        order_status = f"下单失败:{result['message']}"

    # ==========================================
    # 第九步：画图并保存，拿到相对路径用于推送图片
    # ==========================================
    image_rel_path = ""   # 默认空，画图失败时推送不含图片
    try:
        sup_zone, res_zone, _, _ = get_sr_line(df_5m, df_20m, df_1h)

        # ★ 优化：把强度也写到 K线图的标题上
        title = (
            f"{pattern} {direction} (强度:{trend_strength}) | "
            f"入场:{real_price:.2f} SL:{sl_price:.2f} TP:{tp_price:.2f} | "
            f"手数:{lot} | 订单:{order_no} | {order_status}"
        )

        fig = plot_klines(
            df_result,
            title        = title,
            support      = sup_zone,
            resistance   = res_zone,
            entry_price  = real_price,
            entry_time   = entry_time,
            entry_signal = signal,
            sl_price     = sl_price,
            tp_price     = tp_price,
        )
        image_rel_path = save_chart(fig, title=f"{pattern}_{direction}")

    except Exception as e:
        console.print(f"[yellow]⚠️ 画图失败: {e}[/yellow]")

    # ==========================================
    # 第十步：推送通知（Bark + ntfy，附带K线图）
    # ==========================================
    send_notification(
        signal       = signal,
        pattern      = pattern,
        entry_price  = real_price,
        sl_price     = sl_price,
        tp_price     = tp_price,
        lot          = lot,
        order_no     = order_no,
        order_status = order_status,
        image_name   = image_rel_path,   # "{YYYYMMDD}/{uuid}.png"，空字符串则不附图
        success      = result["success"],
    )


# ==========================================
# 程序入口
# ==========================================
if __name__ == "__main__":
    console.print("[bold green]🚀 猎手机器人启动！[/bold green]")

    while True:
        if connect_mt5():
            console.print("[bold green]✅ MT5已连接，开始监控...[/bold green]")
            break
        else:
            console.print("[yellow]⚠️ MT5连接失败，5秒后重试...[/yellow]")
            time_module.sleep(5)

    do_task()

    schedule.every(5).seconds.do(do_task)

    try:
        while True:
            schedule.run_pending()
            time_module.sleep(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]🛑 收到停止指令，猎手安全退出。[/yellow]")
        disconnect_mt5()