# Add selenium script
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.wait import WebDriverWait
import time
import dotenv
import os
import pytest

dotenv.load_dotenv()
url = os.getenv('URL')
driver = webdriver.Chrome()
driver.get(url)

search_input = driver.find_element(By.ID, 'searchInput')
search_term = 'test'
search_input.send_keys(search_term)

search_button = driver.find_element(By.ID, 'searchButton')
search_button.click()

wait = WebDriverWait(driver, timeout=10)
wait.until(lambda d: d.find_element(By.ID, 'output'))

output = driver.find_element(By.ID, 'output')
print(output.text)

expected = f'["Test","Dummy","{search_term}"]'
assert output.text == expected

driver.quit()
