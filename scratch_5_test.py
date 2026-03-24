import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

BASE_URL = "https://www.voedingswaardetabel.nl/voedingswaarde/voedingsmiddel/?id={id}"
TEST_PRODUCT_IDS = [76, 914, 1, 10, 100]

REQUEST_DELAY_SECONDS = 1.0
TIMEOUT_SECONDS = 20
OUTPUT_FILE = "products.jsonl"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BHLTHYDataBot/1.0; +https://bhlthy.com)"
}


def clean_text(value: Optional[str]) -> Optional[str]:
    """Normalize whitespace and return None for empty values."""
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def parse_number_and_unit(raw_value: Optional[str]) -> Dict[str, Any]:
    """Parse strings into a normalized dictionary with value, unit, and raw text."""
    cleaned = clean_text(raw_value)
    if not cleaned:
        return {"value": None, "unit": None, "raw": None}

    if cleaned.startswith("-"):
        parts = cleaned.split(maxsplit=1)
        unit = parts[1].strip() if len(parts) > 1 else None
        return {"value": None, "unit": unit, "raw": cleaned}

    match = re.match(r"^([0-9]+(?:[.,][0-9]+)?)\s*(.*)$", cleaned)
    if not match:
        return {"value": None, "unit": None, "raw": cleaned}

    number_str = match.group(1).replace(",", ".")
    unit = clean_text(match.group(2))

    try:
        number = float(number_str)
    except ValueError:
        number = None

    return {"value": number, "unit": unit, "raw": cleaned}


def get_page_html(product_id: int) -> str:
    """Fetch product page HTML."""
    url = BASE_URL.format(id=product_id)
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


def detect_indent(tag: Tag) -> int:
    """Detect indentation level based on \xa0 characters in the text."""
    text = tag.get_text()
    if "\xa0\xa0\xa0" in text or "   " in text:
        return 1
    
    # Fallback to checking classes
    classes = tag.get("class", [])
    if any(c in ["sub", "indent", "item_sub"] for c in classes):
        return 1
        
    return 0


def collect_sections(soup: BeautifulSoup) -> Dict[str, Dict[str, Any]]:
    """Collect all data grouped by their actual h2 section headers."""
    sections_data: Dict[str, Dict[str, Any]] = {}
    
    # The structure is usually: h2 followed by div or fieldset containing rowitems
    for h2 in soup.find_all("h2"):
        section_title = clean_text(h2.get_text(" ", strip=True))
        if not section_title:
            continue
            
        items = {}
        node = h2.next_sibling
        while node:
            if isinstance(node, Tag) and node.name == "h2":
                break
            
            if isinstance(node, Tag):
                # Look for rowitems inside this node or if node itself is a rowitem
                rows = node.find_all(class_="rowitem")
                if not rows and "rowitem" in node.get("class", []):
                    rows = [node]
                
                for row in rows:
                    val_div = row.find(class_="floatright")
                    if not val_div:
                        continue
                        
                    val_text = clean_text(val_div.get_text(strip=True))
                    
                    # Extract label (all text except the value div)
                    label_parts = []
                    for child in row.contents:
                        if child != val_div:
                            if isinstance(child, NavigableString):
                                label_parts.append(str(child))
                            elif isinstance(child, Tag):
                                label_parts.append(child.get_text(" ", strip=True))
                    
                    label = clean_text(" ".join(label_parts))
                    if label:
                        label = label.rstrip(":").strip()
                        parsed = parse_number_and_unit(val_text)
                        parsed["indent"] = detect_indent(row)
                        items[label] = parsed
            
            node = node.next_sibling
            
        if items:
            sections_data[section_title] = items
            
    return sections_data


def extract_field_from_strings(strings: List[str], field_name: str) -> Optional[str]:
    """Find a single field value in flattened page text."""
    for index, item in enumerate(strings):
        if item == field_name and index + 1 < len(strings):
            return strings[index + 1]
    return None


def parse_product(product_id: int, html: str) -> Dict[str, Any]:
    """Parse one product page into a structured dict using dynamic sections."""
    soup = BeautifulSoup(html, "html.parser")
    strings = [clean_text(s) for s in soup.stripped_strings if clean_text(s)]

    h1 = soup.find("h1")
    name = clean_text(h1.get_text(" ", strip=True)) if h1 else f"Product {product_id}"

    # Extract dynamic sections
    all_sections = collect_sections(soup)

    # Map sections to our expected keys for better UI handling
    # but keep the original titles as well
    data: Dict[str, Any] = {
        "id": product_id,
        "url": BASE_URL.format(id=product_id),
        "name": name,
        "latin_name": extract_field_from_strings(strings, "Latijnse naam:"),
        "product_group": extract_field_from_strings(strings, "Productgroep:"),
        "sections": all_sections,
        # Legacy fields for backward compatibility if needed in frontend
        "general": all_sections.get("Algemeen", {}),
        "energy": all_sections.get("Energie", {}),
        "nutrition": all_sections.get("Voedingswaarde", {}),
        "vitamins": all_sections.get("Vitamines", {}),
        "minerals": all_sections.get("Mineralen", {}),
    }

    return data


def load_existing_ids(filename: str) -> Set[int]:
    """Read JSONL file and return set of already processed product IDs."""
    ids = set()
    if not os.path.exists(filename):
        return ids
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
                if "id" in item:
                    ids.add(int(item["id"]))
            except (json.JSONDecodeError, ValueError):
                continue
    return ids


def save_product_to_jsonl(product: Dict[str, Any], filename: str) -> None:
    """Append a single product to the JSONL file."""
    with open(filename, "a", encoding="utf-8") as f:
        f.write(json.dumps(product, ensure_ascii=False) + "\n")


def main() -> None:
    # Clear output file for this test to ensure full update with new structure
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
        print(f"Cleared {OUTPUT_FILE} for fresh update.")

    count = 0
    for product_id in TEST_PRODUCT_IDS:
        try:
            print(f"Fetching product id={product_id} ...")
            html = get_page_html(product_id)
            product = parse_product(product_id, html)
            save_product_to_jsonl(product, OUTPUT_FILE)
            print(f"OK: Saved id={product_id} -> {product.get('name')}")
            count += 1
            time.sleep(REQUEST_DELAY_SECONDS)
        except Exception as exc:
            print(f"ERROR: id={product_id} -> {exc}")

    print(f"Done. Processed {count} products with dynamic section grouping.")


if __name__ == "__main__":
    main()