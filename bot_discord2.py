import discord
from discord.ext import commands
import aiohttp
import io
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import asyncio
import time
import re

TOKEN = os.getenv('TOKEN')
EMAIL = os.getenv('EMAIL')
PASSWORD = os.getenv('PASSWORD')

def clean_link_from_post_link(post_link):
    """
    Làm sạch liên kết bằng cách:
    1. Loại bỏ phần 'mbasic.'.
    2. Giữ lại phần liên kết từ 'id=' đến cuối liên kết.
    
    :param post_link: Liên kết gốc để làm sạch.
    :return: Liên kết đã được làm sạch.
    """
    # Bước 1: Loại bỏ phần 'mbasic.'
    clean_link = post_link.replace("mbasic.", "")
    
    # Bước 2: Tìm vị trí của '&id='
    id_position = clean_link.find("&id=")
    
    if id_position != -1:
        # Bước 3: Trích xuất ID từ liên kết
        id_match = re.search(r'id=(\d+)', clean_link[id_position:])
        if id_match:
            id_value = id_match.group(1)
            clean_link = clean_link[:id_position + len("&id=") + len(id_value)]
    
    return clean_link

def sort_elements_by_position(elements):
    """
    Sắp xếp các phần tử Selenium dựa trên tọa độ (x, y) của chúng.
    
    :param elements: Danh sách các phần tử Selenium.
    :return: Danh sách các phần tử Selenium đã được sắp xếp theo thứ tự từ trên xuống dưới.
    """
    # Lấy tọa độ (x, y) của mỗi phần tử và sắp xếp dựa trên tọa độ y (vị trí dọc)
    sorted_elements = sorted(elements, key=lambda el: el.location['y'])
    
    return sorted_elements

def get_xpath_of_element(driver, element):
    return driver.execute_script("""
        function getElementXPath(element) {
            var paths = [];
            for (; element && element.nodeType === Node.ELEMENT_NODE; element = element.parentNode) {
                var siblingIndex = 1;
                for (var sibling = element.previousSibling; sibling; sibling = sibling.previousSibling) {
                    if (sibling.nodeType === Node.ELEMENT_NODE && sibling.nodeName === element.nodeName) {
                        siblingIndex++;
                    }
                }
                paths.unshift(element.nodeName.toLowerCase() + (siblingIndex > 1 ? "[" + siblingIndex + "]" : ""));
            }
            return paths.length ? "/" + paths.join("/") : null;
        }
        return getElementXPath(arguments[0]);
    """, element)


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Hàm đọc cookie từ file cookie.json và trả về danh sách cookies
def read_cookies_from_json(cookies):
    cookies = json.loads(cookies)
    
    selenium_cookies = []
    for cookie in cookies:
        selenium_cookie = {
            'name': cookie['name'],
            'value': cookie['value'],
            'domain': cookie['domain'],
            'path': cookie.get('path', '/'),
            'secure': cookie.get('secure', False),
            # Chuyển đổi `expirationDate` thành `expiry` cho Selenium (nếu có)
            'expiry': int(cookie['expirationDate']) if 'expirationDate' in cookie else None
        }
        # Loại bỏ trường 'expiry' nếu nó là None (Selenium không chấp nhận giá trị None cho trường này)
        if selenium_cookie['expiry'] is None:
            selenium_cookie.pop('expiry')
        
        selenium_cookies.append(selenium_cookie)

    return selenium_cookies

# Hàm tải ảnh từ URL
async def download_image(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                return io.BytesIO(data)

# Hàm để lưu hoặc so sánh bài post mới với tệp recent_post.json
def check_and_update_articles(articles, filename='recent_post.json', max_posts=5000):
    
    new_articles = [{'header': art['header'], 'paragraphs': art['paragraphs'], 'comment_links': art['comment_links'], 'first_image': art['first_image']} for art in articles]

    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            old_articles = json.load(f)

        old_articles_simplified = [{'header': art['header'], 'paragraphs': art['paragraphs']} for art in old_articles]
        new_posts =[]
        print(new_articles)
        for art  in new_articles:
            if {'header': art['header'], 'paragraphs': art['paragraphs']} not in old_articles_simplified:
                new_posts.append(art)


        if new_posts:
            print("Bài post mới phát hiện:")
            for i, post in enumerate(new_posts):
                print(f"Bài post mới {i + 1}: {json.dumps(post, ensure_ascii=False, indent=4)}")

            old_articles.extend(new_posts)

            if len(old_articles) > max_posts:
                old_articles = old_articles[-max_posts:]

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(old_articles, f, ensure_ascii=False, indent=4)

            return new_posts
        else:
            print("Không có bài post mới.")
            return []

    else:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(new_articles, f, ensure_ascii=False, indent=4)
        print("File recent_post.json được tạo và lưu bài viết.")
        return new_articles

def login_facebook(driver, username, password, timeout=100):
    try:
        # Wait for the email input field to be available
        # Find the email input field and enter the email
        email_input = driver.find_element(By.CSS_SELECTOR, '#email')
        email_input.send_keys(username)

        # Find the password input field and enter the password
        password_input = driver.find_element(By.CSS_SELECTOR, '#pass')
        password_input.send_keys(password)

        # Find the login button and click it
        login_button = driver.find_element(By.CSS_SELECTOR, '#loginbutton')
        login_button.click()


        print("Đăng nhập thành công và trang đã chuyển hướng!")
    except Exception as e:
        print(f"Error during Facebook login: {e}")

# Khởi tạo trình duyệt
def init_driver(EMAIL, PASSWORD):
    chrome_driver_path = "chromedriver.exe"
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--no-sandbox")
    service = Service(chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get("https://www.facebook.com/login")
        login_facebook(driver, EMAIL, PASSWORD)
        cookies = driver.get_cookies()

        for cookie in cookies:
            driver.add_cookie(cookie)
        driver.refresh()
    except Exception as e:
        print(f"Error initializing driver: {e}")
        driver.quit()

    return driver

# Hàm để lấy các bài viết từ Facebook và chuẩn hóa
def scrape_facebook_posts(driver, link):
    try:
        driver.get(link)

        articles = driver.find_elements(By.TAG_NAME, 'article')
        result = []

        for article in articles:
            header = ''
            combined_paragraphs = ''
            comment_links = []
            first_image = ''

            headers = article.find_elements(By.TAG_NAME, 'h1') + \
                          article.find_elements(By.TAG_NAME, 'h2') + \
                          article.find_elements(By.TAG_NAME, 'h3') + \
                          article.find_elements(By.TAG_NAME, 'h4') + \
                          article.find_elements(By.TAG_NAME, 'h5') + \
                          article.find_elements(By.TAG_NAME, 'h6')
            if headers:
                header = headers[0].text.strip()

            elements = article.find_elements(By.TAG_NAME, 'p') + article.find_elements(By.TAG_NAME, 'span')

            elements = [element for element in elements if element.tag_name == 'p' or \
                sum(1 for e in elements if get_xpath_of_element(driver, e) == get_xpath_of_element(driver, element) \
                and e.tag_name == 'span') > 1]

            elements = sort_elements_by_position(elements)

            text_elements = []
            for element in elements:
                xpath = get_xpath_of_element(driver, element)
                if 'header' not in xpath:
                    text_elements.append(element.text.strip())

            text_elements = list(set(text_elements))
            combined_paragraphs = '\n'.join(text_elements)

            images = article.find_elements(By.TAG_NAME, 'img')
            if images:
                first_image = images[0].get_attribute('src')

            article_links = article.find_elements(By.TAG_NAME, 'a')
            for link in article_links:
                link_text = link.text.strip().lower()
                if "comment" in link_text:
                    href  = link.get_attribute('href')
                    comment_links.append(href.replace('mbasic.',''))

            if not comment_links:
                continue
            article_dict = {
                'header': header,
                'paragraphs': combined_paragraphs.strip()[:4095],
                'comment_links': [clean_link_from_post_link(comment_links[0]) if comment_links else ''],
                'first_image': first_image
            }

            result.append(article_dict)

        return result
    except Exception as e:
        print(f"Error scraping Facebook posts: {e}")
        return []

async def send_new_posts_to_discord(channel, new_posts):
    for article in new_posts:
        # Tag @everyone
        mention_everyone = "@everyone "
        content = f"{mention_everyone}Có bài viết mới! {article['header'] if article['header'] else 'Không có tiêu đề'}"

        embed = discord.Embed(
            title=article['header'] if article['header'] else "Bài post không có tiêu đề",
            description=article['paragraphs'],
            color=discord.Color.blue(),
            url=article['comment_links'][0] if article['comment_links'][0] else None
        )

        if article['first_image']:
            image_data = await download_image(article['first_image'])
            if image_data:
                file = discord.File(fp=image_data, filename="image.jpg")
                embed.set_image(url="attachment://image.jpg")
                await channel.send(content=content, embed=embed, file=file)
        else:
            await channel.send(content=content, embed=embed)

# Hàm để quét bài viết và gửi

links_page = [
"https://mbasic.facebook.com/truongdhbachkhoa?v=timeline",
"https://mbasic.facebook.com/dhspkt.hcmute?v=timeline",
"https://mbasic.facebook.com/VNUHCM.US?v=timeline",
"https://mbasic.facebook.com/groups/voz.ver3",
"https://mbasic.facebook.com/groups/thosansaigon"
]
async def scrape_and_post(driver, channel):
    try:
        while True:
            for index, link in enumerate(links_page):
                print("~~~~ Đây là lần thứ:    "+str(index))
                articles = scrape_facebook_posts(driver, link)
                new_posts = check_and_update_articles(articles)
                if new_posts:
                    await send_new_posts_to_discord(channel, new_posts)

    except Exception as e:
        print(e)
    finally:
        driver.quit()

@client.event
async def on_ready():
    print(f"Bot {client.user} đã sẵn sàng!")
    channel = client.get_channel(1282376586888347658)
    
    driver = init_driver(EMAIL, PASSWORD)

    # Tạo một task cho việc scraping và gửi bài post lên Discord
    client.loop.create_task(scrape_and_post(driver, channel))

# Chạy bot
client.run(TOKEN)
