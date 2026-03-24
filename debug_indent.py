from bs4 import BeautifulSoup
import requests

url = "https://www.voedingswaardetabel.nl/voedingswaarde/voedingsmiddel/?id=76"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers)
soup = BeautifulSoup(resp.text, "html.parser")

for row in soup.find_all(class_="rowitem"):
    # Print the first few characters of the raw HTML of each row
    html = str(row)
    if "vet" in html.lower():
        print(f"DEBUG ROW: {html[:100]}")
        # Check for various space types
        has_nbsp = "&nbsp;" in html
        has_xa0 = "\xa0" in html
        print(f"  has &nbsp;: {has_nbsp}, has \\xa0: {has_xa0}")
