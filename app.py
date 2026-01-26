import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import re

st.set_page_config(
    page_title="App-ads.txt Checker Pro", 
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

st.title("🛡️ App-ads.txt Checker Pro")
st.markdown("Verifies file availability and counts **valid IAB ad records** (Bypasses WAF/Cloudflare).")

# Максимально полный User-Agent и заголовки как у реального Chrome
LIVE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def get_session():
    session = requests.Session()
    headers = {
        'User-Agent': LIVE_UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }
    session.headers.update(headers)
    return session

def clean_domain(url_input):
    url_input = url_input.strip().replace('"', '').replace("'", "")
    if not url_input.startswith(("http://", "https://")):
        url_input = "http://" + url_input
    try:
        parsed = urlparse(url_input)
        domain = parsed.netloc if parsed.netloc else parsed.path.split('/')[0]
        return domain.lower().strip()
    except:
        return url_input

def count_valid_lines(content):
    valid_count = 0
    content = content.replace('\ufeff', '') # Remove BOM
    lines = content.replace('\r\n', '\n').replace('\r', '\n').splitlines()
    
    for line in lines:
        clean_line = line.split('#')[0].strip()
        if not clean_line:
            continue
            
        parts = [p.strip() for p in clean_line.split(',')]
        
        if len(parts) >= 3:
            # Строгая очистка типа записи
            relationship = re.sub(r'[^A-Z]', '', parts[2].upper())
            if relationship in ["DIRECT", "RESELLER"]:
                valid_count += 1
                
    return valid_count

def check_domain_smart(domain):
    session = get_session()
    
    # Генерируем варианты: https, http, и обязательно www версии
    urls_to_try = [
        f"https://{domain}/app-ads.txt",
        f"https://www.{domain}/app-ads.txt", # Часто помогает с редиректами
        f"http://{domain}/app-ads.txt",
        f"http://www.{domain}/app-ads.txt"
    ]
    
    # Удаляем дубликаты, если домен уже был введен с www
    urls_to_try = list(dict.fromkeys(urls_to_try))
    
    for url in urls_to_try:
        try:
            # Verify=False часто нужен для старых корпоративных серверов
            response = session.get(url, timeout=15, allow_redirects=True, verify=False)
            
            # Проверяем не только 200, но и контент
            if response.status_code == 200:
                response.encoding = response.apparent_encoding
                content = response.text
                
                # Пропускаем HTML заглушки
                if "<html" in content.lower()[:300] or "<!doctype" in content.lower()[:300]:
                    continue 
                
                valid_lines = count_valid_lines(content)
                
                # Если нашли 0 строк, возможно файл пустой, но ссылка рабочая.
                # Но лучше поискать дальше, вдруг другая ссылка даст результат.
                if valid_lines > 0:
                    return url, "Valid", valid_lines
                
                # Если дошли до конца и ничего не нашли, вернем этот результат как "Valid (Empty)"
                # Но пока сохраним его как кандидата
                
        except Exception:
            pass
            
    # Если мы прошли цикл, но нашли файл с 0 строк (но доступный), нужно вернуть его
    # Повторяем быстрый проход для поиска хотя бы доступного файла
    for url in urls_to_try:
        try:
            response = session.get(url, timeout=5, allow_redirects=True, verify=False)
            if response.status_code == 200 and "<html" not in response.text.lower()[:300]:
                 valid_lines = count_valid_lines(response.text)
                 return url, "Valid (Warning)", valid_lines
        except:
            pass

    return f"https://{domain}/app-ads.txt", "Error / Not Found", 0

input_text = st.text_area("Insert domain list (1 per line)", height=300, placeholder="hyperhippo.com")

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
        
        with ThreadPoolExecutor(max_workers=10) as executor: # Снизил потоки для стабильности
            future_to_idx = {
                executor.submit(check_domain_smart, domain): idx 
                for idx, domain in tasks
            }
            
            completed = 0
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    url, status, lines = future.result()
                except Exception as e:
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
            if "Valid" in val:
                return 'color: #4CAF50; font-weight: bold'
            return 'color: #FF5252; font-weight: bold'
            
        st.dataframe(
            df.style.map(highlight_row, subset=['Status']),
            use_container_width=True,
            hide_index=True,
            column_config={
                "App-ads Link": st.column_config.LinkColumn("App-ads Link"),
                "Valid Lines": st.column_config.NumberColumn("Valid Lines (IAB)")
            }
        )
        
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button("💾 Download Report (CSV)", csv_data, "app_ads_check_results.csv", "text/csv")
