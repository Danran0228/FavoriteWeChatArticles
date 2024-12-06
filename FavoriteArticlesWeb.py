from flask import Flask, request, jsonify, make_response
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import os
import re
import requests
import html2text
from bs4 import BeautifulSoup
from datetime import datetime
import configparser
from logger_config import setup_logger
from multiprocessing import Pool
from functools import partial

# 设置日志
logger = setup_logger()

app = Flask(__name__)

# 设置 webdriver_manager 的缓存路径
os.environ['WDM_LOCAL'] = '1'  # 启用本地缓存
os.environ['WDM_PATH'] = os.path.join(os.getcwd(), "drivers")  # 设置缓存路径

class Config:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config_file = 'config.ini'
        self.load_config()

    def load_config(self):
        if os.path.exists(self.config_file):
            self.config.read(self.config_file, encoding='utf-8')
        else:
            # 创建默认配置
            self.config['Path'] = {'save_path': 'articles'}
            with open(self.config_file, 'w', encoding='utf-8') as f:
                self.config.write(f)

    def get_save_path(self):
        return self.config.get('Path', 'save_path', fallback='articles')

class WebDriverSingleton:
    _instance = None
    _driver = None

    @classmethod
    def get_driver(cls):
        if cls._driver is None:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            try:
                # 首先尝试直接使用系统安装的 Chrome
                cls._driver = webdriver.Chrome(
                    options=chrome_options
                )
            except Exception as e:
                logger.info("未找到系统Chrome驱动，正在下载...")
                # 如果失败，则使用 webdriver_manager 下载
                chrome_driver_path = ChromeDriverManager().install()
                cls._driver = webdriver.Chrome(
                    service=Service(chrome_driver_path),
                    options=chrome_options
                )
                
        return cls._driver

    @classmethod
    def quit_driver(cls):
        if cls._driver is not None:
            cls._driver.quit()
            cls._driver = None

class WechatArticleCrawler:
    def __init__(self):
        self.config = Config()

    def process_url(self, url):
        try:
            driver = WebDriverSingleton.get_driver()
            driver.get(url)
            
            # 等待文章标题加载
            title_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "rich_media_title"))
            )
            title = title_element.text.strip()
            
            # 等待并获取作者名称
            author_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "rich_media_meta_nickname"))
            )
            author = author_element.text.strip()

            # 等待文章发布时间加载
            publish_time_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "publish_time"))
            )
            publish_time = publish_time_element.text.strip()
            
            # 提取发布日期
            publish_date = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', publish_time)
            if publish_date:
                year = publish_date.group(1)
                month = publish_date.group(2).zfill(2)
                day = publish_date.group(3).zfill(2)
                publish_date = f"{year}{month}{day}"
            else:
                publish_date = None
            
            # 等待文章内容加载
            content_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "rich_media_content"))
            )
            
            # 获取HTML内容而不是纯文本
            content_html = content_element.get_attribute('innerHTML')
            
            # 获取所有图片的URL
            images = content_element.find_elements(By.TAG_NAME, "img")
            image_urls = [img.get_attribute('data-src') for img in images if img.get_attribute('data-src')]
            
            return {
                'title': title,
                'author': author,
                'publish_date': publish_date,
                'content_html': content_html,
                'image_urls': image_urls,
                'url': url
            }
        except Exception as e:
            raise e

    def get_article_content_selenium(self, url):
        try:
            return self.process_url(url)
        except Exception as e:
            print(f"抓取文章失败: {str(e)}")
            return None

    def save_article(self, article, custom_path=None):
        try:
            # 获取基础保存路径
            base_dir = self.config.get_save_path()
            
            if custom_path:
                # 如果提供了自定义路径,使用自定义路径
                base_dir = custom_path
            
            # 规范化路径
            base_dir = os.path.normpath(base_dir)
            
            # 确保目录存在
            if not os.path.exists(base_dir):
                os.makedirs(base_dir)
            
            # 清理作者名称和文章标题中的非法字符
            author_name = re.sub(r'[\\/*?:"<>|]', "", article['author'])
            article_title = re.sub(r'[\\/*?:"<>|]', "", article['title'])
            
            if article['publish_date']:
                date_prefix = article['publish_date']
            else:
                # 如果没有发布日期,则使用当前日期
                date_prefix = datetime.now().strftime('%Y%m%d')
            
            # 使用 os.path.join 来创建路径
            author_dir = os.path.join(base_dir, author_name)
            if not os.path.exists(author_dir):
                os.makedirs(author_dir)
            logger.info(f"创建路径: {author_dir}")
            # 创建 images 目录
            images_dir = os.path.join(author_dir, 'images')
            if not os.path.exists(images_dir):
                os.makedirs(images_dir)
            
            # 下载图片时使用正确的路径
            image_map = {}
            logger.info(f"开始下载图片")
            for i, img_url in enumerate(article['image_urls']):
                try:
                    response = requests.get(img_url, stream=True)
                    if response.status_code == 200:
                        # 使用时间戳命名图片
                        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
                        img_filename = f"image_{timestamp}.jpg"
                        img_path = os.path.join(images_dir, img_filename)
                        with open(img_path, 'wb') as f:
                            f.write(response.content)
                        # 在 Markdown 中使用相对路径
                        image_map[img_url] = f"./images/{img_filename}"
                except Exception as e:
                    print(f"下载图片失败 {img_url}: {str(e)}")
            
            content_html = article['content_html']
            soup = BeautifulSoup(content_html, 'html.parser')
            
            for img in soup.find_all('img'):
                src = img.get('data-src') or img.get('src')
                if src in image_map:
                    new_path = image_map[src]
                    markdown_img = f'\n\n![image]({new_path})\n\n'
                    img.replace_with(BeautifulSoup(markdown_img, 'html.parser'))
            
            content_html = str(soup)
            
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = False
            h.ignore_emphasis = False
            h.body_width = 0
            h.unicode_snob = True
            
            content_markdown = h.handle(content_html)
            
            markdown_content = f"""# {article['title']}

> 原文链接：{article['url']}

{content_markdown}"""
            
            # 创建文件路径
            filepath = os.path.join(author_dir, f"{date_prefix}-{article_title}.md")
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
                
            print(f"文章已保存为 Markdown 文件: {filepath}")
            return filepath
        except Exception as e:
            print(f"保存文章失败: {str(e)}")
            return None

@app.after_request
def set_response_headers(response):
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route('/save', methods=['GET'])
def save_article():
    try:
        logger.info("开始处理文章请求")
        url = request.args.get('url')
        if not url:
            logger.warning("未提供文章URL")
            return jsonify({'error': '请提供文章URL'}), 400
            
        save_path = request.args.get('path')
        if save_path:
            logger.info(f"使用自定义保存路径: {save_path}")
            # 确保路径是绝对路径
            save_path = os.path.abspath(save_path)
            
            # 检查路径是否合法
            if not os.access(os.path.dirname(save_path), os.W_OK):
                return jsonify({'error': '指定的保存路径无法访问或没有写入权限'}), 400
            
        logger.info(f"开始抓取文章: {url}")
        crawler = WechatArticleCrawler()
        article = crawler.get_article_content_selenium(url)
        
        if not article:
            logger.error("文章抓取失败")
            return jsonify({'error': '文章抓取失败'}), 500
            
        logger.info("开始保存文章")
        filepath = crawler.save_article(article, save_path)
        
        if not filepath:
            logger.error("文章保存失败")
            return jsonify({'error': '文章保存失败'}), 500
            
        logger.info(f"文章保存成功: {filepath}")
        return jsonify({
            'message': '文章保存成功',
            'filepath': filepath,
            'title': article['title']
        }), 200
        
    except Exception as e:
        logger.exception(f"处理请求时发生错误: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5001)
    finally:
        WebDriverSingleton.quit_driver()
