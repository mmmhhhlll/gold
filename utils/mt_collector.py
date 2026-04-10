import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

def _check_symbol(symbol: str) -> str:
    """内部辅助：确保品种存在"""
    if mt5.symbol_select(symbol, True):
        return symbol
    
    fallback = "XAUUSD"
    if mt5.symbol_select(fallback, True):
        return fallback
        
    raise ValueError(f"品种 {symbol} 不可用")

def _calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """计算 RSI 指标"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)  # 填充 NaN 为中性值 50

def _calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """计算 EMA 指标"""
    return series.ewm(span=period, adjust=False).mean()

def _calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """计算 ATR 指标"""
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())

    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr.fillna(0)

def _calculate_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    """计算布林带"""
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()

    bb_upper = sma + (std * std_dev)
    bb_lower = sma - (std * std_dev)
    bb_middle = sma

    return bb_upper.fillna(0), bb_middle.fillna(0), bb_lower.fillna(0)

def _get_klines(symbol: str, timeframe_str: str, limit: int) -> pd.DataFrame:
    """内部辅助：获取指定数量的 K 线数据（包含所有技术指标）"""
    tf_map = {
        'M5': mt5.TIMEFRAME_M5,
        'M15': mt5.TIMEFRAME_M15
    }

    # 从当前位置向前获取 limit 根棒线（多获取一些用于计算指标）
    rates = mt5.copy_rates_from_pos(symbol, tf_map[timeframe_str], 0, limit + 50)

    if rates is None or len(rates) == 0:
        return None

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')

    # 计算所有技术指标
    df['rsi'] = _calculate_rsi(df['close'], period=14)
    df['ema20'] = _calculate_ema(df['close'], period=20)
    df['ema50'] = _calculate_ema(df['close'], period=50)
    df['atr'] = _calculate_atr(df, period=14)
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = _calculate_bollinger_bands(df['close'], period=20)

    # 只返回需要的行数（去掉用于计算指标的额外数据）
    df = df.tail(limit)

    # 返回包含所有指标的数据
    return df[['time', 'open', 'high', 'low', 'close', 'tick_volume', 'rsi',
               'ema20', 'ema50', 'atr', 'bb_upper', 'bb_middle', 'bb_lower']]

def fetch_snapshot(symbol: str = "XAUUSDm", m15_limit: int = 30, m5_limit: int = 50) -> dict:
    """
    主入口函数
    :param symbol: 交易品种
    :param m15_limit: M15 图表获取的 K 线数量 (默认 30)
    :param m5_limit: M5 图表获取的 K 线数量 (默认 50)
    """
    data_pack = {'M15': None, 'M5': None, 'current_price': 0.0}
    
    if not mt5.initialize():
        print(f"❌ MT5 初始化失败: {mt5.last_error()}")
        return None

    try:
        real_symbol = _check_symbol(symbol)
        
        # 获取现价
        tick = mt5.symbol_info_tick(real_symbol)
        data_pack['current_price'] = tick.bid if tick else 0.0

        # 使用传入的参数获取数据
        data_pack['M15'] = _get_klines(real_symbol, 'M15', m15_limit)
        data_pack['M5']  = _get_klines(real_symbol, 'M5', m5_limit)

        return data_pack

    except Exception as e:
        print(f"❌ 数据获取异常: {e}")
        return None
        
    finally:
        mt5.shutdown()