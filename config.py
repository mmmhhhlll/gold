import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from rich.logging import RichHandler
from rich.console import Console
import matplotlib.pyplot as plt
# ============================================
# 0. 全局工具实例化
# ============================================
# Console 无状态，可以直接初始化供全局使用
console = Console()

# 加载环境变量
load_dotenv()

# ============================================
# 1. 基础应用配置
# ============================================
MT5_CONFIG = {
    "login": int(os.getenv("MT5_LOGIN", 0)),
    "password": os.getenv("MT5_PASSWORD", ""),
    "server": os.getenv("MT5_SERVER", ""),
    "symbol": os.getenv("MT5_SYMBOL", "XAUUSD"),
    "deviation": int(os.getenv("MT5_DEVIATION", 20)),
    "magic": int(os.getenv("MT5_MAGIC", 100000)),
}

# ============================================
# 2. Bark 推送配置
# ============================================
BARK_KEY       = os.getenv("BARK_KEY", "")
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "")

# ============================================
# 3. ntfy 推送配置
# ============================================
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC  = os.getenv("NTFY_TOPIC", "gold_2_gold")
NTFY_TOKEN  = os.getenv("NTFY_TOKEN", "")   # 自建服务有 ACL 时填入，公共服留空

# ============================================
# 4. 图表保存配置
# ============================================
CHART_SAVE_DIR = os.getenv("CHART_SAVE_DIR", "charts")


# ============================================
# 2. LLM 配置
# ============================================
MODEL_NAME = "deepseek-chat"
LLM_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.deepseek.com")
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY")
LLM_TEMPERATURE = 0.1


# ============================================
# 3. 日志配置
# ============================================
LOG_NAME = "mt5_bot_logger"
LOG_FILE = "logs/application.log"
LOG_LEVEL = "INFO"


# ============================================
# 4. 内部初始化逻辑 (自动执行)
# ============================================
def _setup_logging():
    """
    内部函数：配置日志系统
    当此模块被 import 时会自动执行
    """
    # 1. 确保日志目录存在
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 2. 文件处理器 (带回滚功能)
    file_handler = RotatingFileHandler(
        filename=LOG_FILE,
        maxBytes=5*1024*1024, # 5MB
        backupCount=5,
        encoding='utf-8'
    )
    # 文件日志保持详细的时间格式
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))

    # 3. 控制台处理器 (Rich)
    # console=console 确保日志和 print 使用同一个控制台对象
    rich_handler = RichHandler(
        console=console, 
        rich_tracebacks=True,
        show_time=False  # Rich 自带时间显示略繁琐，通常设为 False 或使用默认
    )

    # 4. 应用配置
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        handlers=[file_handler, rich_handler],
        format="%(message)s", # RichHandler 只需 message，其他信息由它自己处理
        datefmt="[%X]"
    )

# ============================================
# 5. 执行初始化并导出 Logger
# ============================================
# 这一行保证了只要 import config，日志系统就立即就绪
_setup_logging()

# 导出这个 logger 供其他文件使用
logger = logging.getLogger(LOG_NAME)



plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei'] # 指定默认字体
plt.rcParams['axes.unicode_minus'] = False # 解决保存图像是负号'-'显示为方块的问题