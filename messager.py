"""
消息推送模块 — 支持 Bark 和 ntfy 双通道
下单成功/失败时同时推送到手机
"""
import requests
from datetime import datetime
from config import console, logger, BARK_KEY, IMAGE_BASE_URL, NTFY_SERVER, NTFY_TOPIC, NTFY_TOKEN

BARK_URL = f"https://api.day.app/{BARK_KEY}"

def send_bark_notification(
    signal: int,
    pattern: str,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    lot: float,
    order_no,
    order_status: str,
    image_name: str = "",       # 🟢 增加默认值，防止为空时报错
    success: bool = True,
):
    symbol    = "XAUUSD"
    direction = "做多 📈" if signal == 100 else "做空 📉"
    now_str   = datetime.now().strftime("%m-%d %H:%M")

    if success:
        title  = f"✅ 下单成功 | {symbol} {direction}"
        level  = "timeSensitive"
        sound  = "minuet"
    else:
        title  = f"❌ 下单失败 | {symbol} {direction}"
        level  = "active"
        sound  = "shake"

    body = (
        f"形态: {pattern}  方向: {direction}\n"
        f"入场: {entry_price:.2f}  手数: {lot}\n"
        f"止损: {sl_price:.2f}  止盈: {tp_price:.2f}\n"
        f"订单: {order_no}  {now_str}\n"
        f"状态: {order_status}"
    )

    payload = {
        "title"    : title,
        "body"     : body,
        "group"    : "MT5猎手",
        "sound"    : sound,
        "level"    : level,
        "badge"    : 1,
        "isArchive": "1",
        "icon"     : "https://day.app/assets/images/avatar.jpg",
        "copy"     : f"{direction} 入场:{entry_price:.2f} SL:{sl_price:.2f} TP:{tp_price:.2f}",
    }

    # 🟢 只有当图片名存在且配置了 IMAGE_BASE_URL 时才拼接 image 参数
    if image_name and IMAGE_BASE_URL:
        payload["image"] = f"{IMAGE_BASE_URL.rstrip('/')}/{image_name}"

    try:
        resp = requests.post(
            BARK_URL,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=5,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 200:
            console.print("[green]📱 Bark 推送成功[/green]")
        else:
            console.print(f"[yellow]⚠️ Bark 返回异常: {result}[/yellow]")
    except Exception as e:
        logger.warning(f"Bark 推送失败: {e}")


def send_ntfy_notification(
    signal: int,
    pattern: str,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    lot: float,
    order_no,
    order_status: str,
    image_name: str = "",
    success: bool = True,
):
    """
    通过 ntfy 推送下单通知。

    采用 JSON 发布方式（POST 到 Server 根地址，topic 写入 JSON body），
    所有字段放在 JSON 里，完全避开 HTTP Header 的 latin-1 编码限制，
    中文、emoji 均可正常使用。

    参考文档：https://docs.ntfy.sh/publish/#publish-as-json
    """
    if not NTFY_TOPIC:
        logger.warning("NTFY_TOPIC 未配置，跳过 ntfy 推送")
        return

    direction = "做多 📈" if signal == 100 else "做空 📉"
    now_str   = datetime.now().strftime("%m-%d %H:%M")

    if success:
        title    = f"✅ 下单成功 | {direction} | {pattern}"
        tags     = ["white_check_mark", "chart_with_upwards_trend" if signal == 100 else "chart_with_downwards_trend"]
        priority = 4    # high：屏幕亮起，有声音，但不持续响铃 
    else:
        title    = f"❌ 下单失败 | {direction} | {pattern}"
        tags     = ["x", "warning"]
        priority = 3    # default 

    # Markdown 正文，ntfy 支持加粗/斜体/列表
    message = (
        f"**形态**: {pattern}  **方向**: {direction}\n"
        f"**入场**: {entry_price:.2f}  **手数**: {lot}\n"
        f"**止损**: {sl_price:.2f}  **止盈**: {tp_price:.2f}\n"
        f"**订单**: {order_no}  {now_str}\n"
        f"**状态**: {order_status}"
    )

    payload = {
        "topic"   : NTFY_TOPIC,
        "title"   : title,
        "message" : message,
        "tags"    : tags,
        "priority": priority,
        "icon"    : "https://day.app/assets/images/avatar.jpg",
        "markdown": True,
    }

    # 🟢 根据文档 JSON 格式支持，如果有图片，则附加到 payload 
    if image_name and IMAGE_BASE_URL:
        payload["attach"]   = f"{IMAGE_BASE_URL.rstrip('/')}/{image_name}"
        payload["filename"] = image_name

    # 自建服务开启 ACL 时需要携带 Token
    headers = {"Content-Type": "application/json"}
    if NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"

    try:
        resp = requests.post(
            NTFY_SERVER.rstrip('/'),    # JSON 发布 POST 到 Server 根地址
            json=payload,
            headers=headers,
            timeout=5,
        )
        resp.raise_for_status()
        console.print("[green]📡 ntfy 推送成功[/green]")
    except Exception as e:
        logger.warning(f"ntfy 推送失败: {e}")


def send_notification(
    signal: int,
    pattern: str,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    lot: float,
    order_no,
    order_status: str,
    image_name: str = "",
    success: bool = True,
):
    """统一推送入口：同时发送 Bark 和 ntfy 两路通知。"""
    kwargs = dict(
        signal       = signal,
        pattern      = pattern,
        entry_price  = entry_price,
        sl_price     = sl_price,
        tp_price     = tp_price,
        lot          = lot,
        order_no     = order_no,
        order_status = order_status,
        image_name   = image_name,
        success      = success,
    )
    # 🟢 这里已解开注释，确保一次信号能够同时推送到 Bark 和 ntfy
    send_bark_notification(**kwargs)
    send_ntfy_notification(**kwargs)


# ==========================================
# 测试入口
# ==========================================
if __name__ == "__main__":
    send_notification(
        signal       = 100,          # 100=做多  -100=做空
        pattern      = "2B",
        entry_price  = 3285.50,
        sl_price     = 3278.00,
        tp_price     = 3300.00,
        lot          = 0.01,
        order_no     = 123456789,
        order_status = "已成交",
        image_name   = "20260401/6fe9aec7-8a88-4578-8bfc-0de73131fcd6.png",  # {YYYYMMDD}/{uuid}.png
        success      = True,
    )