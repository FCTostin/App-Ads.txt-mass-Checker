import streamlit as st
import pandas as pd
from curl_cffi import requests as cffi_requests # Библиотека для имитации браузера
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import re

# --- Настройка страницы ---
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
st.markdown("Verifies **app-ads.txt** availability using **Browser Impersonation** (similar to Chrome Extension).")

# --- Очистка и подготовка домена ---
def clean_domain(url_input):
    url_input = url_input.strip().replace('"', '').replace("'", "")
    if not url_input.startswith(("http://", "https://")):
        url_input = "http://" + url_input   
    try:
        parsed = urlparse(url_input)
        domain = parsed.netloc if parsed.netloc else parsed.path.split('/')[0]
        # Убираем www, чтобы скрипт сам перебирал варианты
        return domain.lower().replace("www.", "").strip()
    except:
        return url_input

# --- Парсинг (Только валидные строки IAB) ---
def count_valid_lines(content):
    valid_count = 0
    # Удаляем BOM и нормализуем
    content = content.replace('\ufeff', '')
    lines = content.replace('\r\n', '\n').replace('\r', '\n').splitlines()
    
    for line in lines:
        clean_line = line.split('#')[0].strip()
        if not clean_line:
            continue
            
        parts = [p.strip() for p in clean_line.split(',')]
        
        # IAB стандарт: Domain, Account ID, Type
        if len(parts) >= 3:
            # Очистка типа от мусора
            relationship = re.sub(r'[^A-Z]', '', parts[2].upper())
            if relationship in ["DIRECT", "RESELLER"]:
                valid_count += 1
                
    return valid_count

# --- Запрос с имитацией браузера ---
def fetch_url_impersonate(url):
    try:
        # impersonate="chrome120" -> Сервер думает, что это настоящий браузер
        response = cffi_requests.get(
            url, 
            impersonate="chrome120", 
            timeout=15,
            allow_redirects=True
        )
        
        if response.status_code == 200:
            content = response.text
            # Проверка на HTML-заглушки (иногда сервер отдает 200, но это страница ошибки)
            if "<html" in content.lower()[:300] or "<!doctype" in content.lower()[:300]:
                return None
            return content
    except Exception:
        return None
    return None

# --- Умная проверка (только app-ads.txt) ---
def check_domain_smart(domain):
    # Пробуем варианты с www и без. 
    # HyperHippo требует www, другие сайты наоборот. Проверяем все.
    urls_to_try = [
        f"https://www.{domain}/app-ads.txt", # Частый кейс для крупных студий
        f"https://{domain}/app-ads.txt",
        f"http://www.{domain}/app-ads.txt",
        f"http://{domain}/app-ads.txt"
    ]
    
    for url in urls_to_try:
        content = fetch_url_impersonate(url)
        
        if content:
            valid_lines = count_valid_lines(content)
            
            # Если файл найден и валиден (или пуст, но существует физически)
            if valid_lines >= 0:
                # Если файл пуст, помечаем как "Empty File", если нет — "Valid"
                status = "Valid" if valid_lines > 0 else "File Empty (0 lines)"
                return url, status, valid_lines
            
    return f"https://{domain}/app-ads.txt", "Error / Not Found", 0

# --- Интерфейс ---
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
        
        with ThreadPoolExecutor(max_workers=10) as executor:
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
        
        df = pd.DataFrame(unsorted_results)
        df = df.sort_values(by="Original_Index").drop(columns=["Original_Index"])
        
        st.subheader("Results")
        
        def highlight_row(val):
            if "Valid" in str(val):
                return 'color: #4CAF50; font-weight: bold'
            return 'color: #FF5252; font-weight: bold'
            
        st.dataframe(
            df.style.map(highlight_row, subset=['Status']),
            use_container_width=True,
            hide_index=True,
            column_config={
                "App-ads Link": st.column_config.LinkColumn("App-ads Link"),
                "Valid Lines": st.column_config.NumberColumn("Valid Lines", help="Valid IAB records found")
            }
        )
        
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button("💾 Download Report (CSV)", csv_data, "app_ads_check_results.csv", "text/csv")
