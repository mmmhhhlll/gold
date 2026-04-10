from datetime import datetime
import time as time_module
import schedule

from config import *
from mt5 import connect_mt5, get_m5_klines, plot_klines, save_chart
from patterns import _2b, _fractal


# ==========================================
# 全局配置与状态机
# ==========================================
MAX_WAIT_SECONDS = 300   # 最大等待确认时间（5分钟）
MIN_TREND_STRENGTH = 8   # ★ 新增：最小趋势强度要求，小于此值的信号直接抛弃

pending_signal = {
    'signal'    : 0,
    'pattern'   : 'none',
    'strength'  : 0,     # ★ 新增：记录当前挂起信号的强度
    'found_time': None,
}

# 已消费黑名单：同一根K线只处理一次
last_processed_candle_time = None


def clear_pending():
    """清空挂起状态"""
    pending_signal['signal']     = 0
    pending_signal['pattern']    = 'none'
    pending_signal['strength']   = 0
    pending_signal['found_time'] = None


# ==========================================
# 核心扫描与确认逻辑
# ==========================================
def confirm_entry(df, signal, pattern):
    """
    第二阶段：动能确认。观察当前正在跳动的 K 线 (iloc[-1])。
    做多信号 → 当前K收阳才确认
    做空信号 → 当前K收阴才确认
    """
    current_k     = df.iloc[-1]
    current_close = current_k['close']
    current_open  = current_k['open']

    result = {
        "status"     : "WAITING",
        "direction"  : 0,
        "pattern"    : pattern,
        "entry_price": current_close,
        "entry_time" : datetime.now(),
        "df_result"  : df
    }

    if signal == 100:
        if current_close > current_open:
            console.print(f"[bold green]✅ 动能确认！【{pattern}】做多条件成立[/bold green]")
            result["status"]    = "CONFIRMED"
            result["direction"] = 100
        else:
            console.print(f"⏳ 等待动能确认 ({pattern} 做多需收阳)...")

    elif signal == -100:
        if current_close < current_open:
            console.print(f"[bold red]✅ 动能确认！【{pattern}】做空条件成立[/bold red]")
            result["status"]    = "CONFIRMED"
            result["direction"] = -100
        else:
            console.print(f"⏳ 等待动能确认 ({pattern} 做空需收阴)...")

    return result


# ==========================================
# 主轮询入口
# ==========================================
def process_signals(df):
    """
    信号管家：处理信号的生命周期。
    返回 trade_context dict 或 None
    """
    global last_processed_candle_time

    if df is None or len(df) < 3:
        return None

    now = datetime.now()

    # 每次进来都先跑一遍模型，确保 df 上有最新的信号标签
    df_result = _2b(df)
    df_result = _fractal(df_result)

    # 1. 优先处理挂起中的信号
    if pending_signal['signal'] != 0:
        wait_seconds = (now - pending_signal['found_time']).total_seconds()

        if wait_seconds > MAX_WAIT_SECONDS:
            console.print(f"[yellow]⏰ 信号超时放弃 | 形态:{pending_signal['pattern']} | 已等待{wait_seconds:.0f}秒[/yellow]")
            clear_pending()
            return None

        confirmation = confirm_entry(df_result, pending_signal['signal'], pending_signal['pattern'])

        if confirmation["status"] == "CONFIRMED":
            # 将强度信息附加上去，透传给主程序
            confirmation["trend_strength"] = pending_signal['strength']
            clear_pending()
            return confirmation

        return None

    # 2. 扫描倒数第二根K线（已收线）
    last_closed_k  = df_result.iloc[-2]
    signal         = last_closed_k.get('signal', 0)
    pattern        = last_closed_k.get('pattern', 'none')
    trend_strength = last_closed_k.get('trend_strength', 0) # ★ 提取信号强度
    candle_time    = last_closed_k['time']

    if signal in (100, -100):
        # 黑名单检查：已处理过的K线跳过，防止重复入场
        if candle_time == last_processed_candle_time:
            return None

        # 记录时间戳进黑名单 (无论强度够不够，都记入黑名单，避免死循环打印过滤日志)
        last_processed_candle_time = candle_time
        direction_str = '做多' if signal == 100 else '做空'

        # ★ 新增：强度过滤网
        if trend_strength < MIN_TREND_STRENGTH:
            console.print(f"[dim]🗑️ 过滤弱信号:{pattern} {direction_str} | 强度:{trend_strength} (需>={MIN_TREND_STRENGTH}) | 时间:{candle_time}[/dim]")
            return None

        # 强度达标，挂起等待确认
        console.print(f"[cyan]📶 发现高价值信号:{pattern} {direction_str} | 强度:{trend_strength} | 时间:{candle_time} | 挂起等待确认...[/cyan]")

        pending_signal['signal']     = signal
        pending_signal['pattern']    = pattern
        pending_signal['strength']   = trend_strength
        pending_signal['found_time'] = now

    return None


# ==========================================
# 测试入口
# ==========================================
if __name__ == "__main__":
    console.print("[bold cyan]===== signal_manager 测试 =====[/bold cyan]")
    console.print("[dim]每15秒扫描一次，Ctrl+C 退出[/dim]\n")

    if not connect_mt5():
        console.print("[red]❌ MT5连接失败，退出[/red]")
        exit()

    def do_task():
        now = datetime.now()
        console.print(f"\n[cyan]⏰ {now.strftime('%H:%M:%S')} 开始扫描...[/cyan]")

        _, df = get_m5_klines(count=100)

        if df is None or df.empty:
            console.print("[red]❌ 获取K线失败[/red]")
            return

        trade_context = process_signals(df)

        if trade_context is not None:
            direction       = trade_context["direction"]
            pattern         = trade_context["pattern"]
            entry_price     = trade_context["entry_price"]
            entry_time      = trade_context["entry_time"]
            trend_strength  = trade_context.get("trend_strength", 0) # ★ 获取透传的强度
            df_result       = trade_context["df_result"]
            direction_label = "做多" if direction == 100 else "做空"

            # ★ 提示语中增加强度显示
            console.print(f"\n[bold yellow]🎯 信号确认! 形态:{pattern} | {direction_label} | 强度:{trend_strength} | 价格:{entry_price}[/bold yellow]")

            try:
                fig = plot_klines(
                    df_result,
                    title        = f"{pattern}_{direction_label}_{entry_price}",
                    entry_price  = entry_price,
                    entry_time   = entry_time,
                    entry_signal = direction,
                )
                save_chart(fig, title=f"{pattern}_{direction_label}")
                console.print("[green]✅ K线图已保存[/green]")
            except Exception as e:
                console.print(f"[red]⚠️ 画图失败: {e}[/red]")

    # 立即执行一次
    do_task()

    # 每15秒轮询
    schedule.every(15).seconds.do(do_task)

    try:
        while True:
            schedule.run_pending()
            time_module.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]🛑 已停止[/yellow]")