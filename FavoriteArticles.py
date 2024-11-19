import requests
from bs4 import BeautifulSoup
import json
import time

class WechatArticleCrawler:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    def get_article_content(self, url):
        try:
            response = requests.get(url, headers=self.headers)
            
            # 打印响应状态码和内容长度，用于调试
            print(f"响应状态码: {response.status_code}")
            print(f"响应内容长度: {len(response.text)}")
            
            # 检查响应状态
            if response.status_code != 200:
                print(f"请求失败，状态码: {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 获取文章标题
            title_element = soup.find('h1', class_='rich_media_title')
            if not title_element:
                print("未找到文章标题元素")
                return None
            title = title_element.text.strip()
            
            # 获取文章内容
            content_element = soup.find('div', class_='rich_media_content')
            if not content_element:
                print("未找到文章内容元素")
                return None
            content = content_element.text.strip()
            
            return {
                'title': title,
                'content': content,
                'url': url
            }
        except requests.exceptions.RequestException as e:
            print(f"网络请求错误: {str(e)}")
            return None
        except Exception as e:
            print(f"抓取文章失败: {str(e)}")
            return None
    
    def save_article(self, article_data, filename='favorite_articles.json'):
        try:
            # 读取现有数据
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    articles = json.load(f)
            except FileNotFoundError:
                articles = []
            
            # 添加新文章
            articles.append(article_data)
            
            # 保存更新后的数据
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(articles, f, ensure_ascii=False, indent=4)
                
            print(f"文章《{article_data['title']}》已保存")
        except Exception as e:
            print(f"保存文章失败: {str(e)}")


if __name__ == "__main__":
    # 使用示例
    crawler = WechatArticleCrawler()
    
    # 可以添加多个文章URL
    article_urls = [
        "https://mp.weixin.qq.com/s/7PRALCWfdV-iXjOOofOEkQ"
    ]
    
    for url in article_urls:
        print(f"正在抓取文章: {url}")
        article = crawler.get_article_content(url)
        if article:
            crawler.save_article(article)
        time.sleep(3)  # 添加延时，避免频繁请求
