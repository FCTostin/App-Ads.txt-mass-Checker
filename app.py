import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import re

# --- 1. Настройка страницы ---
st.set_page_config(
    page_title="App-ads.txt Checker", 
    layout="wide", 
    page_icon="🛡️"
)

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    .stTextArea textarea { background-color: #262730; color: #ffffff; border: 1px solid #444; }
    div[data-testid="stDataFrame"] { background-color: #262730; }
    </style>
""", unsafe_allow_html=True)

st.title("🛡️ App-ads.txt Checker")
st.markdown("Verifies file availability (checking www/non-www) and counts **valid IAB ad records**.")

# --- 2. Настройка сессии (имитация браузера) ---
def get_session():
    session = requests.Session()
    # Максимально похожие на настоящий Chrome заголовки
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Ch-Ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
    })
    return session

# --- 3. Очистка домена из ввода ---
def clean_domain(url_input):
    # Убираем кавычки и лишние пробелы
    url_input = url_input.strip().replace('"', '').replace("'", "")
    
    # Добавляем схему для парсинга, если её нет
    if not url_input.startswith(("http://", "https://")):
        url_input = "http://" + url_input
        
    try:
        parsed = urlparse(url_input)
        domain = parsed.netloc if parsed.netloc else parsed.path.split('/')[0]
        # Убираем www. в начале, чтобы алгоритм перебора сам решал, добавлять его или нет
        return domain.lower().replace("www.", "").strip()
    except:
        return url_input

# --- 4. Парсинг содержимого файла (IAB Logic) ---
def count_valid_lines(content):
    valid_count = 0
    
    # 1. Удаляем BOM (Byte Order Mark), который часто ломает первую строку
    content = content.replace('\ufeff', '')
    
    # 2. Нормализуем переносы строк (Windows/Unix)
    lines = content.replace('\r\n', '\n').replace('\r', '\n').splitlines()
    
    for line in lines:
        # Убираем комментарии
        clean_line = line.split('#')[0].strip()
        
        if not clean_line:
            continue
            
        parts = [p.strip() for p in clean_line.split(',')]
        
        # Стандарт IAB: Domain, Account ID, Type (минимум 3 поля)
        if len(parts) >= 3:
            # Очищаем поле типа (DIRECT/RESELLER) от невидимых символов
            # Оставляем только буквы A-Z
            relationship = re.sub(r'[^A-Z]', '', parts[2].upper())
            
            if relationship in ["DIRECT", "RESELLER"]:
                valid_count += 1
                
    return valid_count

# --- 5. Основная логика проверки домена ---
def check_domain_smart(domain):
    session = get_session()
    
    # Генерируем варианты. Приоритет: HTTPS, WWW, потом HTTP
    urls_to_try = [
        f"https://{domain}/app-ads.txt",
        f"https://www.{domain}/app-ads.txt",
        f"http://{domain}/app-ads.txt",
        f"http://www.{domain}/app-ads.txt"
    ]
    
    for url in urls_to_try:
        try:
            # verify=True важно для безопасности, но если падает - обработаем ниже
            response = session.get(url, timeout=10, allow_redirects=True, verify=True)
            
            if response.status_code == 200:
                # Определяем кодировку автоматически
                response.encoding = response.apparent_encoding
                content = response.text
                
                # Защита от HTML-заглушек (иногда сервер отдает 200 OK, но внутри "Page not found")
                if "<html" in content.lower()[:300] or "<!doctype" in content.lower()[:300]:
                    continue 
                
                valid_lines = count_valid_lines(content)
                return url, "Valid", valid_lines
                
        except requests.exceptions.SSLError:
            # Если SSL ошибка, пробуем без проверки сертификата
            try:
                response = session.get(url, timeout=10, allow_redirects=True, verify=False)
                if response.status_code == 200:
                    response.encoding = response.apparent_encoding
                    content = response.text
                    if "<html" not in content.lower()[:300]:
                        valid_lines = count_valid_lines(content)
                        return url, "Valid", valid_lines
            except:
                pass
        except Exception:
            pass
            
    # Если перебрали все варианты и не нашли
    return f"https://{domain}/app-ads.txt", "Error / Not Found", 0

# --- 6. Интерфейс ---
input_text = st.text_area(
    "Insert domain list (1 per line)", 
    height=300, 
    placeholder="hyperhippo.com\ngoogle.com"
)

if st.button("Run Check"):
    if not input_text.strip():
        st.warning("The list is empty.")
    else:
        raw_lines = [line.strip() for line in input_text.splitlines() if line.strip()]
        
        tasks = []
        for idx, line in enumerate(raw_lines):
            domain = clean_domain(line)
            tasks.append((idx, domain))
            
        st.info(f"Analyzing {len(tasks)} domains...")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        unsorted_results = []
        
        # Многопоточность для ускорения
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_idx = {
                executor.submit(check_domain_smart, domain): idx 
                for idx, domain in tasks
            }
            
            completed = 0
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    url, status, lines = future.result()
                except Exception:
                    # Fallback на случай критической ошибки в потоке
                    orig_domain = tasks[idx][1]
                    url = f"https://{orig_domain}/app-ads.txt"
                    status = "Error"
                    lines = 0
                
                unsorted_results.append({
                    "Original_Index": idx,
                    "App-ads Link": url,
                    "Status": status,
                    "Valid Lines": lines
                })
                
                completed += 1
                progress_bar.progress(completed / len(tasks))
                status_text.text(f"Processed: {completed}/{len(tasks)}")
        
        progress_bar.empty()
        status_text.empty()
        
        # Сборка таблицы результатов
        df = pd.DataFrame(unsorted_results)
        df = df.sort_values(by="Original_Index").drop(columns=["Original_Index"])
        
        st.subheader("Results")
        
        def highlight_row(val):
            if val == "Valid":
                return 'color: #4CAF50; font-weight: bold'
            return 'color: #FF5252; font-weight: bold'
            
        st.dataframe(
            df.style.map(highlight_row, subset=['Status']),
            use_container_width=True,
            hide_index=True,
            column_config={
                "App-ads Link": st.column_config.LinkColumn("App-ads Link"),
                "Valid Lines": st.column_config.NumberColumn("Valid Lines (IAB)", help="Number of records matching IAB standards")
            }
        )
        
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button("💾 Download Report (CSV)", csv_data, "app_ads_check_results.csv", "text/csv")
