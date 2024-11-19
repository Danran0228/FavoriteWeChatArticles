from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import re

class WechatArticleCrawler:
    def get_article_content_selenium(self, url):
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # 无界面模式
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(20)
            
            driver.get(url)
            
            # 等待文章标题加载
            title_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "rich_media_title"))
            )
            title = title_element.text.strip()
            
            # 等待文章内容加载
            content_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "rich_media_content"))
            )
            content = content_element.text.strip()
            
            driver.quit()
            
            return {
                'title': title,
                'content': content,
                'url': url
            }
        except Exception as e:
            print(f"抓取文章失败: {str(e)}")
            if 'driver' in locals():
                driver.quit()
            return None
    
    def save_article(self, article):
        try:
            # 创建输出目录
            if not os.path.exists('articles'):
                os.makedirs('articles')
            
            # 使用标题作为文件名（去除非法字符）
            filename = re.sub(r'[\\/*?:"<>|]', "", article['title'])
            filepath = f"articles/{filename}.md"
            
            # 构建 Markdown 格式的内容
            markdown_content = f"""# {article['title']}

> 原文链接：{article['url']}

{article['content']}
"""
            
            # 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            print(f"文章已保存为 Markdown 文件: {filepath}")
        except Exception as e:
            print(f"保存文章失败: {str(e)}")

if __name__ == "__main__":
    crawler = WechatArticleCrawler()
    article_urls = [
        "https://mp.weixin.qq.com/s/7PRALCWfdV-iXjOOofOEkQ"
    ]
    
    for url in article_urls:
        print(f"正在抓取文章: {url}")
        # 使用 Selenium 方法
        article = crawler.get_article_content_selenium(url)
        if article:
            crawler.save_article(article)
        time.sleep(3)