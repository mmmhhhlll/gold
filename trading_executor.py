#!/usr/bin/env python3
"""
交易执行器模块
整合 MT5 交易功能，包括买入、卖出、平仓和账户状态检查
（完全通过 mt5.py 底层调用，无原生 MetaTrader5 依赖）
"""

import time as time_module
from datetime import datetime
from config import *
from mt5 import (
    connect_mt5, get_tick, get_symbol_info,
    select_symbol, send_market_order, modify_sltp,
    get_positions, get_account_info
)

# ==========================================
# 下单（买入/卖出）
# ==========================================
def execute_order(signal, volume=0.01, sl=None, tp=None, pattern="", entry_time=None):
    """
    执行买入或卖出订单
    signal     : 100=买入 -100=卖出
    pattern    : 触发形态，如 '2B' / 'Fractal'
    entry_time : 信号产生时间（datetime），写入 MT5 注释
    """
    if signal not in (100, -100):
        return {"success": False, "message": f"无效信号: {signal}"}

    config = MT5_CONFIG
    symbol = config["symbol"]
    is_buy = (signal == 100)

    try:
        if not connect_mt5():
            return {"success": False, "message": "MT5 连接失败"}

        if not select_symbol(symbol):
            return {"success": False, "message": f"无法选择品种 {symbol}"}

        ask, bid, _ = get_tick(symbol)
        if ask is None or bid is None:
            return {"success": False, "message": "无法获取实时价格"}

        price     = ask if is_buy else bid
        direction = "BUY" if is_buy else "SELL"
        dir_cn    = "买入" if is_buy else "卖出"
        magic     = config.get("magic", 100001) if is_buy else config.get("magic", 100002)

        # MT5 comment 字段上限 31 字符，格式：形态 方向 HH:MM
        time_str = (entry_time or datetime.now()).strftime("%H:%M")
        comment  = f"{pattern} {direction} {time_str}"[:31]

        result = send_market_order(
            symbol=symbol,
            direction=direction,
            volume=volume,
            price=price,
            sl=sl,
            tp=tp,
            magic=magic,
            comment=comment,
        )

        if result["success"]:
            logger.info(f"{dir_cn}成功! 订单号:{result['order']} 成交价:{result['price']:.3f}")
            time_module.sleep(1)
            
            # 获取成交后的持仓信息
            positions = get_positions(ticket=result['order'])
            position_info = {}
            if positions:
                pos = positions[0]
                position_info = {
                    "ticket"       : pos["ticket"],
                    "price_open"   : pos["price_open"],
                    "price_current": pos["price_current"],
                    "profit"       : pos["profit"]
                }
            return {
                "success" : True,
                "order"   : result['order'],
                "price"   : result['price'],
                "position": position_info,
                "message" : f"{dir_cn}成功"
            }
        else:
            logger.error(f"{dir_cn}失败: {result['message']}")
            return result

    except Exception as e:
        logger.error(f"执行下单异常: {str(e)}", exc_info=True)
        return {"success": False, "message": str(e)}

def execute_buy(volume=0.01, price=None, sl=None, tp=None):
    return execute_order(signal=100, volume=volume, sl=sl, tp=tp)

def execute_sell(volume=0.01, price=None, sl=None, tp=None):
    return execute_order(signal=-100, volume=volume, sl=sl, tp=tp)


# ==========================================
# 全部平仓
# ==========================================
def close_position(ticket=None, symbol=None, magic_numbers=None):
    """
    全部平仓
    ticket: 指定订单号
    symbol: 平该品种所有持仓
    """
    try:
        if not connect_mt5():
            return {"success": False, "message": "MT5 连接失败"}

        if ticket:
            positions = get_positions(ticket=ticket)
        elif symbol:
            positions = get_positions(symbol=symbol)
        else:
            return {"success": False, "message": "请指定订单号或品种代码"}

        if not positions:
            return {"success": True, "message": "无持仓", "closed_count": 0, "total_profit": 0.0}

        closed_count     = 0
        total_profit     = 0.0
        closed_positions = []

        for pos in positions:
            if magic_numbers and pos["magic"] not in magic_numbers:
                continue

            # 平仓方向与持仓方向相反
            close_dir   = "SELL" if pos["direction"] == "BUY" else "BUY"
            ask, bid, _ = get_tick(pos["symbol"])
            
            if ask is None or bid is None:
                logger.error(f"无法获取价格，跳过订单 {pos['ticket']}")
                continue

            close_price = bid if close_dir == "SELL" else ask

            result = send_market_order(
                symbol=pos["symbol"],
                direction=close_dir,
                volume=pos["volume"],
                price=close_price,
                magic=pos["magic"],
                comment="自动平仓",
                position_ticket=pos["ticket"]
            )

            if result["success"]:
                logger.info(f"平仓成功! 订单:{pos['ticket']} 成交:{result['price']:.3f}")
                closed_count += 1
                total_profit += pos["profit"]
                closed_positions.append({
                    "ticket"     : pos["ticket"],
                    "volume"     : pos["volume"],
                    "profit"     : pos["profit"],
                    "close_price": result["price"]
                })
            else:
                logger.error(f"平仓失败 订单{pos['ticket']}: {result['message']}")

            time_module.sleep(0.5)

        return {
            "success"         : True,
            "closed_count"    : closed_count,
            "total_profit"    : total_profit,
            "closed_positions": closed_positions,
            "message"         : f"平仓完成，共{closed_count}单"
        }

    except Exception as e:
        logger.error(f"平仓异常: {str(e)}", exc_info=True)
        return {"success": False, "message": str(e)}


# ==========================================
# 部分平仓（半仓止盈专用）
# ==========================================
def close_partial(ticket, volume):
    """
    部分平仓，只平指定手数，剩余继续持有
    """
    try:
        if not connect_mt5():
            return {"success": False, "message": "MT5 连接失败"}

        positions = get_positions(ticket=ticket)
        if not positions:
            return {"success": False, "message": f"找不到订单 {ticket}"}

        pos = positions[0]

        if volume > pos["volume"]:
            logger.warning(f"部分平仓手数({volume})超过持仓手数({pos['volume']})，改为全部平仓")
            volume = pos["volume"]

        symbol_info = get_symbol_info(pos["symbol"])
        if symbol_info and volume < symbol_info["volume_min"]:
            return {"success": False, "message": f"平仓手数{volume}小于最小手数{symbol_info['volume_min']}"}

        close_dir   = "SELL" if pos["direction"] == "BUY" else "BUY"
        ask, bid, _ = get_tick(pos["symbol"])
        
        if ask is None or bid is None:
            return {"success": False, "message": "无法获取实时价格"}

        close_price = bid if close_dir == "SELL" else ask

        result = send_market_order(
            symbol=pos["symbol"],
            direction=close_dir,
            volume=volume,
            price=close_price,
            magic=pos["magic"],
            comment=f"半仓止盈 {volume}手",
            position_ticket=ticket
        )

        if result["success"]:
            remain_volume = round(pos["volume"] - volume, 2)
            logger.info(
                f"部分平仓成功! 订单:{ticket} "
                f"平仓:{volume}手 剩余:{remain_volume}手 "
                f"成交:{result['price']:.3f}"
            )
            return {
                "success"      : True,
                "ticket"       : ticket,
                "closed_volume": volume,
                "remain_volume": remain_volume,
                "close_price"  : result["price"],
                "message"      : f"部分平仓成功，平{volume}手，剩余{remain_volume}手"
            }
        else:
            logger.error(f"部分平仓失败: {result['message']}")
            return result

    except Exception as e:
        logger.error(f"部分平仓异常: {str(e)}", exc_info=True)
        return {"success": False, "message": str(e)}


# ==========================================
# 修改止损止盈
# ==========================================
def modify_position(ticket, sl=None, tp=None):
    """修改持仓的止损止盈"""
    try:
        if not connect_mt5():
            return {"success": False, "message": "MT5 连接失败"}

        positions = get_positions(ticket=ticket)
        if not positions:
            return {"success": False, "message": f"找不到订单 {ticket}"}

        pos = positions[0]
        final_sl = sl if sl is not None else pos["sl"]
        final_tp = tp if tp is not None else pos["tp"]

        result = modify_sltp(ticket, pos["symbol"], final_sl, final_tp)
        if result["success"]:
            logger.info(f"修改订单成功 {ticket} sl={final_sl} tp={final_tp}")
            return {"success": True, "message": "修改成功"}
        else:
            logger.error(f"修改失败: {result['message']}")
            return result

    except Exception as e:
        logger.error(f"修改订单异常: {str(e)}", exc_info=True)
        return {"success": False, "message": str(e)}


# ==========================================
# 账户和市场状态
# ==========================================
def get_account_status():
    try:
        if not connect_mt5():
            return {"success": False, "message": "MT5 连接失败"}

        account_info = get_account_info() or {}
        symbol       = MT5_CONFIG["symbol"]
        positions    = get_positions(symbol=symbol)
        
        total_profit = sum(p["profit"] for p in positions) if positions else 0.0
        
        market_info  = {}
        ask, bid, spread = get_tick(symbol)
        if ask is not None:
            market_info = {"bid": bid, "ask": ask, "spread": spread}

        return {
            "success"     : True,
            "account"     : account_info,
            "positions"   : positions,
            "total_profit": total_profit,
            "market"      : market_info
        }

    except Exception as e:
        logger.error(f"获取账户状态异常: {str(e)}", exc_info=True)
        return {"success": False, "message": str(e)}


def check_market():
    try:
        if not connect_mt5():
            return {"success": False, "message": "MT5 连接失败"}

        symbol = MT5_CONFIG["symbol"]
        if not select_symbol(symbol):
            return {"success": False, "message": f"无法选择品种 {symbol}"}

        ask, bid, spread = get_tick(symbol)
        if ask is None:
            return {"success": False, "message": "无法获取实时价格"}

        return {
            "success": True,
            "market" : {
                "symbol": symbol,
                "bid"   : bid,
                "ask"   : ask,
                "spread": spread,
                "time"  : datetime.now().isoformat()
            }
        }

    except Exception as e:
        logger.error(f"检查市场异常: {str(e)}", exc_info=True)
        return {"success": False, "message": str(e)}


if __name__ == "__main__":
    import sys
    from rich.console import Console
    console = Console()

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        if command == "status":
            status = get_account_status()
            if status["success"]:
                a = status["account"]
                console.print(f"[green]账户:{a.get('login')} 余额:{a.get('balance'):.2f} 净值:{a.get('equity'):.2f} 持仓:{len(status['positions'])}单[/green]")
        else:
            console.print("[yellow]可用测试命令: python trading_executor.py status[/yellow]")
    else:
        status = get_account_status()
        if status["success"]:
            a = status["account"]
            console.print(f"账户:{a.get('login')} 余额:{a.get('balance'):.2f} 净值:{a.get('equity'):.2f} 持仓:{len(status['positions'])}单")