import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import re

# Настройка страницы
st.set_page_config(
    page_title="App-ads.txt Checker", 
    layout="wide", 
    page_icon="🛡️"
)

# Стилизация интерфейса
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    .stTextArea textarea { background-color: #262730; color: #ffffff; border: 1px solid #444; }
    div[data-testid="stDataFrame"] { background-color: #262730; }
    </style>
""", unsafe_allow_html=True)

st.title("🛡️ App-ads.txt Checker")
st.markdown("Verifies file availability and counts **valid IAB ad records**.")

LIVE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def get_session():
    session = requests.Session()
    session.headers.update({
        'User-Agent': LIVE_UA,
        'Accept': 'text/plain,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })
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
    """
    Парсит контент app-ads.txt согласно стандартам IAB.
    Устойчив к BOM, разным кодировкам и невидимым символам.
    """
    valid_count = 0
    # Удаляем Byte Order Mark (BOM), если он есть
    content = content.replace('\ufeff', '')
    # Нормализуем переносы строк
    lines = content.replace('\r\n', '\n').replace('\r', '\n').splitlines()
    
    for line in lines:
        # Убираем комментарии (все, что после #)
        clean_line = line.split('#')[0].strip()
        
        if not clean_line:
            continue
            
        # Разбиваем строку по запятым
        parts = [p.strip() for p in clean_line.split(',')]
        
        # Запись валидна, если в ней есть: Domain, Account ID, Type (DIRECT/RESELLER)
        if len(parts) >= 3:
            # Очищаем поле типа записи от возможных невидимых символов
            # Оставляем только буквы A-Z
            relationship = re.sub(r'[^A-Z]', '', parts[2].upper())
            
            if relationship in ["DIRECT", "RESELLER"]:
                valid_count += 1
                
    return valid_count

def check_domain_smart(domain):
    session = get_session()
    # По спецификации app-ads.txt должен быть в корне или в подпапке (но чаще в корне)
    urls_to_try = [f"https://{domain}/app-ads.txt", f"http://{domain}/app-ads.txt"]
    
    for url in urls_to_try:
        try:
            response = session.get(url, timeout=12, allow_redirects=True, verify=True)
            
            # Если SSL ошибка — пробуем без проверки сертификата (некоторые экономят на SSL)
            if response.status_code == 200:
                # Принудительно определяем кодировку, чтобы не было "кракозябр"
                response.encoding = response.apparent_encoding
                content = response.text
                
                # Если сервер вернул HTML вместо текстового файла (частая ошибка 404-редиректов)
                if "<html" in content.lower()[:200] or "<!doctype" in content.lower()[:200]:
                    continue 
                
                valid_lines = count_valid_lines(content)
                return url, "Valid", valid_lines
                
        except requests.exceptions.SSLError:
            try:
                # Повторная попытка без проверки SSL
                response = session.get(url, timeout=10, allow_redirects=True, verify=False)
                if response.status_code == 200:
                    response.encoding = response.apparent_encoding
                    content = response.text
                    if "<html" not in content.lower()[:200]:
                        valid_lines = count_valid_lines(content)
                        return url, "Valid", valid_lines
            except:
                pass
        except Exception:
            pass
            
    return f"https://{domain}/app-ads.txt", "Error / Not Found", 0

# Интерфейс Streamlit
input_text = st.text_area("Insert domain list (1 per line)", height=300, placeholder="example.com\nhyperhippo.com")

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
        
        # Используем ThreadPoolExecutor для ускорения (20 потоков)
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
        
        # Сортируем обратно в порядке ввода
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
        
        # Скачивание отчета
        csv_data = df.to_csv(index=False).encode('utf-8')
        st.download_button("💾 Download Report (CSV)", csv_data, "app_ads_check_results.csv", "text/csv")
