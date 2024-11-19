from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import re
import requests
import html2text
from bs4 import BeautifulSoup

class WechatArticleCrawler:
    def get_article_content_selenium(self, url):
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
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
            
            # 获取HTML内容而不是纯文本
            content_html = content_element.get_attribute('innerHTML')
            
            # 获取所有图片的URL
            images = content_element.find_elements(By.TAG_NAME, "img")
            image_urls = [img.get_attribute('data-src') for img in images if img.get_attribute('data-src')]
            
            driver.quit()
            
            return {
                'title': title,
                'content_html': content_html,
                'image_urls': image_urls,
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
            
            # 为每篇文章创建单独的目录
            filename = re.sub(r'[\\/*?:"<>|]', "", article['title'])
            article_dir = f"articles/{filename}"
            if not os.path.exists(article_dir):
                os.makedirs(article_dir)
            
            # 创建images目录
            images_dir = f"{article_dir}/images"
            if not os.path.exists(images_dir):
                os.makedirs(images_dir)
            
            # 下载所有图片并创建URL映射
            image_map = {}
            for i, img_url in enumerate(article['image_urls']):
                try:
                    response = requests.get(img_url, stream=True)
                    if response.status_code == 200:
                        img_filename = f"image_{i+1}.jpg"
                        img_path = f"{images_dir}/{img_filename}"
                        with open(img_path, 'wb') as f:
                            f.write(response.content)
                    image_map[img_url] = f"./images/{img_filename}"  # 使用 ./ 开头的相对路径
                except Exception as e:
                    print(f"下载图片失败 {img_url}: {str(e)}")
            
            # 处理HTML内容，直接将img标签转换为Markdown格式
            content_html = article['content_html']
            
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(content_html, 'html.parser')
            
            # 找到所有图片标签并替换为Markdown格式
            for img in soup.find_all('img'):
                src = img.get('data-src') or img.get('src')
                if src in image_map:
                    new_path = image_map[src]
                    # 创建Markdown格式的图片引用
                    markdown_img = f'\n\n![image]({new_path})\n\n'
                    img.replace_with(BeautifulSoup(markdown_img, 'html.parser'))
            
            # 获取处理后的HTML
            content_html = str(soup)
            
            # 创建html2text实例并配置
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = False
            h.ignore_emphasis = False
            h.body_width = 0
            h.unicode_snob = True
            
            # 将HTML转换为Markdown格式
            content_markdown = h.handle(content_html)
            
            # 构建完整的Markdown内容
            markdown_content = f"""# {article['title']}

> 原文链接：{article['url']}

{content_markdown}"""
            
            # 保存Markdown文件
            filepath = f"{article_dir}/article.md"
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