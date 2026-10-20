from selenium import webdriver
from selenium.webdriver.firefox.options import Options

URL = "https://ctftime.org/event/list/upcoming"

print("[DEBUG] Configuring Firefox...", flush=True)

options = Options()
options.add_argument("-headless")

driver = None

try:
    print("[DEBUG] Starting Firefox WebDriver...", flush=True)
    driver = webdriver.Firefox(options=options)
    print("[DEBUG] Firefox started successfully.", flush=True)

    print(f"[DEBUG] Navigating to {URL}", flush=True)
    driver.get(URL)
    print(f"[DEBUG] Page title: {driver.title}", flush=True)

    print("[DEBUG] Extracting page text...", flush=True)
    page_text = driver.find_element("tag name", "body").text

    print(f"[DEBUG] Extracted {len(page_text)} characters.", flush=True)
    print("=" * 60)
    print(page_text)
    print("=" * 60)

except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
    raise

finally:
    if driver:
        print("[DEBUG] Closing Firefox...", flush=True)
        driver.quit()
        print("[DEBUG] Firefox closed.", flush=True)
