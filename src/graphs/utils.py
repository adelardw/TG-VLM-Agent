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
from graphs.structured_outputs import WebStructuredOutputs
from beautylogger import logger
from datetime import datetime
from config import TIMEZONE


class WebChromeSearch:
    def __init__(self, main_url: str = 'https://www.google.com',
                 base_screen_path: str = 'screenshot.png'):

        self.base_screen_path = base_screen_path
        options = uc.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--force-device-scale-factor=1')

        prefs = {
            "profile.default_content_setting_values.geolocation": 2,
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False
        }
        options.add_experimental_option("prefs", prefs)
        options.add_argument('--lang=ru-RU')

        self.driver = uc.Chrome(use_subprocess=True, options=options)
        self.all_elements = []
        self.blacklist_urls = set()
        self.driver.maximize_window()
        self.driver.get(main_url)


    def encode_image_to_data_url(self):
        with open(self.base_screen_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:image/png;base64,{encoded_string}"

    def make_sreenshot(self):
        try:
            self.driver.execute_script("document.querySelectorAll('.agent-highlight-element').forEach(el => el.remove());")
        except Exception:
            pass
        self.driver.save_screenshot(self.base_screen_path)

    def get_llm_inputs(self, elements_list: list[dict[str, str | int]]):
        elements_text = "\n".join([f"  {el['id']}: {el['description']}" for el in elements_list])
        image_url = self.encode_image_to_data_url()
        return elements_text, image_url


    @staticmethod
    def _get_elements_js(assign_data_ids: bool):


        assign_str = 'true' if assign_data_ids else 'false'

        js_script  = f"""
        if ({assign_str}) {{
            document.querySelectorAll('[data-agent-id]').forEach(el => el.removeAttribute('data-agent-id'));
        }}

        const elements = document.querySelectorAll(
            'a, button, input, select, textarea, div, span, [onclick], [role="button"], [role="link"], ' +
            '[role="menuitem"], [role="option"], [role="checkbox"], [role="radio"], [tabindex="0"], ' +
            '[class*="button"], [class*="btn"], [class*="select"], [class*="control"], [class*="click"]'
        );

        const elementsData = [];
        let agentIdCounter = 1;

        elements.forEach((el, index) => {{
            const rect = el.getBoundingClientRect();
            const tagName = el.tagName.toLowerCase();
            const style = window.getComputedStyle(el);

            // --- ФИЛЬТР 1: Базовые проверки видимости и размера ---
            if (rect.width < 10 || rect.height < 10 || el.offsetParent === null || el.disabled || style.visibility === 'hidden' || style.opacity === '0' || style.display === 'none') {{ 
                return;
            }}

            // --- ФИЛЬТР 2: Проверка на 'div'/'span' (cursor: pointer) ---
            if (tagName === 'div' || tagName === 'span') {{
                if (style.cursor !== 'pointer') {{
                    return; // Это неинтерактивный div/span, пропускаем.
                }}
                // Пропускаем "пустые" div/span, которые могут быть просто обертками
                if (el.textContent.trim().length === 0 && el.children.length === 0) {{
                    return;
                }}
            }}

            // --- [НОВЫЙ] ФИЛЬТР 3: Проверка на перекрытие (OVERLAY) ---
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;

            // Проверяем, что центр элемента в пределах видимой области
            if (centerX < 0 || centerY < 0 || centerX > window.innerWidth || centerY > window.innerHeight) {{
                return;
            }}

            const topElement = document.elementFromPoint(centerX, centerY);

            if (topElement) {{
                // Проверяем, является ли наш элемент (el) тем самым верхним элементом
                // или его прямым родителем.
                let isTop = (el === topElement || el.contains(topElement));
                if (!isTop) {{
                    // Элемент 'el' чем-то перекрыт. Пропускаем его.
                    return;
                }}
            }} else {{
                // elementFromPoint вернул null (например, вне вьюпорта)
                return;
            }}
            // --- КОНЕЦ НОВОГО ФИЛЬТРА ---

            const agentId = agentIdCounter++;

            if ({assign_str}) {{
                el.setAttribute('data-agent-id', agentId);
            }}

            let href = (tagName.toLowerCase() === 'a') ? el.href : null;
            let description = "";
            const type = el.type ? el.type.toLowerCase() : "";

            // --- УЛУЧШЕННАЯ ЛОГИКА ОПИСАНИЙ ---
            if (tagName === 'a') {{ description = 'link';
            }} else if (tagName === 'button' || (tagName ==='input' && ['button', 'submit', 'reset'].includes(type)) || el.getAttribute('role') === 'button') {{ description = 'button';
            }} else if (style.cursor === 'pointer' && (tagName === 'div' || tagName === 'span')) {{
                description = 'custom button';
            }} else if (tagName === 'input' && ['text', 'search', 'email', 'password', 'tel', 'url'].includes(type)) {{ description = 'textfield';
            }} else if (tagName === 'textarea') {{ description = 'textarea';
            }} else if (tagName === 'select') {{ description = 'dropdown';
            }} else {{ description = tagName; }} // Fallback

            // Конкатенация строк
            if (el.innerText) {{ description += ': "' + el.innerText.substring(0, 50).trim() + '"';
            }} else if (el.value && !['button', 'submit', 'reset'].includes(type)) {{ description += '(value: "' + el.value.substring(0, 50).trim() + '")';
            }} else if (el.placeholder) {{ description += '(placeholder: "' + el.placeholder.substring(0, 50).trim() + '")';
            }} else if (el.ariaLabel) {{ description += '(label: "' + el.ariaLabel.substring(0, 50).trim() + '")'; }}

            elementsData.push({{
                id: agentId,
                description: description,
                tag: tagName,
                href: href,
                rect: {{ left: rect.left, top: rect.top, width: rect.width, height: rect.height }}
            }});
        }});
        return JSON.stringify(elementsData);
        """
        return js_script

    def execute_invisivle_analysis(self):
        """Только анализирует страницу (для 'selection'). Не присваивает ID."""
        elements = self.driver.execute_script(self._get_elements_js(assign_data_ids=False))
        return json.loads(elements)

    def execute_invisivle_apply_ids(self):
        """Анализирует И ПРИСВАИВАЕТ ID (для 'route', прямо перед 'action')."""
        elements = self.driver.execute_script(self._get_elements_js(assign_data_ids=True))
        return json.loads(elements)


    def filter_by_blacklist(self, elements: list[dict[str, str | int]]):
        filtered_list = []
        for el in elements:
            if el.get('href') and el['href'] in self.blacklist_urls:
                continue
            filtered_list.append(el)
        return filtered_list

    def get_drawning_elements(self, full_elements: list[dict[str, str | int]],
                                    filtred_elements: set[int]):
        drawning = []
        without_rect = []
        for el in full_elements:
            if el['id'] in filtred_elements:
                drawning.append(el)
                without_rect.append({
                "id": el["id"],
                "description": el["description"],
                "tag": el["tag"]})
        return drawning, without_rect


    def draw_highlights_on_image(self, elements: list[dict[str, str | int]]):


        with Image.open(self.base_screen_path) as img:
            draw = ImageDraw.Draw(img)
            try: font = ImageFont.truetype("arial.ttf", 20)
            except IOError: font = ImageFont.load_default()
            for el in elements:
                rect = el['rect']

                x1, y1 = rect['left'], rect['top']

                x2, y2 = x1 + rect['width'], y1 + rect['height']

                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(img.width, x2), min(img.height, y2)
                if x2 <= x1 or y2 <= y1: continue

                draw.rectangle([x1, y1, x2, y2], outline="red", width=3)
                draw.text((x1 + 5, y1 + 5), str(el['id']), fill="red", font=font)
            img.save(self.base_screen_path)


    def get_elements_without_rect(self, elements: list[dict[str, str | int]]):
        simplified_list = []
        for el in elements:
            simplified_list.append({
                "id": el["id"],
                "description": el["description"],
                "tag": el.get("tag", "unknown")
            })
        return simplified_list

    def find_element_by_agent_id(self, element_id: int) -> Optional[WebElement]:
        if element_id is None:
            logger.warning("Агент прислал element_id: None. Действие будет пропущено.")
            return None

        try:
            return self.driver.find_element(By.CSS_SELECTOR, f'[data-agent-id="{element_id}"]')
        except Exception as e:
            logger.error(f"Не удалось найти элемент с data-agent-id={element_id} (NoSuchElementException).")
            return None
        except Exception as e:

            logger.error(f"Критическая ошибка при поиске [data-agent-id={element_id}]: {e}")
            return None


    def action(self, action_config: WebStructuredOutputs):
        action = action_config.action
        reason = action_config.reason
        element_id = action_config.element_id
        text_to_type = action_config.text
        direction = action_config.direction

        if action == "done":
            logger.info(f"Агент решил 'done' для этой страницы: {reason}")
            return


        elif action == "back":
            current_url_to_blacklist = self.driver.current_url
            logger.info(f"Добавляю в черный список: {current_url_to_blacklist}")
            self.blacklist_urls.add(current_url_to_blacklist)
            self.driver.back()

        elif action == "scroll":
            if direction == "down":
                self.driver.execute_script("window.scrollBy(0, window.innerHeight);")
            else:
                self.driver.execute_script("window.scrollBy(0, -window.innerHeight);")

        else:
            # click, type, submit
            target_element = self.find_element_by_agent_id(element_id)

            if not target_element:
                logger.error(f"Действие '{action}' не может быть выполнено: элемент {element_id} не найден. Пропускаю.")
                return

            if action == "submit":
                target_element.send_keys(Keys.RETURN)

            elif action == "click":
                try:
                    target_element.click()
                except Exception as e:
                    logger.warning(f"Нативный .click() не удался ({e}). Пробую JS-клик...")
                    try:
                        self.driver.execute_script("arguments[0].click();", target_element)
                    except Exception as e2:
                        logger.error(f"JS-клик также не удался ({e2}). Клик пропущен.")
                        pass
                except Exception as e_other:
                    logger.error(f"Нативный .click() провалился: {e_other}. Пропускаю.")
                    pass

            elif action == "type":
                try:
                    target_element.clear()
                    target_element.send_keys(text_to_type)
                except Exception as e:
                    logger.error(f"Агент попытался ввести текст '{text_to_type}' в элемент {element_id}, который не является полем ввода. Пропускаю.")
                    pass
                except Exception as e_other:
                    logger.error(f"Действие 'type' провалилось: {e_other}. Пропускаю.")
                    pass


class DDGSSeleniumSearch:

    def __init__(self,
                 base_screen_path: str = 'screenshot.png'):

        self.base_screen_path = base_screen_path
        options = uc.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--force-device-scale-factor=1') # Фикс для Retina

        prefs = {
            "profile.default_content_setting_values.geolocation": 2,
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False
        }
        options.add_experimental_option("prefs", prefs)
        options.add_argument('--lang=ru-RU')

        self.driver = uc.Chrome(use_subprocess=True, options=options)
        self.all_elements = []
        self.blacklist_urls = set()
        self.driver.maximize_window()
        self.search_engine = DDGS()
        # Инициализируем links здесь, чтобы get_links мог его перезаписать
        self.links = deque() 


    def get_links(self, query: str):
        self.links = deque(self.search_engine.text(query))
        return self.links

    def open_link(self):
        if len(self.links) > 0:
            current_links = self.links.popleft()
            logger.info(f"Открываю ссылку: {current_links['href']}")
            self.driver.get(current_links['href'])
        else:
            logger.warning("Ссылки закончились, не могу открыть.")

    def encode_image_to_data_url(self):
        with open(self.base_screen_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:image/png;base64,{encoded_string}"

    def make_sreenshot(self):
        """Делает чистый скриншот."""
        try:
            self.driver.execute_script("document.querySelectorAll('.agent-highlight-element').forEach(el => el.remove());")
        except Exception:
            pass
        self.driver.save_screenshot(self.base_screen_path)

    def get_llm_inputs(self, elements_list: list[dict[str, str | int]]):
        elements_text = "\n".join([f"  {el['id']}: {el['description']}" for el in elements_list])
        image_url = self.encode_image_to_data_url()
        return elements_text, image_url


    @staticmethod
    def _get_elements_js(assign_data_ids: bool):


        assign_str = 'true' if assign_data_ids else 'false'

        js_script  = f"""
        if ({assign_str}) {{
            document.querySelectorAll('[data-agent-id]').forEach(el => el.removeAttribute('data-agent-id'));
        }}

        const elements = document.querySelectorAll(
            'a, button, input, select, textarea, div, span, [onclick], [role="button"], [role="link"], ' +
            '[role="menuitem"], [role="option"], [role="checkbox"], [role="radio"], [tabindex="0"], ' +
            '[class*="button"], [class*="btn"], [class*="select"], [class*="control"], [class*="click"]'
        );

        const elementsData = [];
        let agentIdCounter = 1;

        elements.forEach((el, index) => {{
            const rect = el.getBoundingClientRect();
            const tagName = el.tagName.toLowerCase();
            const style = window.getComputedStyle(el);

            // --- ФИЛЬТР 1: Базовые проверки видимости и размера ---
            if (rect.width < 10 || rect.height < 10 || el.offsetParent === null || el.disabled || style.visibility === 'hidden' || style.opacity === '0' || style.display === 'none') {{ 
                return;
            }}

            // --- ФИЛЬТР 2: Проверка на 'div'/'span' (cursor: pointer) ---
            if (tagName === 'div' || tagName === 'span') {{
                if (style.cursor !== 'pointer') {{
                    return; // Это неинтерактивный div/span, пропускаем.
                }}
                // Пропускаем "пустые" div/span, которые могут быть просто обертками
                if (el.textContent.trim().length === 0 && el.children.length === 0) {{
                    return;
                }}
            }}

            // --- [НОВЫЙ] ФИЛЬТР 3: Проверка на перекрытие (OVERLAY) ---
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;

            // Проверяем, что центр элемента в пределах видимой области
            if (centerX < 0 || centerY < 0 || centerX > window.innerWidth || centerY > window.innerHeight) {{
                return;
            }}

            const topElement = document.elementFromPoint(centerX, centerY);

            if (topElement) {{
                // Проверяем, является ли наш элемент (el) тем самым верхним элементом
                // или его прямым родителем.
                let isTop = (el === topElement || el.contains(topElement));
                if (!isTop) {{
                    // Элемент 'el' чем-то перекрыт. Пропускаем его.
                    return;
                }}
            }} else {{
                // elementFromPoint вернул null (например, вне вьюпорта)
                return;
            }}
            // --- КОНЕЦ НОВОГО ФИЛЬТРА ---

            const agentId = agentIdCounter++;

            if ({assign_str}) {{
                el.setAttribute('data-agent-id', agentId);
            }}

            let href = (tagName.toLowerCase() === 'a') ? el.href : null;
            let description = "";
            const type = el.type ? el.type.toLowerCase() : "";

            // --- УЛУЧШЕННАЯ ЛОГИКА ОПИСАНИЙ ---
            if (tagName === 'a') {{ description = 'link';
            }} else if (tagName === 'button' || (tagName ==='input' && ['button', 'submit', 'reset'].includes(type)) || el.getAttribute('role') === 'button') {{ description = 'button';
            }} else if (style.cursor === 'pointer' && (tagName === 'div' || tagName === 'span')) {{
                description = 'custom button';
            }} else if (tagName === 'input' && ['text', 'search', 'email', 'password', 'tel', 'url'].includes(type)) {{ description = 'textfield';
            }} else if (tagName === 'textarea') {{ description = 'textarea';
            }} else if (tagName === 'select') {{ description = 'dropdown';
            }} else {{ description = tagName; }} // Fallback

            // Конкатенация строк
            if (el.innerText) {{ description += ': "' + el.innerText.substring(0, 50).trim() + '"';
            }} else if (el.value && !['button', 'submit', 'reset'].includes(type)) {{ description += '(value: "' + el.value.substring(0, 50).trim() + '")';
            }} else if (el.placeholder) {{ description += '(placeholder: "' + el.placeholder.substring(0, 50).trim() + '")';
            }} else if (el.ariaLabel) {{ description += '(label: "' + el.ariaLabel.substring(0, 50).trim() + '")'; }}

            elementsData.push({{
                id: agentId,
                description: description,
                tag: tagName,
                href: href,
                rect: {{ left: rect.left, top: rect.top, width: rect.width, height: rect.height }}
            }});
        }});
        return JSON.stringify(elementsData);
        """
        return js_script

    def execute_invisivle_analysis(self):
        """Только анализирует страницу (для 'selection'). Не присваивает ID."""
        elements = self.driver.execute_script(self._get_elements_js(assign_data_ids=False))
        return json.loads(elements)

    def execute_invisivle_apply_ids(self):
        """Анализирует И ПРИСВАИВАЕТ ID (для 'route', прямо перед 'action')."""
        elements = self.driver.execute_script(self._get_elements_js(assign_data_ids=True))
        return json.loads(elements)


    def filter_by_blacklist(self, elements: list[dict[str, str | int]]):
        filtered_list = []
        for el in elements:
            if el.get('href') and el['href'] in self.blacklist_urls:
                continue
            filtered_list.append(el)
        return filtered_list

    def get_drawning_elements(self, full_elements: list[dict[str, str | int]],
                                    filtred_elements: set[int]):
        drawning = []
        without_rect = []
        for el in full_elements:
            if el['id'] in filtred_elements:
                drawning.append(el)
                without_rect.append({
                "id": el["id"],
                "description": el["description"],
                "tag": el["tag"]})
        return drawning, without_rect


    def draw_highlights_on_image(self, elements: list[dict[str, str | int]]):


        with Image.open(self.base_screen_path) as img:
            draw = ImageDraw.Draw(img)
            try: font = ImageFont.truetype("arial.ttf", 20)
            except IOError: font = ImageFont.load_default()
            for el in elements:
                rect = el['rect']

                x1, y1 = rect['left'], rect['top']

                x2, y2 = x1 + rect['width'], y1 + rect['height']

                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(img.width, x2), min(img.height, y2)
                if x2 <= x1 or y2 <= y1: continue

                draw.rectangle([x1, y1, x2, y2], outline="red", width=3)
                draw.text((x1 + 5, y1 + 5), str(el['id']), fill="red", font=font)
            img.save(self.base_screen_path)


    def get_elements_without_rect(self, elements: list[dict[str, str | int]]):
        simplified_list = []
        for el in elements:
            simplified_list.append({
                "id": el["id"],
                "description": el["description"],
                "tag": el.get("tag", "unknown")
            })
        return simplified_list

    def find_element_by_agent_id(self, element_id: int) -> Optional[WebElement]:
        if element_id is None:
            logger.warning("Агент прислал element_id: None. Действие будет пропущено.")
            return None

        try:
            return self.driver.find_element(By.CSS_SELECTOR, f'[data-agent-id="{element_id}"]')
        except Exception as e:
            # Эта ошибка ожидаема, если элемент исчез
            logger.error(f"Не удалось найти элемент с data-agent-id={element_id} (NoSuchElementException).")
            return None
        except Exception as e:
            # Другие, более серьезные ошибки
            logger.error(f"Критическая ошибка при поиске [data-agent-id={element_id}]: {e}")
            return None


    def action(self, action_config: WebStructuredOutputs):
        action = action_config.action
        reason = action_config.reason
        element_id = action_config.element_id
        text_to_type = action_config.text
        direction = action_config.direction

        if action == "done":
            logger.info(f"Агент решил 'done' для этой страницы: {reason}")
            return

        elif action == "back":
            current_url_to_blacklist = self.driver.current_url
            logger.info(f"Добавляю в черный список: {current_url_to_blacklist}")
            self.blacklist_urls.add(current_url_to_blacklist)
            self.driver.back()

            if self.driver.current_url == 'chrome://new-tab-page/':
                 self.open_link()


        elif action == "scroll":
            if direction == "down":
                self.driver.execute_script("window.scrollBy(0, window.innerHeight);")
            else:
                self.driver.execute_script("window.scrollBy(0, -window.innerHeight);")

        else:
            # click, type, submit
            target_element = self.find_element_by_agent_id(element_id)

            if not target_element:
                logger.error(f"Действие '{action}' не может быть выполнено: элемент {element_id} не найден. Пропускаю.")
                return

            if action == "submit":
                target_element.send_keys(Keys.RETURN)

            elif action == "click":
                try:
                    target_element.click()
                except Exception as e:
                    logger.warning(f"Нативный .click() не удался ({e}). Пробую JS-клик...")
                    try:
                        self.driver.execute_script("arguments[0].click();", target_element)
                    except Exception as e2:
                        logger.error(f"JS-клик также не удался ({e2}). Клик пропущен.")
                        pass
                except Exception as e_other:
                    logger.error(f"Нативный .click() провалился: {e_other}. Пропускаю.")
                    pass

            elif action == "type":
                try:
                    target_element.clear()
                    target_element.send_keys(text_to_type)
                except Exception as e: # Ловим конкретную ошибку
                    logger.error(f"Агент попытался ввести текст '{text_to_type}' в элемент {element_id}, который не является полем ввода. Пропускаю.")
                    pass
                except Exception as e_other:
                    logger.error(f"Действие 'type' провалилось: {e_other}. Пропускаю.")
                    pass

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
    results = search_engine.text(search_query, region="ru-ru", max_results=3)
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
        
        if key != 'image_url':
            contents.append({"type": "text",'text': value})
        else:
            image_urls = value if isinstance(value, list) else [value]
            for link in image_urls:
                contents.append({"type": "image_url", "image_url": {"url": link}})
                

    messages = []
    if sys_prompt:
        messages.append(SystemMessage(content=sys_prompt))
    
    messages.extend(history)
    if contents:
        messages.append(HumanMessage(content=contents))
    
    return messages


def prepare_cache_messages_to_langchain(history_list: list[dict[str, Any]]):
    if history_list:
        langchain_history = [SystemMessage(content='--- Начало Истории Сообщений ---')]

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
        
        langchain_history.append(SystemMessage(content='--- Конец Истории Сообщений ---'))
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



