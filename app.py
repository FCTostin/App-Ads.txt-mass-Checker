import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import time
import re

# ---------------- Page Setup ----------------
st.set_page_config(
    page_title="Smart App-ads.txt Checker", 
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

st.title("🛡️ Smart App-ads.txt Checker")
st.markdown("Проверяет доступность файла и считает только **реальные рекламные записи** (формат IAB).")

# ---------------- Configuration ----------------
LIVE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def get_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': LIVE_UA,
        'Accept': 'text/plain,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })
    return session

def clean_domain(url_input):
    """Очищает ввод, оставляя только домен"""
    url_input = url_input.strip()
    # Убираем пробелы и возможные кавычки
    url_input = url_input.replace('"', '').replace("'", "")
    
    if not url_input.startswith(("http://", "https://")):
        url_input = "http://" + url_input
    try:
        parsed = urlparse(url_input)
        return parsed.netloc if parsed.netloc else parsed.path.split('/')[0]
    except:
        return url_input

def count_valid_lines(content):
    """
    Парсит контент и считает только строки, соответствующие стандарту IAB.
    Стандарт: domain, publisher-id, relationship-type, [certification-id]
    """
    valid_count = 0
    lines = content.splitlines()
    
    for line in lines:
        # 1. Убираем комментарии (все что после #) и пробелы
        clean_line = line.split('#')[0].strip()
        
        # 2. Пропускаем пустые строки
        if not clean_line:
            continue
            
        # 3. Разбиваем по запятой
        parts = [p.strip() for p in clean_line.split(',')]
        
        # 4. Проверка стандарта: должно быть минимум 3 поля
        # Пример: google.com, pub-1234, DIRECT
        if len(parts) >= 3:
            # Дополнительная проверка: 3-е поле должно быть DIRECT или RESELLER (нечувствительно к регистру)
            relationship = parts[2].upper()
            if "DIRECT" in relationship or "RESELLER" in relationship:
                valid_count += 1
                
    return valid_count

def check_domain_smart(domain):
    """
    Возвращает: (Actual_URL, Status, Valid_Lines_Count)
    """
    session = get_session()
    
    # Сначала HTTPS, потом HTTP
    urls_to_try = [f"https://{domain}/app-ads.txt", f"http://{domain}/app-ads.txt"]
    
    for url in urls_to_try:
        try:
            response = session.get(url, timeout=10, allow_redirects=True)
            
            if response.status_code == 200:
                content = response.text
                
                # Защита: если сервер вернул HTML (ошибку 404 в виде страницы), это не валидный файл
                if "<!doctype html" in content.lower() or "<html" in content.lower()[:200]:
                    continue 
                
                # Умный подсчет строк
                valid_lines = count_valid_lines(content)
                
                # Если файл пустой или нет валидных строк, но статус 200 - помечаем как Warning или Valid (но с 0 строк)
                return url, "Valid", valid_lines
                
        except requests.exceptions.SSLError:
            # Попытка без SSL верификации
            try:
                response = session.get(url, timeout=10, allow_redirects=True, verify=False)
                if response.status_code == 200:
                    content = response.text
                    if "<!doctype html" not in content.lower():
                        valid_lines = count_valid_lines(content)
                        return url, "Valid", valid_lines
            except:
                pass
        except Exception:
            pass
            
    # Если ничего не нашли
    return urls_to_try[0], "Error", 0

# ---------------- Main UI ----------------

input_text = st.text_area("Вставьте список доменов (1 строка - 1 домен)", height=300)

if st.button("🚀 Проверить (Smart Check)"):
    if not input_text.strip():
        st.warning("Список пуст.")
    else:
        raw_lines = [line.strip() for line in input_text.splitlines() if line.strip()]
        
        # Подготовка задач
        tasks = []
        for idx, line in enumerate(raw_lines):
            domain = clean_domain(line)
            tasks.append((idx, domain))
            
        st.info(f"Анализируем {len(tasks)} доменов...")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        unsorted_results = []
        
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
                except:
                    # Fallback
                    orig_domain = tasks[idx][1]
                    url = f"https://{orig_domain}/app-ads.txt"
                    status = "Error"
                    lines = 0
                
                unsorted_results.append({
                    "Original_Index": idx,
                    "App-ads Link": url,
                    "Valid": status,
                    "Valid Lines": lines # Переименовали для ясности
                })
                
                completed += 1
                progress_bar.progress(completed / len(tasks))
                status_text.text(f"Проверено: {completed}/{len(tasks)}")
        
        progress_bar.empty()
        status_text.empty()
        
        # ---------------- Output ----------------
        df = pd.DataFrame(unsorted_results)
        df = df.sort_values(by="Original_Index").drop(columns=["Original_Index"])
        
        st.subheader("Результаты проверки")
        
        def highlight_row(val):
            if val == "Valid":
                return 'color: #4CAF50; font-weight: bold'
            return 'color: #FF5252; font-weight: bold'
            
        st.dataframe(
            df.style.map(highlight_row, subset=['Valid']),
            use_container_width=True,
            hide_index=True,
            column_config={
                "App-ads Link": st.column_config.LinkColumn("App-ads Link"),
                "Valid Lines": st.column_config.NumberColumn("Valid Lines (IAB)", help="Количество строк, соответствующих стандарту")
            }
        )
        
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button("💾 Скачать отчет (CSV)", csv_data, "smart_ads_check.csv", "text/csv")
