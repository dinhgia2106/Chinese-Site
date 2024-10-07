import requests
import base64
import re
import os

api_key = os.getenv("GOOGLE_TEXT_TO_SPEECH_API_KEY")

url = f'https://speech.googleapis.com/v1/speech:recognize?key={api_key}'

with open('gǔn.mp3', 'rb') as audio_file:
    audio_content = base64.b64encode(audio_file.read()).decode('utf-8')

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

response = requests.post(url, json=request_data)

if response.status_code == 200:
    result = response.json()
    if 'results' in result:
        transcript = result['results'][0]['alternatives'][0]['transcript']
        print(transcript)
    else:
        print("Không nhận dạng được, vui lòng thử lại.")
else:
    print(f"Lỗi: {response.status_code} - {response.text}")
