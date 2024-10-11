import mysql.connector
from datetime import datetime, timezone, timedelta
import os
from dotenv import load_dotenv
import random
import string
import google.generativeai as genai
import requests 

load_dotenv()

mydb = mysql.connector.connect(
    host=os.getenv('DB_CLOUD_HOST'),
    user=os.getenv('DB_CLOUD_USER'),
    password=os.getenv('DB_CLOUD_PASSWORD'),
    database=os.getenv('DB_CLOUD_NAME'),
    buffered=True
)

mycursor = mydb.cursor(dictionary=True)

def execute_query(query, params=None):
    with mydb.cursor(dictionary=True) as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()

def update_whitelist_status(user_id):
    now = datetime.now(timezone(timedelta(hours=7)))
    mycursor.execute("SELECT expiration_date, is_permanent FROM whitelist WHERE user_id = %s", (user_id,))
    result = mycursor.fetchone()
    if result:
        if result['is_permanent']:
            return True
        expiration_date = result['expiration_date']
        if expiration_date and now.date() > expiration_date:
            mycursor.execute("DELETE FROM whitelist WHERE user_id = %s", (user_id,))
            mydb.commit()
            return False
        return now.date() <= expiration_date if expiration_date else False
    return False

def is_whitelisted(user_id):
    return update_whitelist_status(user_id)

def get_new_sentence():
    utc_plus_7 = timezone(timedelta(hours=7))
    current_date = datetime.now(utc_plus_7).date()
    current_datetime = datetime.now(utc_plus_7)

    mycursor.execute(
        "SELECT * FROM sentences WHERE DATE(created_at) = %s", (current_date,))
    today_sentence = mycursor.fetchone()

    if today_sentence:
        return today_sentence

    mycursor.execute("SELECT chinese FROM sentences")
    existing_sentences = set(row['chinese'] for row in mycursor.fetchall())
    result = None

    while True:
        prompt = f"""Bạn là 1 người trung. Tôi là người Việt và tôi đặt câu hỏi như sau: Hãy tạo một câu tiếng Trung ngắn, hoàn toàn ngẫu nhiên và không giới hạn trong bất kỳ chủ đề nào nhưng dành cho người Việt học tiếng Trung, bao gồm:

        - Chữ Hán
        - Pinyin
        - Âm Hán Việt (phiên âm Hán Việt của câu chữ Hán)
        - Nghĩa tiếng Việt (dịch nghĩa của câu sang tiếng Việt)

        Hãy đảm bảo rằng:

        - Câu trả lời chỉ bao gồm các thông tin trên, không thêm nội dung khác.
        - Định dạng kết quả chính xác như sau:

        Chữ Hán: ...
        Pinyin: ...
        Âm Hán Việt: ...
        Nghĩa tiếng Việt: ...

        Không thêm bất kỳ văn bản nào khác.

        Lưu ý: Câu được tạo ra phải khác với các câu sau đây:
        {', '.join(existing_sentences)}
        """
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(
                temperature=1),)
            text = response.text
            lines = text.strip().split('\n')
            temp_result = {}
            for line in lines:
                if 'Chữ Hán:' in line:
                    temp_result['chinese'] = line.replace(
                        'Chữ Hán:', '').strip()
                elif 'Pinyin:' in line:
                    temp_result['pinyin'] = line.replace('Pinyin:', '').strip()
                elif 'Âm Hán Việt:' in line:
                    temp_result['sino_vietnamese'] = line.replace(
                        'Âm Hán Việt:', '').strip()
                elif 'Nghĩa tiếng Việt:' in line:
                    temp_result['vietnamese_meaning'] = line.replace(
                        'Nghĩa tiếng Việt:', '').strip()

            if len(temp_result) < 4:
                continue

            if temp_result['chinese'] in existing_sentences:
                continue
            else:
                result = temp_result
                break
        except Exception as e:
            print(f"Lỗi khi gọi Google Generative AI API: {e}")
            result = None
            break

    if result:
        sql = """INSERT INTO sentences 
                 (chinese, pinyin, sino_vietnamese, vietnamese_meaning, created_at, created_date) 
                 VALUES (%s, %s, %s, %s, %s, %s)"""
        values = (result['chinese'], result['pinyin'], result['sino_vietnamese'],
                  result['vietnamese_meaning'], current_datetime, current_date)
        mycursor.execute(sql, values)
        mydb.commit()

    return result

def check_transaction(reference_code):
    url = "https://my.sepay.vn/userapi/transactions/list"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('SEPAY_API_TOKEN')}"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        for transaction in data.get('transactions', []):
            if f"TTGP {reference_code}" in transaction['transaction_content']:
                return float(transaction['amount_in'])
        return None
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi gọi API: {e}")
        return None