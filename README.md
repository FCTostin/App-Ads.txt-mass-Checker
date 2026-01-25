# 🛡️ App-ads.txt Checker

A high-performance, Streamlit-based tool designed to validate the accessibility and compliance of `app-ads.txt` files against **IAB standards**.

## 🚀 Key Features

* **Smart Protocol Discovery:** Automatically attempts connection via `HTTPS` and fallbacks to `HTTP` with SSL-error handling.
* **IAB Record Parsing:** Doesn't just check for file existence—it counts valid entries (checks for `DIRECT`/`RESELLER` relationship types).
* **HTML Detection:** Prevents false positives by identifying when servers return 404 pages as HTML instead of text.
* **Concurrent Processing:** Uses `ThreadPoolExecutor` to scan dozens of domains in seconds.
* **Clean Export:** Direct CSV export for easy integration into ad-ops workflows.

## 🛠️ Installation

1. **Clone the repository:**
```bash
git clone https://github.com/yourusername/app-ads-checker.git
cd app-ads-checker

```


2. **Install dependencies:**
```bash
pip install streamlit pandas requests

```


3. **Run the app:**
```bash
streamlit run app.py

```



## 📋 Input Format

Simply paste a list of domains or URLs. The tool automatically cleans the input, extracting the core domain to locate the `/app-ads.txt` path.

## ⚙️ Tech Stack

* **Streamlit** (UI/Frontend)
* **Pandas** (Data handling)
* **Requests** (Network calls)
* **Concurrent.futures** (Multi-threading)
