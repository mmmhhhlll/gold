# ==========================================
# mt5.py
# MT5 底层交互与数据处理模块（已深度梳理去重）
# ==========================================
import os
import uuid
import MetaTrader5 as mt5
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import pandas_ta as ta
from scipy.signal import argrelextrema
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from datetime import datetime

from config import console, logger, MT5_CONFIG, CHART_SAVE_DIR


# ==========================================
# 1. MT5 连接管理
# ==========================================
def connect_mt5():
    """初始化并登录 MT5"""
    if mt5.terminal_info() is not None:
        return True

    if not mt5.initialize():
        logger.error("MT5 初始化失败")
        return False

    if not mt5.login(MT5_CONFIG["login"], MT5_CONFIG["password"], server=MT5_CONFIG["server"]):
        console.print("[bold red]❌ MT5 登录失败，请检查账号密码[/bold red]")
        mt5.shutdown()
        return False

    console.print("[bold green]✅ MT5 连接并登录成功！[/bold green]")
    return True

def disconnect_mt5():
    """安全断开 MT5 连接"""
    mt5.shutdown()
    console.print("[bold yellow]🛑 MT5 连接已安全关闭。[/bold yellow]")


# ==========================================
# 2. 市场与品种数据 (Symbol, Tick, Klines)
# ==========================================
def select_symbol(symbol):
    """确保品种在市场报价窗口可见"""
    return mt5.symbol_select(symbol, True)

def get_symbol_info(symbol=None):
    """获取品种的基础信息（点值、小数点位数、最小手数等），返回字典"""
    symbol = symbol or MT5_CONFIG["symbol"]
    info = mt5.symbol_info(symbol)
    if info is None:
        return None
    return {
        "point": info.point,
        "digits": info.digits,
        "trade_tick_size": info.trade_tick_size,
        "trade_tick_value": info.trade_tick_value,
        "volume_step": info.volume_step,
        "volume_min": info.volume_min,
        "volume_max": info.volume_max
    }

def get_tick(symbol=None):
    """获取当前实时 tick 数据，返回 (ask, bid, spread_points)"""
    symbol = symbol or MT5_CONFIG["symbol"]
    tick = mt5.symbol_info_tick(symbol)
    symbol_info = mt5.symbol_info(symbol)

    if tick is None or symbol_info is None:
        console.print(f"[red]❌ 无法获取 {symbol} tick数据[/red]")
        return None, None, None

    spread_points = round((tick.ask - tick.bid) / symbol_info.point, 1)
    return tick.ask, tick.bid, spread_points

def get_entry_price(signal, symbol=None):
    """根据信号方向返回入场价：100(做多)用ask, -100(做空)用bid"""
    ask, bid, spread = get_tick(symbol)
    if ask is None:
        return None

    console.print(f"[dim]📌 ask={ask} bid={bid} 点差={spread}points[/dim]")
    if signal == 100:
        return ask
    elif signal == -100:
        return bid
    else:
        console.print("[yellow]⚠️ 信号无效，无法获取入场价[/yellow]")
        return None

def _fetch_klines_base(timeframe, count):
    """内部通用方法：获取K线"""
    if mt5.terminal_info() is None:
        console.print("[red]❌ MT5未连接，跳过本次K线获取[/red]")
        return False, pd.DataFrame()

    symbol = MT5_CONFIG["symbol"]
    if not select_symbol(symbol):
        console.print(f"[yellow]⚠️ 无法选择品种: {symbol}[/yellow]")
        return False, pd.DataFrame()

    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        console.print(f"[yellow]⚠️ 未能获取到 {symbol} 的K线数据[/yellow]")
        return False, pd.DataFrame()

    df = pd.DataFrame(rates)[["time", "open", "high", "low", "close", "tick_volume"]]
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return True, df

def get_m1_klines(count=50):  return _fetch_klines_base(mt5.TIMEFRAME_M1,  count)
def get_m5_klines(count=50):  return _fetch_klines_base(mt5.TIMEFRAME_M5,  count)
def get_m15_klines(count=50): return _fetch_klines_base(mt5.TIMEFRAME_M15, count)
def get_m20_klines(count=50): return _fetch_klines_base(mt5.TIMEFRAME_M20, count)
def get_m30_klines(count=50): return _fetch_klines_base(mt5.TIMEFRAME_M30, count)
def get_h1_klines(count=50):  return _fetch_klines_base(mt5.TIMEFRAME_H1,  count)
def get_h4_klines(count=50):  return _fetch_klines_base(mt5.TIMEFRAME_H4,  count)
def get_d1_klines(count=50):  return _fetch_klines_base(mt5.TIMEFRAME_D1,  count)
def get_w1_klines(count=50):  return _fetch_klines_base(mt5.TIMEFRAME_W1,  count)
def get_mn1_klines(count=50): return _fetch_klines_base(mt5.TIMEFRAME_MN1, count)


# ==========================================
# 3. 账户与持仓 (Account & Positions)
# ==========================================
def get_account_info():
    """获取账户综合信息，统一返回标准字典"""
    account = mt5.account_info()
    if account is None:
        return None
    return {
        "login": account.login,
        "server": account.server,
        "balance": account.balance,
        "equity": account.equity,
        "margin_free": account.margin_free,
        "leverage": account.leverage,
        "trade_mode": "模拟" if account.trade_mode == 1 else "真实"
    }

def get_positions(symbol=None, ticket=None):
    """获取持仓列表，解耦MT5对象，返回字典列表"""
    if ticket:
        positions = mt5.positions_get(ticket=ticket)
    elif symbol:
        positions = mt5.positions_get(symbol=symbol)
    else:
        positions = mt5.positions_get()

    if not positions:
        return []

    return [{
        "ticket": p.ticket,
        "symbol": p.symbol,
        "direction": "BUY" if p.type == 0 else "SELL",
        "volume": p.volume,
        "price_open": p.price_open,
        "price_current": p.price_current,
        "sl": p.sl,
        "tp": p.tp,
        "profit": p.profit,
        "magic": p.magic,
        "time": p.time  # <--- 加上这一行，获取订单开仓时间
    } for p in positions]

def get_positions_count(symbol=None):
    """获取指定品种的持仓数量"""
    return len(get_positions(symbol=symbol))


# ==========================================
# 4. 交易执行 (Order Execution)
# ==========================================
def _get_filling_type(symbol):
    """内部方法：自动获取 broker 支持的订单填充类型"""
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return mt5.ORDER_FILLING_IOC
    filling_mode = symbol_info.filling_mode
    if filling_mode & mt5.ORDER_FILLING_IOC:
        return mt5.ORDER_FILLING_IOC
    elif filling_mode & mt5.ORDER_FILLING_FOK:
        return mt5.ORDER_FILLING_FOK
    else:
        return mt5.ORDER_FILLING_RETURN

def send_market_order(symbol, direction, volume, price, sl=None, tp=None, magic=0, comment="", position_ticket=None):
    """发送市价单（涵盖开新仓和针对特定单号平仓）"""
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

    request = {
        "action"      : mt5.TRADE_ACTION_DEAL,
        "symbol"      : symbol,
        "volume"      : float(volume),
        "type"        : order_type,
        "price"       : float(price),
        "deviation"   : 20,
        "magic"       : int(magic),
        "comment"     : comment,
        "type_time"   : mt5.ORDER_TIME_GTC,
        "type_filling": _get_filling_type(symbol),
    }

    if sl is not None: request["sl"] = float(sl)
    if tp is not None: request["tp"] = float(tp)
    if position_ticket is not None: request["position"] = int(position_ticket)

    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        return {"success": True, "order": result.order, "price": result.price, "volume": result.volume}
    else:
        return {"success": False, "message": f"{result.comment} (retcode={result.retcode})"}

def modify_sltp(ticket, symbol, sl, tp):
    """修改订单的止损和止盈"""
    request = {
        "action"  : mt5.TRADE_ACTION_SLTP,
        "position": int(ticket),
        "symbol"  : symbol,
        "sl"      : float(sl) if sl is not None else 0.0,
        "tp"      : float(tp) if tp is not None else 0.0,
    }
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        return {"success": True, "message": "修改成功"}
    else:
        return {"success": False, "message": f"{result.comment} (retcode={result.retcode})"}


# ==========================================
# 5. 可视化绘图 (Visualization)
# ==========================================
def plot_klines(df, title="K线图 (信号雷达)", support=None, resistance=None,
                entry_price=None, entry_time=None, entry_signal=None,
                sl_price=None, tp_price=None):
    """绘制K线图及支撑阻力、信号、止损止盈位"""
    if df is None or df.empty:
        console.print("[bold yellow]⚠️ 数据为空，无法绘图[/bold yellow]")
        return None

    x     = mdates.date2num(df["time"])
    width = (x[1] - x[0]) * 0.6 if len(x) > 1 else 0.01
    fig, ax = plt.subplots(figsize=(14, 7))

    for row in df.itertuples(index=False):
        x_pos  = mdates.date2num(row.time)
        bottom = min(row.open, row.close)
        height = abs(row.close - row.open) or 0.0001
        fill_color = "white" if row.close >= row.open else "black"
        edge_color = "black"

        current_pattern = getattr(row, 'pattern', 'none')
        current_signal  = getattr(row, 'signal',  0)

        if current_signal == 100:
            if current_pattern == "2B":        fill_color = "#00cc00"
            elif current_pattern == "Fractal": fill_color = "#ffa500"
        elif current_signal == -100:
            if current_pattern == "2B":        fill_color = "#cc0000"
            elif current_pattern == "Fractal": fill_color = "#0066ff"

        ax.vlines(x_pos, row.low, row.high, color=edge_color, linewidth=1)
        ax.bar(x_pos, height, width=width, bottom=bottom,
               color=fill_color, edgecolor=edge_color, linewidth=1)

    if support is not None:
        for s in (support if isinstance(support, (list, tuple)) else [support]):
            if s is not None:
                ax.axhline(y=s, color='green', linestyle='--', alpha=0.4, linewidth=1)

    if resistance is not None:
        for r in (resistance if isinstance(resistance, (list, tuple)) else [resistance]):
            if r is not None:
                ax.axhline(y=r, color='red', linestyle='--', alpha=0.4, linewidth=1)

    if entry_price is not None and entry_signal is not None:
        entry_color  = "#00aa00" if entry_signal == 100 else "#cc0000"
        arrow_symbol = "▲" if entry_signal == 100 else "▼"
        label_text   = "做多" if entry_signal == 100 else "做空"

        ax.axhline(y=entry_price, color=entry_color, linestyle='-', linewidth=1.5, alpha=0.9)
        ax.annotate(f"入场 {entry_price:.2f}", xy=(1.001, entry_price), xycoords=('axes fraction', 'data'),
                    color=entry_color, fontsize=8, fontweight='bold', va='center')

        if entry_time is not None:
            entry_x      = mdates.date2num(entry_time)
            price_range  = df['high'].max() - df['low'].min()
            price_offset = price_range * 0.03
            arrow_y      = entry_price - price_offset if entry_signal == 100 else entry_price + price_offset

            ax.annotate(f"{arrow_symbol} {label_text}\n{entry_price:.2f}",
                        xy=(entry_x, entry_price), xytext=(entry_x, arrow_y),
                        color=entry_color, fontsize=8, fontweight='bold',
                        ha='center', va='top' if entry_signal == 100 else 'bottom',
                        arrowprops=dict(arrowstyle='->' if entry_signal == 100 else '<-', color=entry_color, lw=2))

    if sl_price is not None:
        ax.axhline(y=sl_price, color='#ff2222', linestyle='-.', linewidth=1.5, alpha=0.9)
        ax.annotate(f"SL {sl_price:.2f}", xy=(1.001, sl_price), xycoords=('axes fraction', 'data'),
                    color='#ff2222', fontsize=8, fontweight='bold', va='center')

    if tp_price is not None:
        ax.axhline(y=tp_price, color='#00aa44', linestyle='-.', linewidth=1.5, alpha=0.9)
        ax.annotate(f"TP {tp_price:.2f}", xy=(1.001, tp_price), xycoords=('axes fraction', 'data'),
                    color='#00aa44', fontsize=8, fontweight='bold', va='center')

    ax.set_title(title, fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax.grid(True, linestyle=':', alpha=0.4)

    legend_elements = [
        Patch(facecolor='#00cc00', edgecolor='black', label='做多: 2B'),
        Patch(facecolor='#cc0000', edgecolor='black', label='做空: 2B'),
        Patch(facecolor='#ffa500', edgecolor='black', label='做多: 底分型'),
        Patch(facecolor='#0066ff', edgecolor='black', label='做空: 顶分型'),
        Patch(facecolor='white',   edgecolor='black', label='阳K'),
        Patch(facecolor='black',   edgecolor='black', label='阴K'),
    ]

    if entry_price is not None and entry_signal is not None:
        entry_color = "#00aa00" if entry_signal == 100 else "#cc0000"
        legend_elements.append(Patch(facecolor=entry_color, edgecolor='black', label=f'入场: {entry_price:.2f}'))
    if sl_price is not None:
        legend_elements.append(Patch(facecolor='#ff2222', edgecolor='black', label=f'止损 SL: {sl_price:.2f}'))
    if tp_price is not None:
        legend_elements.append(Patch(facecolor='#00aa44', edgecolor='black', label=f'止盈 TP: {tp_price:.2f}'))

    ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1.01, 1), fontsize=8)
    fig.autofmt_xdate()
    plt.tight_layout()
    return fig

def save_chart(fig, title="chart") -> str:
    """
    保存绘图到本地，返回相对于 IMAGE_BASE_URL 的路径。

    返回格式：{YYYYMMDD}/{uuid}.png
    完整 URL = IMAGE_BASE_URL.rstrip('/') + '/' + 返回值
    失败时返回空字符串。
    """
    if fig is None:
        console.print("[yellow]⚠️ fig为空，无法保存[/yellow]")
        return ""

    now = datetime.now()
    date_dir  = now.strftime("%Y%m%d")                    # e.g. 20260401
    file_name = f"{uuid.uuid4()}.png"                     # e.g. 6fe9aec7-....png
    save_dir  = os.path.join(CHART_SAVE_DIR, date_dir)
    os.makedirs(save_dir, exist_ok=True)
    filepath  = os.path.join(save_dir, file_name)
    fig.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close(fig)
    rel_path = f"{date_dir}/{file_name}"                  # 返回给调用方拼 URL 用
    console.print(f"[green]📊 已保存: {filepath}[/green]")
    return rel_path


# ==========================================
# 测试入口
# ==========================================
if __name__ == "__main__":
    console.print("[bold cyan]===== mt5.py 测试 =====[/bold cyan]")
    if connect_mt5():
        info = get_account_info()
        console.print(f"账户余额: {info['balance']} | 净值: {info['equity']}")
        df = get_m5_klines(count=20)
        console.print(df)
        disconnect_mt5()
