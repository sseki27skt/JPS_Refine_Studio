import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logger():
    # ログディレクトリの作成
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, 'cleansing_studio.log')
    
    # ロガーの初期化
    logger = logging.getLogger("CleansingStudio")
    logger.setLevel(logging.DEBUG)
    
    # ハンドラが複数登録されるのを防ぐ
    if not logger.handlers:
        # ファイルハンドラ (最大10MB, 5世代バックアップ)
        fh = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        
        # コンソールハンドラ
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        # フォーマッターの設定
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        logger.addHandler(fh)
        logger.addHandler(ch)
        
    return logger

# グローバルロガーインスタンス
logger = setup_logger()

# 統計分析用の専用関数
def log_stats(action: str, count: int, elapsed_sec: float, extra_info: str = ""):
    """
    後日分析しやすくするためのフォーマット固定ロガー関数。
    """
    msg = f"[STATS] {action} | Count: {count} | Time: {elapsed_sec:.2f}s | Info: {extra_info}"
    logger.info(msg)
