import requests
from bs4 import BeautifulSoup
import json
import time
from tqdm import tqdm

def get_stroke_order(character):
    url = f"https://www.strokeorder.com/chinese/{character}"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    result = {
        'character': character,
        'pinyin': '',
        'wubi': '',
        'cangjie': '',
        'zhengma': '',
        'four_corner': '',
        'unicode': '',
        'stroke_order_animation': '',
        'stroke_order_diagrams': []
    }

    # Extract input method information
    input_method_items = soup.find_all('div', class_='stroke-hanzi-item')
    for item in input_method_items:
        left = item.find('span', class_='stroke-hanzi-info-left')
        right = item.find('span', class_='stroke-hanzi-info-right')
        if left and right:
            key = left.text.strip().lower()
            value = right.text.strip()
            if key in result:
                result[key] = value

    # Extract stroke order animation
    animation = soup.find('img', alt=f"{character} Stroke Order Animation")
    if animation:
        result['stroke_order_animation'] = 'https://www.strokeorder.com' + animation['src']

    # Extract stroke order diagrams
    diagrams = soup.find_all('img', alt=f"{character} Stroke Order Diagrams")
    for diagram in diagrams:
        result['stroke_order_diagrams'].append('https://www.strokeorder.com' + diagram['src'])

    return result

# Đọc dữ liệu từ file JSON
with open('static/vocab.json', 'r', encoding='utf-8') as file:
    data = json.load(file)

# Lấy danh sách các ký tự HSK3
hsk3_characters = [char for item in data if item['HSK'] == 3 for char in item['Chinese'] if char.strip()]

# Đếm và in ra số lượng từ vựng HSK3
hsk3_vocab_count = len(set(hsk3_characters))
print(f"Số lượng từ vựng trong HSK3: {hsk3_vocab_count}")

# Lấy thông tin thứ tự viết cho các ký tự HSK3
hsk3_stroke_orders = []

for char in tqdm(hsk3_characters, desc="Đang xử lý ký tự HSK3"):
    stroke_order_info = get_stroke_order(char)
    hsk3_stroke_orders.append(stroke_order_info)
    time.sleep(1)  # Đợi 1 giây giữa các yêu cầu để tránh quá tải máy chủ

# Lưu kết quả vào file JSON
with open('hsk3_stroke_orders.json', 'w', encoding='utf-8') as file:
    json.dump(hsk3_stroke_orders, file, ensure_ascii=False, indent=2)

print("Đã lưu thông tin thứ tự viết vào file hsk3_stroke_orders.json")