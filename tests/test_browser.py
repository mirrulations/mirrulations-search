import time
import os
import json
import subprocess
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.chrome.options import Options

def free_port(port):
    """Kill Flask processes currently holding the given port."""
    try:
        # This gets the files using the port
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            check=False
        )

        pids = result.stdout.strip().split()

        for pid in pids:
            # This inspects the command running for each PID
            cmd_result = subprocess.run(
                ["ps", "-p", pid, "-o", "command="],
                capture_output=True,
                text=True,
                check=False
            )

            command = cmd_result.stdout.strip()

            # Only kill if it's a Flask-related process
            if "flask" in command or "mirrsearch" in command:
                os.kill(int(pid), 9)

        time.sleep(0.5)  # Extra time for the port to be released

    except FileNotFoundError:
        pass  # just in case lsof isn't available

@pytest.fixture(name="driver")
def fixture_driver():
    """Set up the Selenium Driver and Flask process"""
    free_port(5001)  # Ensure port is clear before starting

    # Start flask app and keep it running for the duration of the test.
    process = subprocess.Popen(  # pylint: disable=consider-using-with
        ["flask", "--app", "src.mirrsearch.app", "run", "--port", "5001", "--no-reload"]
    )
    # Give server time to start
    time.sleep(5)

    # Needed to work with Github CI
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    set_up_driver = webdriver.Chrome(options=options)

    set_up_driver.get('http://127.0.0.1:5001')

    # This allows the test to run, and then clean up the driver and process after
    yield set_up_driver

    set_up_driver.quit()
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()

def test_browser_search(driver):
    """Run the test with two search terms"""
    if os.getenv("USE_POSTGRES", "").lower() in {"1", "true", "yes", "on"}:
        pytest.skip("Unit tests expect dummy data")
    search_terms = ['test', 'esrd']

    for search_term in search_terms:
        driver.find_element(By.ID, 'searchInput').clear()
        driver.find_element(By.ID, 'searchInput').send_keys(search_term)

        driver.find_element(By.ID, 'searchButton').click()

        output = driver.find_element(By.ID, 'output')

        wait = WebDriverWait(driver, timeout=10)
        wait.until(lambda d: d.find_element(By.ID, 'output').text != "")

        if search_term not in ['esrd']:
            # No results expected for non-matching terms
            data = json.loads(output.text)
            assert data == []
        else:
            data = json.loads(output.text)
            assert isinstance(data, list)
            assert len(data) > 0
            required_fields = {"agency_id", "cfrPart", "docket_id", "document_type", "title"}
            assert all(required_fields.issubset(item.keys()) for item in data)
            assert any("ESRD" in item["title"] for item in data)
