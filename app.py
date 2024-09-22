from flask import Flask, render_template, redirect, url_for, session, request, jsonify
import random
from radicals import radicals
from flask_session import Session
import unicodedata
from math import ceil
from urllib.parse import quote
import google.generativeai as genai
from datetime import datetime
import os
from dotenv import load_dotenv
import json
import subprocess
from github import Github
from datetime import datetime, timezone, timedelta

load_dotenv()  # Load biến môi trường từ .env

app = Flask(__name__)
app.secret_key = 'your_secret_key'
# Sử dụng server-side session để lưu trữ dữ liệu lớn
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_sets(radicals, radicals_per_set=20):
    sets = []
    for i in range(0, len(radicals), radicals_per_set):
        sets.append(radicals[i:i+radicals_per_set])
    return sets


radical_sets = get_sets(radicals)


def push_changes_to_github():
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN không được thiết lập.")
        return

    try:
        # Kết nối tới GitHub
        g = Github(GITHUB_TOKEN)

        repo = g.get_user().get_repo('radicals')

        # Đường dẫn tới tệp trong kho
        file_path = 'sentences.json'

        # Nội dung mới của tệp
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()

        # Kiểm tra xem tệp đã tồn tại trong kho chưa
        try:
            contents = repo.get_contents(file_path)
            # Cập nhật tệp
            repo.update_file(
                contents.path, "Cập nhật sentences.json", content, contents.sha)
        except Exception as e:
            # Nếu tệp chưa tồn tại, tạo mới
            repo.create_file(file_path, "Tạo sentences.json", content)

        print("Thay đổi đã được đẩy lên GitHub thành công.")
    except Exception as e:
        print(f"Lỗi khi đẩy thay đổi lên GitHub: {e}")


def remove_accents(input_str):
    # Hàm loại bỏ dấu tiếng Việt và dấu trong Pinyin
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return ''.join([c for c in nfkd_form if not unicodedata.combining(c)])


def get_new_sentence():
    utc_plus_7 = timezone(timedelta(hours=7))

    # Đường dẫn đến tệp JSON
    json_path = os.path.join(BASE_DIR, 'sentences.json')

    # Kiểm tra xem tệp JSON có tồn tại không
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            sentences = json.load(f)
    else:
        sentences = {}

    # Tập hợp các câu đã tồn tại
    existing_sentences = set()
    for sentence in sentences.values():
        existing_sentences.add(sentence['chinese'])

    result = None

    while True:
        prompt = """Hãy cung cấp một câu tiếng Trung ngắn ngẫu nhiên về bất kì chủ đề nào, bao gồm:

- Chữ Hán
- Pinyin
- Âm Hán Việt
- Nghĩa tiếng Việt

Hãy đảm bảo rằng:

- Câu trả lời chỉ bao gồm các thông tin trên, không thêm nội dung khác.
- Định dạng kết quả chính xác như sau:

Chữ Hán: ...
Pinyin: ...
Âm Hán Việt: ...
Nghĩa tiếng Việt: ...

Không thêm bất kỳ văn bản nào khác.

Đây là ví dụ:

Chữ Hán: 你好  
Pinyin: nǐ hǎo  
Âm Hán Việt: nhĩ hảo  
Nghĩa tiếng Việt: xin chào  

Chữ Hán: 我是学生  
Pinyin: wǒ shì xuéshēng  
Âm Hán Việt: ngã thị học sinh  
Nghĩa tiếng Việt: tôi là học sinh  

Chữ Hán: 今天是星期五  
Pinyin: jīntiān shì xīngqī wǔ  
Âm Hán Việt: kim thiên thị tinh kỳ ngũ  
Nghĩa tiếng Việt: hôm nay là thứ sáu  

Chữ Hán: 我正在学习汉语  
Pinyin: wǒ zhèngzài xuéxí hànyǔ  
Âm Hán Việt: ngã chính tại học tập hán ngữ  
Nghĩa tiếng Việt: tôi đang học tiếng Trung  

Chữ Hán: 他正在工作  
Pinyin: tā zhèngzài gōngzuò  
Âm Hán Việt: tha chính tại công tác  
Nghĩa tiếng Việt: anh ấy đang làm việc  

Chữ Hán: 你知道吗  
Pinyin: nǐ zhīdào ma  
Âm Hán Việt: nhĩ tri đạo ma  
Nghĩa tiếng Việt: bạn có biết không  

Chữ Hán: 我有一个弟弟  
Pinyin: wǒ yǒu yī gè dìdì  
Âm Hán Việt: ngã hữu nhất cá đệ đệ  
Nghĩa tiếng Việt: tôi có một em trai  

Nghĩa tiếng Việt: bạn biết nấu ăn không  

Chữ Hán: 她很漂亮  
Pinyin: tā hěn piàoliang  
Âm Hán Việt: tha ngận phiêu lượng  
Nghĩa tiếng Việt: cô ấy rất xinh đẹp  

Chữ Hán: 请给我菜单  
Pinyin: qǐng gěi wǒ càidān  
Âm Hán Việt: thỉnh cấp ngã thái đơn  
Nghĩa tiếng Việt: xin cho tôi thực đơn  

Chữ Hán: 我想学习更多  
Pinyin: wǒ xiǎng xuéxí gèng duō  
Âm Hán Việt: ngã tưởng học tập cánh đa  
Nghĩa tiếng Việt: tôi muốn học thêm nữa  

Chữ Hán: 这个多少钱  
Pinyin: zhège duōshǎo qián  
Âm Hán Việt: giá cách đa thiểu tiền  
Nghĩa tiếng Việt: cái này bao nhiêu tiền  

Chữ Hán: 我们去吃晚饭吧  
Pinyin: wǒmen qù chī wǎnfàn ba  
Âm Hán Việt: ngã môn khứ cật vãn phạn ba  
Nghĩa tiếng Việt: chúng ta đi ăn tối đi  

Chữ Hán: 你看过这本书吗  
Pinyin: nǐ kànguò zhè běn shū ma  
Âm Hán Việt: nhĩ khán quá giá bổn thư ma  
Nghĩa tiếng Việt: bạn đã đọc cuốn sách này chưa  

Chữ Hán: 你喜欢运动吗  
Pinyin: nǐ xǐhuān yùndòng ma  
Âm Hán Việt: nhĩ hỉ hoan vận động ma  
Nghĩa tiếng Việt: bạn có thích thể thao không  

Chữ Hán: 他是我的老师  
Pinyin: tā shì wǒ de lǎoshī  
Âm Hán Việt: tha thị ngã đích lão sư  
Nghĩa tiếng Việt: anh ấy là thầy giáo của tôi  

Chữ Hán: 你叫什么名字  
Pinyin: nǐ jiào shénme míngzì  
Âm Hán Việt: nhĩ khiếu thậm ma danh tự  
Nghĩa tiếng Việt: bạn tên là gì  

Chữ Hán: 我会说英语  
Pinyin: wǒ huì shuō yīngyǔ  
Âm Hán Việt: ngã hội thuyết anh ngữ  
Nghĩa tiếng Việt: tôi biết nói tiếng Anh  

Chữ Hán: 你要喝水吗  
Pinyin: nǐ yào hē shuǐ ma  
Âm Hán Việt: nhĩ yếu hát thủy ma  
Nghĩa tiếng Việt: bạn có muốn uống nước không  

Chữ Hán: 我有两个妹妹  
Pinyin: wǒ yǒu liǎng gè mèimèi  
Âm Hán Việt: ngã hữu lưỡng cá muội muội  
Nghĩa tiếng Việt: tôi có hai em gái  

Chữ Hán: 这是我的书包  
Pinyin: zhè shì wǒ de shūbāo  
Âm Hán Việt: giá thị ngã đích thư bao  
N

ghĩa tiếng Việt: đây là cặp sách của tôi  

Chữ Hán: 你住在哪里  
Pinyin: nǐ zhù zài nǎlǐ  
Âm Hán Việt: nhĩ trú tại nả lý  
Nghĩa tiếng Việt: bạn sống ở đâu  

Chữ Hán: 我们是好朋友  
Pinyin: wǒmen shì hǎo péngyǒu  
Âm Hán Việt: ngã môn thị hảo bằng hữu  
Nghĩa tiếng Việt: chúng tôi là bạn tốt  

Chữ Hán: 你喜欢看书吗  
Pinyin: nǐ xǐhuān kànshū ma  
Âm Hán Việt: nhĩ hỉ hoan khán thư ma  
Nghĩa tiếng Việt: bạn có thích đọc sách không  

Chữ Hán: 今天很热  
Pinyin: jīntiān hěn rè  
Âm Hán Việt: kim thiên ngận nhiệt  
Nghĩa tiếng Việt: hôm nay rất nóng  

Chữ Hán: 你吃过饺子吗  
Pinyin: nǐ chīguò jiǎozi ma  
Âm Hán Việt: nhĩ cật quá giáo tử ma  
Nghĩa tiếng Việt: bạn đã ăn bánh bao chưa  

Chữ Hán: 我想要一杯水  
Pinyin: wǒ xiǎng yào yī bēi shuǐ  
Âm Hán Việt: ngã tưởng yếu nhất bôi thủy  
Nghĩa tiếng Việt: tôi muốn một ly nước  

Chữ Hán: 请告诉我你的名字  
Pinyin: qǐng gàosu wǒ nǐ de míngzì  
Âm Hán Việt: thỉnh cáo tố ngã nhĩ đích danh tự  
Nghĩa tiếng Việt: xin cho tôi biết tên của bạn  

Chữ Hán: 我们去散步吧  
Pinyin: wǒmen qù sànbù ba  
Âm Hán Việt: ngã môn khứ tản bộ ba  
Nghĩa tiếng Việt: chúng ta đi dạo đi  

Chữ Hán: 你有兄弟姐妹吗  
Pinyin: nǐ yǒu xiōngdì jiěmèi ma  
Âm Hán Việt: nhĩ hữu huynh đệ tỷ muội ma  
Nghĩa tiếng Việt: bạn có anh chị em không  

Chữ Hán: 我喜欢吃饺子  
Pinyin: wǒ xǐhuān chī jiǎozi  
Âm Hán Việt: ngã hỉ hoan cật giáo tử  
Nghĩa tiếng Việt: tôi thích ăn bánh bao  

Chữ Hán: 你会写汉字吗  
Pinyin: nǐ huì xiě hànzì ma  
Âm Hán Việt: nhĩ hội tả hán tự ma  
Nghĩa tiếng Việt: bạn có biết viết chữ Hán không  

Chữ Hán: 我有很多朋友  
Pinyin: wǒ yǒu hěn duō péngyǒu  
Âm Hán Việt: ngã hữu ngận đa bằng hữu  
Nghĩa tiếng Việt: tôi có rất nhiều bạn bè  

Chữ Hán: 你在做什么  
Pinyin: nǐ zài zuò shénme  
Âm Hán Việt: nhĩ tại tố thậm ma  
Nghĩa tiếng Việt: bạn đang làm gì  

Chữ Hán: 我喜欢听音乐  
Pinyin: wǒ xǐhuān tīng yīnyuè  
Âm Hán Việt: ngã hỉ hoan thính âm nhạc  
Nghĩa tiếng Việt: tôi thích nghe nhạc  

Chữ Hán: 你有车吗  
Pinyin: nǐ yǒu chē ma  
Âm Hán Việt: nhĩ hữu xa ma  
Nghĩa tiếng Việt: bạn có xe không  

Chữ Hán: 我们去吃早餐吧  
Pinyin: wǒmen qù chī zǎocān ba  
Âm Hán Việt: ngã môn khứ cật tảo xan ba  
Nghĩa tiếng Việt: chúng ta đi ăn sáng đi  

Chữ Hán: 你今天开心吗  
Pinyin: nǐ jīntiān kāixīn ma  
Âm Hán Việt: nhĩ kim thiên khai tâm ma  
Nghĩa tiếng Việt: hôm nay bạn vui không  
  
Chữ Hán: 你会做饭吗  
Pinyin: nǐ huì zuò fàn ma  
Âm Hán Việt: nhĩ hội tố phạn ma  
Nghĩa tiếng Việt: bạn biết nấu ăn không   

Chữ Hán: 风景如画
Pinyin: fēngjǐng rú huà
Âm Hán Việt: phong cảnh như họa
Nghĩa tiếng Việt: phong cảnh như tranh vẽ

Chữ Hán: 青山绿水
Pinyin: qīngshān lǜshuǐ
Âm Hán Việt: thanh sơn lục thủy
Nghĩa tiếng Việt: núi xanh nước biếc

Chữ Hán: 阳光明媚
Pinyin: yángguāng míngmèi
Âm Hán Việt: dương quang minh mị
Nghĩa tiếng Việt: ánh nắng rực rỡ

Chữ Hán: 山清水秀
Pinyin: shānqīng shuǐxiù
Âm Hán Việt: sơn thanh thủy tú
Nghĩa tiếng Việt: núi non tươi đẹp, sông nước hữu tình

Chữ Hán: 流水潺潺
Pinyin: liúshuǐ chánchán
Âm Hán Việt: lưu thủy triền triền
Nghĩa tiếng Việt: dòng nước chảy róc rách

Chữ Hán: 碧海蓝天
Pinyin: bìhǎi lántiān
Âm Hán Việt: bích hải lam thiên
Nghĩa tiếng Việt: biển xanh trời biếc

Chữ Hán: 云雾缭绕
Pinyin: yúnwù liáorào
Âm Hán Việt: vân vụ liêu nhiễu
Nghĩa tiếng Việt: mây mù bao phủ

Chữ Hán: 夕阳西下
Pinyin: xīyáng xīxià
Âm Hán Việt: tịch dương tây hạ
Nghĩa tiếng Việt: hoàng hôn buông xuống

Chữ Hán: 湖光山色
Pinyin: húguāng shānsè
Âm Hán Việt: hồ quang sơn sắc
Nghĩa tiếng Việt: cảnh sắc núi hồ

Chữ Hán: 柳暗花明
Pinyin: liǔ'àn huāmíng
Âm Hán Việt: liễu ám hoa minh
Nghĩa tiếng Việt: liễu rủ hoa tươi

Chữ Hán: 山川秀丽
Pinyin: shānchuān xiùlì
Âm Hán Việt: sơn xuyên tú lệ
Nghĩa tiếng Việt: sông núi tươi đẹp

Chữ Hán: 万紫千红
Pinyin: wànzǐ qiānhóng
Âm Hán Việt: vạn tử thiên hồng
Nghĩa tiếng Việt: muôn hoa đua sắc

Chữ Hán: 天高云淡
Pinyin: tiāngāo yúndàn
Âm Hán Việt: thiên cao vân đạm
Nghĩa tiếng Việt: trời cao mây nhạt

Chữ Hán: 水天一色
Pinyin: shuǐtiān yīsè
Âm Hán Việt: thủy thiên nhất sắc
Nghĩa tiếng Việt: trời nước một màu

Chữ Hán: 白云苍狗
Pinyin: báiyún cānggǒu
Âm Hán Việt: bạch vân thương cẩu
Nghĩa tiếng Việt: mây trắng bay lượn

Chữ Hán: 草长莺飞
Pinyin: cǎo zhǎng yīng fēi
Âm Hán Việt: thảo trưởng oanh phi
Nghĩa tiếng Việt: cỏ mọc chim bay

Chữ Hán: 田园风光
Pinyin: tiányuán fēngguāng
Âm Hán Việt: điền viên phong quang
Nghĩa tiếng Việt: phong cảnh đồng quê

Chữ Hán: 春暖花开
Pinyin: chūnnuǎn huākāi
Âm Hán Việt: xuân noãn hoa khai
Nghĩa tiếng Việt: xuân ấm hoa nở

Chữ Hán: 四季如春
Pinyin: sìjì rú chūn
Âm Hán Việt: tứ quý như xuân
Nghĩa tiếng Việt: bốn mùa như xuân

Chữ Hán: 绿树成荫
Pinyin: lǜshù chéng yīn
Âm Hán Việt: lục thụ thành âm
Nghĩa tiếng Việt: cây xanh rợp bóng

Chữ Hán: 苍翠欲滴
Pinyin: cāngcuì yùdī
Âm Hán Việt: thương thúy dục trích
Nghĩa tiếng Việt: xanh biếc như muốn nhỏ nước

Chữ Hán: 雪山皑皑
Pinyin: xuěshān ái'ái
Âm Hán Việt: tuyết sơn ai ai
Nghĩa tiếng Việt: núi tuyết trắng xóa

Chữ Hán: 山高水长
Pinyin: shān gāo shuǐ cháng
Âm Hán Việt: sơn cao thủy trường
Nghĩa tiếng Việt: núi cao sông dài

Chữ Hán: 林海雪原
Pinyin: línhǎi xuěyuán
Âm Hán Việt: lâm hải tuyết nguyên
Nghĩa tiếng Việt: rừng tuyết mênh mông

Chữ Hán: 星罗棋布
Pinyin: xīngluó qíbù
Âm Hán Việt: tinh la kỳ bố
Nghĩa tiếng Việt: như sao giăng khắp trời

Chữ Hán: 山花烂漫
Pinyin: shānhuā lànmàn
Âm Hán Việt: sơn hoa lạn mạn
Nghĩa tiếng Việt: hoa núi nở rộ

Chữ Hán: 夜色迷人
Pinyin: yèsè mírén
Âm Hán Việt: dạ sắc mê nhân
Nghĩa tiếng Việt: cảnh đêm mê hoặc

Chữ Hán: 日出东方
Pinyin: rìchū dōngfāng
Âm Hán Việt: nhật xuất đông phương
Nghĩa tiếng Việt: mặt trời mọc ở phía đông

Chữ Hán: 海阔天空
Pinyin: hǎikuò tiānkōng
Âm Hán Việt: hải khoát thiên không
Nghĩa tiếng Việt: biển rộng trời cao

Chữ Hán: 湖光倒影
Pinyin: húguāng dàoyǐng
Âm Hán Việt: hồ quang đảo ảnh
Nghĩa tiếng Việt: ánh nước phản chiếu
"""
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
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

            # Kiểm tra định dạng kết quả
            if len(temp_result) < 4:
                continue  # Nếu thiếu thông tin, chạy lại prompt

            # Kiểm tra xem câu đã tồn tại chưa
            if temp_result['chinese'] in existing_sentences:
                continue  # Nếu đã tồn tại, chạy lại prompt
            else:
                result = temp_result
                break  # Thoát khỏi vòng lặp khi có câu mới
        except Exception as e:
            print(f"Lỗi khi gọi Google Generative AI API: {e}")
            result = None
            break  # Thoát khỏi vòng lặp nếu có lỗi

    if result:
        # Tạo một khóa duy nhất cho câu mới, có thể sử dụng timestamp
        timestamp = datetime.now(utc_plus_7).strftime("%Y-%m-%d %H:%M:%S")
        sentences[timestamp] = result

        # Ghi lại tệp JSON
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(sentences, f, ensure_ascii=False, indent=4)
        push_changes_to_github()

    return result


# Trang chủ


@app.route('/')
def home():
    sentence_data = get_new_sentence()
    return render_template('home.html', sentence=sentence_data)


@app.route('/history')
def history():
    # Đường dẫn đến tệp JSON
    json_path = os.path.join(BASE_DIR, 'sentences.json')

    # Đọc dữ liệu từ tệp JSON
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            sentences_dict = json.load(f)
    else:
        sentences_dict = {}

    # Chuyển đổi sang danh sách và sắp xếp
    sentences = [
        {'date': date, **data} for date, data in sentences_dict.items()
    ]
    sentences.sort(key=lambda x: x['date'], reverse=True)

    return render_template('history.html', sentences=sentences)


# ================== Phần Học ==================


@app.route('/radicals', methods=['GET'])
def all_radicals():
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20  # Số bộ thủ mỗi trang

    if query:
        query_no_accents = remove_accents(query.lower())
        # Tìm kiếm theo bộ thủ, nghĩa hoặc Pinyin (không phân biệt dấu)
        filtered_radicals = [
            r for r in radicals
            if query in r['radical'] or
            query_no_accents in remove_accents(r['meaning'].lower()) or
            query_no_accents in remove_accents(r['pinyin'].lower())
        ]
    else:
        filtered_radicals = radicals

    total = len(filtered_radicals)
    pages = ceil(total / per_page)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_radicals = filtered_radicals[start:end]

    return render_template('radicals.html', radicals=paginated_radicals, query=query, page=page, pages=pages, per_page=per_page)


# Đặt tên cho route để sử dụng trong url_for
app.add_url_rule('/radicals', 'all_radicals', all_radicals)

# Chọn chế độ học


@app.route('/learn')
def learn():
    return render_template('learn.html')

# Học theo thứ tự


@app.route('/learn/sequential', methods=['GET'])
def learn_sequential():
    index = request.args.get('index', default=1, type=int) - 1
    if index < 0:
        index = 0
    elif index >= len(radicals):
        index = len(radicals) - 1

    radical = radicals[index]
    total_radicals = len(radicals)

    prev_index = index if index > 0 else None
    next_index = index + 2 if index < total_radicals - 1 else None

    return render_template('flashcard_sequential.html', radical=radical, index=index + 1, total=total_radicals, prev_index=prev_index, next_index=next_index)


@app.route('/learn/sequential/next')
def next_flashcard_sequential():
    index = session.get('learn_index', 0) + 1
    if index >= len(radicals):
        index = 0
    session['learn_index'] = index
    return redirect(url_for('learn_sequential'))

# Học ngẫu nhiên


@app.route('/learn/random')
def learn_random():
    radical = random.choice(radicals)
    return render_template('flashcard.html', radical=radical, next_url=url_for('learn_random'))

# ================== Phần Kiểm Tra ==================

# Chọn chế độ kiểm tra


@app.route('/test')
def test():
    return render_template('test.html', total_sets=len(radical_sets))

# Kiểm tra theo bộ đề


# ... Các import và khai báo khác ...


@app.route('/test/set/<int:set_number>', methods=['GET', 'POST'])
def test_set(set_number):
    test_type = request.args.get('test_type', 'meaning')
    selected_radicals = radical_sets[set_number - 1]
    total_questions = len(selected_radicals)

    session_key = f'test_data_set_{set_number}_{test_type}'

    if session.get('current_set') != set_number or session.get('test_type') != test_type or session_key not in session:
        session['current_set'] = set_number
        session['test_type'] = test_type
        test_data = {
            'questions': [],
            'answers': {},
            'marked_questions': []
        }
        for idx, radical in enumerate(selected_radicals):
            if test_type == 'meaning':
                correct_answer = radical['meaning']
            else:
                correct_answer = radical['pinyin']
            question = {
                'index': idx + 1,
                'radical': radical['radical'],
                'correct_answer': correct_answer,
                'choices': generate_choices(correct_answer, test_type),
                'selected_choice': None,
                'is_marked': False
            }
            test_data['questions'].append(question)
        session[session_key] = test_data

    test_data = session[session_key]

    if request.method == 'POST':
        action = request.form.get('action')
        question_index = int(request.form.get('question_index', 1)) - 1
        if action == 'save_answer':
            selected_choice = request.form.get('selected_choice')
            test_data['questions'][question_index]['selected_choice'] = selected_choice
            session[session_key] = test_data
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'success', 'question_index': question_index + 1})
            else:
                return redirect(url_for('test_set', set_number=set_number, test_type=test_type))
        elif action == 'mark_question':
            test_data['questions'][question_index]['is_marked'] = not test_data['questions'][question_index]['is_marked']
            session[session_key] = test_data
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'success', 'question_index': question_index + 1, 'is_marked': test_data['questions'][question_index]['is_marked']})
            else:
                return redirect(url_for('test_set', set_number=set_number, q=question_index+1, test_type=test_type))
        elif action == 'submit_test':
            score = 0
            answers = []
            for q in test_data['questions']:
                is_correct = q['selected_choice'] == q['correct_answer']
                if is_correct:
                    score += 1
                answers.append({
                    'radical': q['radical'],
                    'selected': q['selected_choice'],
                    'correct': q['correct_answer'],
                    'is_correct': is_correct
                })
            session.pop(session_key, None)
            session.pop('current_set', None)
            session.pop('test_type', None)
            return render_template('result.html', score=score, total=total_questions, answers=answers, test_type=test_type)

    current_question_index = int(request.args.get('q', 1)) - 1
    if current_question_index < 0 or current_question_index >= total_questions:
        current_question_index = 0
    current_question = test_data['questions'][current_question_index]

    return render_template('test_navigation.html', test_data=test_data, set_number=set_number, current_question=current_question, total_questions=total_questions, test_type=test_type)


def generate_choices(correct_answer, test_type):
    choices = [correct_answer]
    if test_type == 'meaning':
        other_options = [r['meaning']
                         for r in radicals if r['meaning'] != correct_answer]
    elif test_type == 'pinyin':
        other_options = [r['pinyin']
                         for r in radicals if r['pinyin'] != correct_answer]
    choices.extend(random.sample(other_options, min(3, len(other_options))))
    random.shuffle(choices)
    return choices


# Review


@app.route('/review')
def review():
    import json
    answers = request.args.get('answers')
    answers = json.loads(answers)
    test_type = request.args.get('test_type', 'meaning')
    return render_template('review.html', answers=answers, test_type=test_type)

# Kiểm tra ngẫu nhiên


@app.route('/test/random', methods=['GET', 'POST'])
def test_random():
    test_type = request.args.get('test_type', 'meaning')
    total_questions = 20
    session_key = f'test_data_random_{test_type}'

    if session_key not in session:
        test_data = {
            'questions': [],
            'answers': {},
            'marked_questions': []
        }
        selected_radicals = random.sample(radicals, total_questions)
        for idx, radical in enumerate(selected_radicals):
            if test_type == 'meaning':
                correct_answer = radical['meaning']
            else:
                correct_answer = radical['pinyin']
            question = {
                'index': idx + 1,
                'radical': radical['radical'],
                'correct_answer': correct_answer,
                'choices': generate_choices(correct_answer, test_type),
                'selected_choice': None,
                'is_marked': False
            }
            test_data['questions'].append(question)
        session[session_key] = test_data

    test_data = session[session_key]

    if request.method == 'POST':
        action = request.form.get('action')
        question_index = int(request.form.get('question_index', 1)) - 1
        if action == 'save_answer':
            selected_choice = request.form.get('selected_choice')
            test_data['questions'][question_index]['selected_choice'] = selected_choice
            session[session_key] = test_data
            return redirect(url_for('test_random', q=question_index+1, test_type=test_type))
        elif action == 'mark_question':
            test_data['questions'][question_index]['is_marked'] = not test_data['questions'][question_index]['is_marked']
            session[session_key] = test_data
            return redirect(url_for('test_random', q=question_index+1, test_type=test_type))
        elif action == 'submit_test':
            score = 0
            answers = []
            for q in test_data['questions']:
                is_correct = q['selected_choice'] == q['correct_answer']
                if is_correct:
                    score += 1
                answers.append({
                    'radical': q['radical'],
                    'selected': q['selected_choice'],
                    'correct': q['correct_answer'],
                    'is_correct': is_correct
                })
            session.pop(session_key, None)
            return render_template('result.html', score=score, total=total_questions, answers=answers, test_type=test_type)

    current_question_index = int(request.args.get('q', 1)) - 1
    if current_question_index < 0 or current_question_index >= total_questions:
        current_question_index = 0
    current_question = test_data['questions'][current_question_index]

    return render_template('test_navigation.html', test_data=test_data, current_question=current_question, total_questions=total_questions, set_number=None, test_type=test_type)


if __name__ == '__main__':
    app.run(debug=False)
