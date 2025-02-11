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
            # 步骤1: 确定基础保存路径
            # 从配置文件获取默认保存路径
            base_dir = self.config.get_save_path()
            
            # 如果提供了自定义路径，则覆盖默认路径
            if custom_path:
                base_dir = custom_path
            
            # 标准化路径格式，处理路径分隔符
            base_dir = os.path.normpath(base_dir)
            
            # 确保基础目录存在，如不存在则创建
            if not os.path.exists(base_dir):
                os.makedirs(base_dir)
            
            # 步骤2: 清理文件名中的非法字符
            # 移除作者名称和文章标题中的特殊字符，确保文件名合法
            author_name = re.sub(r'[\\/*?:"<>|]', "", article['author'])
            article_title = re.sub(r'[\\/*?:"<>|]', "", article['title'])
            
            # 步骤3: 处理日期信息
            if article['publish_date']:
                # 如果文章包含发布日期，解析年月日
                date_prefix = article['publish_date']
                year = date_prefix[:4]      # 提取年份
                month = date_prefix[4:6]    # 提取月份
                day = date_prefix[6:8]      # 提取日期
            else:
                # 如果没有发布日期，使用当前时间
                now = datetime.now()
                date_prefix = now.strftime('%Y%m%d')
                year = now.strftime('%Y')
                month = now.strftime('%m')
                day = now.strftime('%d')
            
            # 获取目录编号的辅助函数
            def get_next_dir_number(parent_dir):
                """
                获取目录的下一个可用编号
                
                参数:
                    parent_dir: 父目录路径
                    
                返回:
                    str: 两位数的字符串编号（如："01", "02"等）
                """
                # 步骤1: 检查父目录是否存在
                if not os.path.exists(parent_dir):
                    return "01"  # 如果父目录不存在，返回初始编号"01"
                
                # 步骤2: 获取所有子目录
                existing_dirs = [d for d in os.listdir(parent_dir) 
                                if os.path.isdir(os.path.join(parent_dir, d))]
                
                # 步骤3: 如果没有子目录，返回初始编号
                if not existing_dirs:
                    return "01"
                # 输出已经存在的目录日志
                logger.info(f"已经存在的目录: {existing_dirs}")
                # 步骤4: 提取所有数字编号并找出最大值
                # - 通过split('.')分割目录名，获取编号部分
                # - 只处理以数字开头的目录名
                # - 将编号转换为整数进行比较
                max_num = max([int(d.split('.')[0]) for d in existing_dirs 
                              if d.split('.')[0].isdigit()])
                
                # 步骤5: 返回最大编号+1，并补齐为两位数
                return str(max_num + 1).zfill(2)
            
            # 获取或创建作者目录
            author_dirs = [d for d in os.listdir(base_dir) 
                          if os.path.isdir(os.path.join(base_dir, d)) 
                          and d.endswith(f".{author_name}")]
            if author_dirs:
                author_dir = author_dirs[0]  # 使用已存在的作者目录
            else:
                author_num = get_next_dir_number(base_dir)
                author_dir = f"{author_num}.{author_name}"
            
            # 获取或创建年份目录
            year_path = os.path.join(base_dir, author_dir)
            if not os.path.exists(year_path):
                os.makedirs(year_path)
            year_dirs = [d for d in os.listdir(year_path) 
                        if os.path.isdir(os.path.join(year_path, d)) 
                        and d.endswith(f".{year}")]
            if year_dirs:
                year_dir = year_dirs[0]  # 使用已存在的年份目录
            else:
                year_num = get_next_dir_number(year_path)
                year_dir = f"{year_num}.{year}"
            
            # 创建月份目录（保持原有格式）
            month_dir = f"{month.zfill(2)}.{int(month)}月"
            
            # 创建完整的目录路径
            article_dir = os.path.join(
                base_dir,
                author_dir,
                year_dir,
                month_dir
            )
            
            if not os.path.exists(article_dir):
                os.makedirs(article_dir)
            logger.info(f"创建路径: {article_dir}")
            
            # 在文章目录下创建images子目录用于存储图片
            images_dir = os.path.join(article_dir, 'images')
            if not os.path.exists(images_dir):
                os.makedirs(images_dir)

            # 生成文件名（日期+序号）
            # 获取当前目录下所有markdown文件
            existing_files = [f for f in os.listdir(article_dir) if f.endswith('.md')]
            
            # 获取当天的日期（两位数）
            current_day = day.zfill(2)
            
            # 筛选出当天的文件（文件名前两位匹配当天日期）
            day_files = [f for f in existing_files if f.startswith(current_day)]
            
            if day_files:
                # 获取当天最大序号
                # 从文件名中提取序号部分（第3-4位）并找出最大值
                max_seq = max([int(f.split('.')[0][2:4]) for f in day_files])
                seq = str(max_seq + 1).zfill(2)
            else:
                seq = "01"  # 当天第一个文件
            
            # 文件名格式：DDSS.标题.md
            # DD: 日期（两位）
            # SS: 序号（两位）
            # 例如：1102.文章名.md 表示11日第2篇文章
            filename = f"{current_day}{seq}.{article_title}.md"
            
            logger.info(f"生成文件名: {filename}")  # 添加日志记录
            
            # 步骤4: 处理文章中的图片
            # 创建字典存储原始图片URL和本地保存路径的映射
            image_map = {}
            logger.info(f"开始下载图片")
            for i, img_url in enumerate(article['image_urls']):
                try:
                    # 下载每张图片
                    response = requests.get(img_url, stream=True)
                    if response.status_code == 200:
                        # 使用时间戳生成唯一的图片文件名
                        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
                        img_filename = f"image_{timestamp}.jpg"
                        img_path = os.path.join(images_dir, img_filename)
                        # 保存图片到本地
                        with open(img_path, 'wb') as f:
                            f.write(response.content)
                        # 记录图片的相对路径，用于Markdown文件中的引用
                        image_map[img_url] = f"./images/{img_filename}"
                except Exception as e:
                    print(f"下载图片失败 {img_url}: {str(e)}")
            
            # 步骤6: 处理HTML内容
            content_html = article['content_html']
            soup = BeautifulSoup(content_html, 'html.parser')
            
            # 替换HTML中的图片标签为Markdown格式
            for img in soup.find_all('img'):
                src = img.get('data-src') or img.get('src')
                if src in image_map:
                    new_path = image_map[src]
                    # 创建Markdown格式的图片引用
                    markdown_img = f'\n\n![image]({new_path})\n\n'
                    img.replace_with(BeautifulSoup(markdown_img, 'html.parser'))
            
            content_html = str(soup)
            
            # 步骤7: 配置HTML到Markdown的转换器
            h = html2text.HTML2Text()
            h.ignore_links = False          # 保留链接
            h.ignore_images = False         # 保留图片
            h.ignore_emphasis = True       # 保留强调格式（如粗体、斜体）
            h.body_width = 0               # 不限制行宽
            h.unicode_snob = True          # 使用Unicode字符
            
            # 将HTML转换为Markdown格式
            content_markdown = h.handle(content_html)
            
            # 步骤8: 组装最终的Markdown内容
            markdown_content = f"""---
title: {article_title}
date: {article['publish_date']}
author: 
    name: {author_name}
---
# {article['title']}
{content_markdown}

> 原文链接：{article['url']}"""
            
            # 步骤9: 保存Markdown文件
            filepath = os.path.join(article_dir, f"{filename}")
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
