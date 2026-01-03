from urllib.parse import urlparse
import base64
from collections import deque
from PIL import Image, ImageDraw, ImageFont
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from typing import Optional, Literal
import re
import json
import tldextract
from ddgs import DDGS
import requests
from bs4 import BeautifulSoup
import random
import undetected_chromedriver as uc
from undetected_chromedriver.webelement import WebElement

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys


import base64
from typing import Literal, Optional, List, Union, Dict, Any
from beautylogger import logger
from datetime import datetime
from config import TIMEZONE



def is_url_safe(url: str):
    parsed = urlparse(url)

    if parsed.scheme not in ['http', 'https']:
        return False

    domain_info = tldextract.extract(parsed.netloc)
    domain = f"{domain_info.domain}.{domain_info.suffix}"


    dangerous_domains = [
        'exe-download.com', 'free-cracks.org',
        'adult-site.com', 'bitcoin-miner.net'
    ]

    if domain in dangerous_domains:
        return False

    suspicious_patterns = [
        r'\.exe$', r'\.zip$', r'\.rar$', r'\.msi$',
        r'\/download\/', r'\/install\/', r'\/crack\/',
        r'\/keygen\/', r'\/torrent\/'
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, url, re.I):
            return False

    return True

def parse_site(url: str):
    '''
    Парсит сайт по заданной ссылке (url)
    '''

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.5',
                            'Accept-Encoding': 'gzip, deflate',
                            'DNT': '1',
                            'Connection': 'keep-alive',
                            'Upgrade-Insecure-Requests': '1',
                            'Sec-Fetch-Dest': 'document',
                            'Sec-Fetch-Mode': 'navigate',
                            'Sec-Fetch-Site': 'none',
                            'Sec-Fetch-User': '?1'}

    headers['User-Agent'] = random.choice(user_agents)
    try:
        resp = requests.get(url, headers=headers,timeout=120)
        bs = BeautifulSoup(resp.content,'html.parser')
        for tag in bs(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            tag.decompose()

        main_content = (bs.find('main') or
                        bs.find('article') or
                        bs.find('div', {'id': 'content'}) or
                        bs.find('div', {'class': 'content'}) or
                        bs.find('div', {'id': 'main-content'}) or
                        bs.find('div', {'class': 'post-body'}) or
                        bs.find('div', {'class': 'article-body'}))

        if not main_content:
            main_content = bs.body

        if not main_content:
            return None


        text = main_content.get_text(separator=' ', strip=True)
        return text
    except Exception as e:
        return ''




def search(search_query: str):
    '''
    По поисковому запросу search_query находит топ результатов поисковой выдачи
    '''
    search_engine = DDGS()
    results = search_engine.text(search_query, region="wt-wt", max_results=3)
    texts = []
    for results in results:
        href = results['href']
        checl_url = is_url_safe(href)
        if not checl_url:
            continue
        for l in {'youtube','video','shorts','instagram','inst','meta','facebook','twitter',
                  'vk','t.me'}:
            if l in href:
                next_link = True
                break
            else:
                next_link = False

        if next_link:
            continue
        else:
            text = parse_site(href)
            texts.append(text)

    return texts




def image_text_prompt(sys_prompt: Optional[str], input_dict: dict, history_key: str ):

    contents = []
    history = input_dict.get(history_key, [])
    
    for key, value in input_dict.items():

        if key == history_key:
            continue
        
        if (key != 'image_url') & (key != 'input_audio') & (key != 'video_url'):
            contents.append({"type": "text",'text': value})

        elif key == 'image_url' or key == 'video_url':
            urls = value if isinstance(value, list) else [value]
            for link in urls:
                contents.append({"type": key, key: {"url": link}})
        
        elif key == 'input_audio':
            urls = value if isinstance(value, list) else [value]
            for link in urls:
                contents.append({"type": key, key: {"data": link['data'],
                                                    "format": link['format']}})
                

    messages = []
    if sys_prompt:
        messages.append(SystemMessage(content=sys_prompt))
    
    messages.extend(history)
    if contents:
        messages.append(HumanMessage(content=contents))
    
    return messages


def prepare_cache_messages_to_langchain(history_list: list[dict[str, Any]],
                                        local: bool = True):
    if history_list:
        scope = "Локальная память" if local else "Глобальная память"
        langchain_history = [SystemMessage(content=f'--- Начало Истории Сообщений ({scope}) ---')]

        for i, message in enumerate(history_list):
            role = message.get('role')
            content_str = message.get('content', '[Нет текста]')
            metadata = message.get('metadata') or {}

            time_str = f"Time: {metadata['time']} | " if metadata.get('time') else ""
            indexed_content = f"[MSG_ID: {i}] | {time_str}{content_str}"

            images = metadata.get('images')
            content_blocks = []

            if images:
                content_blocks = [{"type": "text", "text": indexed_content}]

                if isinstance(images, list):
                    for img_url in images:
                        content_blocks.append({
                            "type": "image_url",
                            "image_url": {"url": img_url} 
                        })
                else:
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": images}
                    })
            else:
                content_blocks = indexed_content


            if role == 'system':
                langchain_history.append(SystemMessage(content=content_blocks))

            elif role in {'assistant'}:
                langchain_history.append(AIMessage(content=content_blocks))

            elif role in {'human', 'user'}:
                langchain_history.append(HumanMessage(content=content_blocks))
        
        langchain_history.append(SystemMessage(content=f'--- Конец Истории Сообщений ({scope}) ---'))
        return langchain_history
    else:
        return []
    


def format_history_for_llm(history_list: List[Union[str, Dict]],
                           wonder_list: List[Union[str, Dict]]) -> str:
    """
    Превращает список (строк или словарей) в текст вида:
    User: Привет
    Assistant: Привет!
    """
    dialogue_text = ""

    for item in history_list:
        try:
            if isinstance(item, dict):
                data = item
            else:
                data = json.loads(item)
            
            role = data.get("role", "unknown").capitalize() 
            content = data.get("content", "")
            dialogue_text += f"{role}: {content}\n"
        except (json.JSONDecodeError, TypeError):
            continue
    
    for item in wonder_list:
        try:

            if isinstance(item, dict):
                data = item
            else:
                data = json.loads(item)

            content = data.get("content", "")
            dialogue_text += f">>> INSIGHT (Инсайт): {content}\n"
        except (json.JSONDecodeError, TypeError):
            continue
        
    return dialogue_text

user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 15; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Windows NT 10.0; WOW64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15.0; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Mozilla/5.0 (Android 15; Mobile; rv:130.0) Gecko/130.0 Firefox/130.0",
    "Mozilla/5.0 (Android 14; Mobile; rv:129.0) Gecko/129.0 Firefox/129.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 14; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36"
]



