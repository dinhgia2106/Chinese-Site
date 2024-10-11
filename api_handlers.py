import google.generativeai as genai
import os
import requests
from bs4 import BeautifulSoup
import re
from dotenv import load_dotenv
import base64
import uuid

from utils import process_meanings

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=api_key)

def translate_and_analyze(text):
    prompt = f"""
    Bạn là một chuyên gia ngôn ngữ Trung - Việt, hãy thực hiện các yêu cầu sau:

    Đọc đoạn văn bản sau:
    {text}

    Phân tích đoạn văn và câu văn tiếng Trung:

    Nếu đoạn văn bản nhiều hơn 10 từ thì chỉ cần trả về bản dịch với cấu trúc sau (nếu là tiếng Trung, nếu không phải thì trả về kết quả: "Vui lòng nhập tiếng Trung"):

    Đây là nội dung bản dịch:
    - [Bản dịch tiếng Việt]

    Nếu đoạn văn bản có 10 từ trở xuống thì thực hiện các bước sau:

    Dịch toàn bộ đoạn văn bản sang tiếng Việt.
    Phân tích từng chữ Hán theo các yêu cầu sau:
    Nghĩa Hán Việt
    Bộ thủ tạo thành chữ đó
    Pinyin
    Ý nghĩa tiếng Việt
    Gợi ý cách nhớ
    Cách sử dụng
    Các từ liên quan
    Sau đó hãy kiểm tra kết quả step by step và trả về kết quả cuối cùng.
    Trình bày kết quả theo định dạng sau:

    Bản dịch: [Bản dịch tiếng Việt]
    Phân tích từng chữ:
    Chữ [Chữ Hán]:
    - Nghĩa Hán Việt: [Nghĩa]
    - Bộ thủ: [Danh sách bộ thủ]
    - Pinyin: [Cách đọc]
    - Ý nghĩa tiếng Việt: [Ý nghĩa]
    - Gợi ý cách nhớ: [Gợi ý]
    - Cách sử dụng: [Cách sử dụng]
    - Các từ liên quan: [Các từ liên quan]
    [Chữ Hán tiếp theo]
    Chỉ cung cấp thông tin được yêu cầu, không thêm bất kỳ giải thích nào khác.
    """

    try:
        model = genai.GenerativeModel("gemini-1.5-pro")
        response = model.generate_content(prompt)
        
        if hasattr(response, 'text'):
            result = response.text
        else:
            result = ''.join([part.text for part in response.parts])

        # Thêm chức năng nghe cho đoạn văn gốc
        api_key = os.getenv("GOOGLE_TEXT_TO_SPEECH_API_KEY")
        url = f'https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}'
        
        clean_text = re.sub(r'\s*\(.*?\)', '', text)
        
        payload = {
            'input': {
                'text': clean_text
            },
            'voice': {
                'languageCode': 'cmn-CN',
                'name': 'cmn-CN-Standard-A'
            },
            'audioConfig': {
                'audioEncoding': 'MP3'
            }
        }
        
        headers = {'Content-Type': 'application/json'}
        
        tts_response = requests.post(url, json=payload, headers=headers)
        tts_response.raise_for_status()
        
        audio_content = tts_response.json().get('audioContent')
        if audio_content:
            filename = f"audio_{uuid.uuid4()}.mp3"
            file_path = os.path.join('static', 'audio', filename)
            
            audio_data = base64.b64decode(audio_content)
            with open(file_path, 'wb') as f:
                f.write(audio_data)
            
            audio_url = f'/static/audio/{filename}'
            return {
                'audio_url': audio_url,
                'result': result
            }
        else:
            print("Không nhận được dữ liệu âm thanh từ API")
            return {'result': result}

    except Exception as e:
        return {'error': f"Đang lỗi, vui lòng thử lại sau. Chi tiết lỗi: {str(e)}"}

def get_hannom_info(character):
    url = f"https://hvdic.thivien.net/whv/{character}"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    result = {
        'character': character,
        'han_viet': None,
        'pinyin': None,
        'total_strokes': None,
        'radical': None,
        'meanings': None,
        'found': False
    }

    info_div = soup.find('div', class_='info')
    if info_div and "Có 1 kết quả:" in info_div.text:
        result['found'] = True
        hvres_div = soup.find('div', class_='hvres')
        if hvres_div:
            han_viet = hvres_div.find('a', class_='hvres-goto-link')
            if han_viet:
                result['han_viet'] = han_viet.text.strip()

            pinyin_tag = hvres_div.find(string=lambda x: x and 'Âm Pinyin:' in x)
            if pinyin_tag:
                pinyin_element = pinyin_tag.find_next('a')
                if pinyin_element:
                    result['pinyin'] = pinyin_element.text.strip()

            meaning_div = hvres_div.find('div', class_='hvres-meaning')
            if meaning_div:
                raw_meaning = meaning_div.text.strip()
                result['meanings'] = process_meanings(raw_meaning)

    elif soup.find('div', class_='hvres'):
        result['found'] = True
        hvres_divs = soup.find_all('div', class_='hvres')
        main_hvres = hvres_divs[0]
        main_details = main_hvres.find('div', class_='hvres-details')
        if main_details:
            av_tag = main_details.find(string=lambda x: x and 'Âm Hán Việt:' in x)
            if av_tag:
                parent = av_tag.parent
                spans = parent.find_all('span', class_='hvres-goto-link')
                readings = [span.get_text(strip=True) for span in spans]
                result['han_viet'] = ', '.join(readings)

            pinyin_tag = main_details.find(string=lambda x: x and 'Âm Pinyin:' in x)
            if pinyin_tag:
                pinyin_element = pinyin_tag.find_next('a')
                if pinyin_element:
                    result['pinyin'] = pinyin_element.text.strip()

            tn_tag = main_details.find(string=lambda x: x and 'Tổng nét:' in x)
            if tn_tag:
                tn_text = tn_tag.strip()
                tn = tn_text.split('Tổng nét:')[-1].strip()
                result['total_strokes'] = tn

            b_tag = main_details.find(string=lambda x: x and 'Bộ:' in x)
            if b_tag:
                a_tag = b_tag.find_next('a')
                if a_tag:
                    radical = a_tag.get_text(strip=True)
                    extra_info = a_tag.next_sibling
                    if extra_info:
                        radical += ' ' + extra_info.strip()
                    result['radical'] = radical

        meanings = []
        for hvres in hvres_divs:
            details = hvres.find('div', class_='hvres-details')
            if details:
                sources = details.find_all('p', class_='hvres-source')
                for p in sources:
                    p_text = p.get_text(strip=True)
                    if 'Từ điển' in p_text:
                        meaning_div = p.find_next_sibling('div', class_='hvres-meaning')
                        if meaning_div and 'han-clickable' in meaning_div.get('class', []):
                            meaning_text = meaning_div.get_text(strip=True)
                            meanings.extend(process_meanings(meaning_text))
                            if len(meanings) >= 2:
                                break
                if len(meanings) >= 2:
                    break
        
        if meanings:
            result['meanings'] = meanings

    return result

def get_stroke_order(character):
    url = f"https://www.strokeorder.com/chinese/{character}"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    result = {
        'character': character,
        'wubi': '',
        'cangjie': '',
        'zhengma': '',
        'four_corner': '',
        'unicode': '',
        'stroke_order_animation': '',
        'stroke_order_diagrams': []
    }

    input_method_items = soup.find_all('div', class_='stroke-hanzi-item')
    for item in input_method_items:
        left = item.find('span', class_='stroke-hanzi-info-left')
        right = item.find('span', class_='stroke-hanzi-info-right')
        if left and right:
            key = left.text.strip().lower()
            value = right.text.strip()
            if key in result:
                result[key] = value

    animation = soup.find('img', alt=f"{character} Stroke Order Animation")
    if animation:
        result['stroke_order_animation'] = 'https://www.strokeorder.com' + animation['src']

    diagrams = soup.find_all('img', alt=f"{character} Stroke Order Diagrams")
    for diagram in diagrams:
        result['stroke_order_diagrams'].append('https://www.strokeorder.com' + diagram['src'])

    return result

def get_combined_info(character):
    hannom_info = get_hannom_info(character)
    stroke_order_info = get_stroke_order(character)
    
    combined_info = {**hannom_info, **stroke_order_info}
    return combined_info