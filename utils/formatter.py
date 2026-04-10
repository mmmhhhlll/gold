# utils/formatter.py

import pandas as pd
import json
import re
from typing import Optional, Dict, Any

def df_to_table_string(df: pd.DataFrame, max_rows: int = 20, include_indicators: bool = False) -> str:
    """
    将 DataFrame 转换为易读的表格字符串

    参数:
        df: 数据框
        max_rows: 最多显示的行数
        include_indicators: 是否包含技术指标（EMA、ATR、布林带）
    """
    if df is None or df.empty:
        return "No Data"

    # 拷贝并切片
    df = df.tail(max_rows).copy()

    # 格式化时间 (兼容 datetime 和 index)
    if 'time' in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df['time']):
            df['time_str'] = df['time'].dt.strftime("%H:%M")
        else:
            df['time_str'] = df['time'].astype(str)
    else:
        df['time_str'] = df.index.astype(str)

    # 检查可用的列
    has_volume = 'tick_volume' in df.columns
    has_rsi = 'rsi' in df.columns
    has_ema20 = 'ema20' in df.columns
    has_ema50 = 'ema50' in df.columns
    has_atr = 'atr' in df.columns
    has_bb = 'bb_upper' in df.columns and 'bb_lower' in df.columns

    lines = []

    # 根据 include_indicators 参数决定显示哪些列
    if include_indicators and has_ema20 and has_atr and has_bb:
        # 完整模式：包含所有技术指标（用于支撑阻力分析）
        lines.append("Time  | Open    | High    | Low     | Close   | Vol  | RSI  | EMA20   | EMA50   | ATR   | BB_Up   | BB_Low")
        lines.append("-" * 120)

        for _, row in df.iterrows():
            lines.append(
                f"{row['time_str']:<5} | {row['open']:<7.2f} | {row['high']:<7.2f} | "
                f"{row['low']:<7.2f} | {row['close']:<7.2f} | {int(row['tick_volume']):<4} | "
                f"{row['rsi']:<4.1f} | {row['ema20']:<7.2f} | {row['ema50']:<7.2f} | "
                f"{row['atr']:<5.2f} | {row['bb_upper']:<7.2f} | {row['bb_lower']:<7.2f}"
            )
    elif has_volume and has_rsi:
        # 简化模式：只包含 OHLC + Volume + RSI（用于信号生成）
        lines.append("Time  | Open    | High    | Low     | Close   | Volume | RSI")
        lines.append("-" * 70)

        for _, row in df.iterrows():
            lines.append(
                f"{row['time_str']:<5} | {row['open']:<7.2f} | {row['high']:<7.2f} | "
                f"{row['low']:<7.2f} | {row['close']:<7.2f} | {int(row['tick_volume']):<6} | {row['rsi']:<5.1f}"
            )
    else:
        # 最简模式：只有 OHLC
        lines.append("Time  | Open    | High    | Low     | Close")
        lines.append("-" * 45)

        for _, row in df.iterrows():
            lines.append(
                f"{row['time_str']:<5} | {row['open']:<7.2f} | {row['high']:<7.2f} | "
                f"{row['low']:<7.2f} | {row['close']:<7.2f}"
            )

    return "\n".join(lines)


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    从 LLM 的回复文本中提取并解析 JSON
    """
    try:
        # 1. 尝试直接解析
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            # 2. 尝试提取 ```json {...} ``` 代码块
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            
            # 3. 尝试提取最外层的大括号 {...}
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != -1:
                return json.loads(text[start:end])
                
        except Exception:
            pass
    return None


def format_account_info(info: dict) -> str:
    """格式化账户显示"""
    if not info:
        return "[red]账户数据不可用[/red]"
    
    return (
        f"💰 余额: [bold]${info.get('balance', 0):.2f}[/bold] | "
        f"净值: ${info.get('equity', 0):.2f} | "
        f"可用: ${info.get('free_margin', 0):.2f}"
    )


# ==========================================
# 补回缺失的函数，解决 ImportError
# ==========================================

def format_price(price: float, decimals: int = 2) -> str:
    """格式化价格"""
    return f"{price:.{decimals}f}"


def format_signal(signal: int) -> str:
    """格式化信号"""
    mapping = {1: "BUY", -1: "SELL", 0: "HOLD"}
    return mapping.get(signal, "UNKNOWN")