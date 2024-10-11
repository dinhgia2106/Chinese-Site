import base64
import os
import requests
import google.generativeai as genai

def recognize_speech(audio_file):
    # Đọc và mã hóa file âm thanh
    audio_content = base64.b64encode(audio_file.read()).decode('utf-8')
    
    # Chuẩn bị dữ liệu cho API Speech-to-Text
    api_key = os.getenv("GOOGLE_TEXT_TO_SPEECH_API_KEY")
    url = f'https://speech.googleapis.com/v1/speech:recognize?key={api_key}'
    
    request_data = {
        'config': {
            'languageCode': 'zh-CN',
            'encoding': 'MP3',
            'sampleRateHertz': 16000
        },
        'audio': {
            'content': audio_content
        }
    }
    
    # Gửi yêu cầu đến API Speech-to-Text
    response = requests.post(url, json=request_data)
    
    if response.status_code == 200:
        result = response.json()
        if 'results' in result:
            return result['results'][0]['alternatives'][0]['transcript']
        else:
            return {'error': 'Speech could not be recognized, please try again.'}
    else:
        return {'error': f'API Error: {response.status_code} - {response.text}'}

def get_feedback(text_to_read, transcript):
    prompt = f""" 
    Bạn là một giáo viên tiếng Trung thân thiện. Hãy kiểm tra xem người học đã đọc đúng chưa và đưa ra phản hồi như trong một cuộc hội thoại.

    Câu yêu cầu đọc: "{text_to_read}"
    Câu người học đã đọc: "{transcript}"
    Chuyển cả 2 sang pinyin vì chỉ kiểm tra phát âm ví dụ như "他" và "她" đều đọc là "tā" nên người học đọc vẫn đúng (Lưu ý: pinyin là để bạn kiểm tra, sau khi kiểm tra xong thì không cần dùng pinyin nữa)
    Hãy kiểm tra và đưa ra phản hồi theo mẫu sau:

    Nếu đọc sai:
    Bạn đã đọc chưa chính xác. Hãy cùng xem lại nhé!
    Nhận xét: 
    [Nhận xét về cách đọc, chỉ ra lỗi cụ thể]
    
    Cách sửa: 
    [Hướng dẫn cách đọc đúng, giải thích rõ ràng]
    
    Đừng nản chí nhé! Hãy thử lại lần nữa. Bạn có thể làm được!

    Ví dụ cho trường hợp đọc sai: 
    'Bạn đã đọc chưa chính xác. Hãy cùng xem lại nhé!
    Nhận xét:
    Bạn đã đọc "立场" (lìchăng) thay vì "你好" (nǐ hǎo). Hai chữ này có cách đọc rất khác nhau.
    Cách sửa:
    Khi đọc "你好", bạn cần chú ý phát âm nhẹ âm sắc ở vần thứ hai ("-ǎo"). Âm "h" cũng được phát âm rất nhẹ, gần như không nghe thấy. Hãy thử đọc lại "你好" và chú ý đến cách phát âm này.'
    
    Nếu đọc đúng:
    Tuyệt vời! Bạn đã đọc rất chuẩn.
    
    Nhận xét: 
    [Nhận xét tích cực về cách đọc của người học]
    
    Hãy tiếp tục phát huy nhé! Bạn đang tiến bộ rất nhanh đấy.

    Ví dụ cho trường hợp đọc đúng:
    'Tuyệt vời! Bạn đã đọc rất chuẩn.
    Nhận xét:
    Bạn đã phát âm rõ ràng và chính xác từng âm tiết. Giọng điệu cũng rất tự nhiên.'
    
    Hãy tiếp tục phát huy nhé! Bạn đang tiến bộ rất nhanh đấy.
    Chỉ trả lời theo đúng định dạng trên, không thêm nội dung khác.
    """
    
    model = genai.GenerativeModel("gemini-pro")
    response = model.generate_content(prompt)
    return response.text