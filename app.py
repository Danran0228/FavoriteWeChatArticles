from FavoriteArticlesWeb import app
from waitress import serve
import logging

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        logger.info("正在启动应用服务器...")
        serve(app, host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"服务器启动失败: {str(e)}") 