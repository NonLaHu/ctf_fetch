from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

URL = "https://ctftime.org/event/list/upcoming"

print("[DEBUG] Configuring Chrome options...")
options = Options()
options.add_argument("--headless=new")

driver = None

try:
    print("[DEBUG] Starting Chrome WebDriver...")
    driver = webdriver.Firefox(options=options)
    print("[DEBUG] Chrome WebDriver started successfully.")

    print(f"[DEBUG] Navigating to: {URL}")
    driver.get(URL)
    print(f"[DEBUG] Page loaded. Current URL: {driver.current_url}")

    print("[DEBUG] Waiting for the page body...")
    WebDriverWait(driver, 15).until(
        lambda d: d.find_element("tag name", "body")
    )
    print("[DEBUG] Page body found.")

    print("[DEBUG] Reading page title...")
    print(f"[DEBUG] Title: {driver.title}")

    print("[DEBUG] Extracting visible page text...")
    page_text = driver.find_element("tag name", "body").text

    print(f"[DEBUG] Extracted {len(page_text)} characters.")
    print("[DEBUG] Beginning page output...")
    print("=" * 60)
    print(page_text)
    print("=" * 60)
    print("[DEBUG] Page output complete.")

except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}")
    raise

finally:
    if driver:
        print("[DEBUG] Closing Chrome WebDriver...")
        driver.quit()
        print("[DEBUG] Chrome WebDriver closed.")
