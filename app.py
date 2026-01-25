import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
import time
import re

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
        return parsed.netloc if parsed.netloc else parsed.path.split('/')[0]
    except:
        return url_input

def count_valid_lines(content):
    valid_count = 0
    lines = content.splitlines()
    
    for line in lines:
        clean_line = line.split('#')[0].strip()
        
        if not clean_line:
            continue
            
        parts = [p.strip() for p in clean_line.split(',')]
        
        if len(parts) >= 3:
            relationship = parts[2].upper()
            if "DIRECT" in relationship or "RESELLER" in relationship:
                valid_count += 1
                
    return valid_count

def check_domain_smart(domain):
    session = get_session()
    urls_to_try = [f"https://{domain}/app-ads.txt", f"http://{domain}/app-ads.txt"]
    
    for url in urls_to_try:
        try:
            response = session.get(url, timeout=10, allow_redirects=True)
            
            if response.status_code == 200:
                content = response.text
                
                if "<!doctype html" in content.lower() or "<html" in content.lower()[:200]:
                    continue 
                
                valid_lines = count_valid_lines(content)
                return url, "Valid", valid_lines
                
        except requests.exceptions.SSLError:
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
            
    return urls_to_try[0], "Error", 0

input_text = st.text_area("Insert domain list (1 per line)", height=300)

if st.button("🚀 Run Smart Check"):
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
