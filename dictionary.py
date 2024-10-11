import requests
from bs4 import BeautifulSoup
from utils import process_meanings

def get_hannom_info(character):
  url = f"https://hvdic.thivien.net/whv/{character}"
  response = requests.get(url)
  soup = BeautifulSoup(response.content, 'html.parser')

  result = {
      'character': character,
      'han_viet': None,
      'pinyin': None,  # Add Pinyin field
      'total_strokes': None,
      'radical': None,
      'meanings': None,
      'found': False
  }

  # Check if there is a result
  info_div = soup.find('div', class_='info')
  if info_div and "Có 1 kết quả:" in info_div.text:
      result['found'] = True
      hvres_div = soup.find('div', class_='hvres')
      if hvres_div:
          # Get Han Viet reading
          han_viet = hvres_div.find('a', class_='hvres-goto-link')
          if han_viet:
              result['han_viet'] = han_viet.text.strip()

          # Get Pinyin
          pinyin_tag = hvres_div.find(string=lambda x: x and 'Âm Pinyin:' in x)
          if pinyin_tag:
              pinyin_element = pinyin_tag.find_next('a')
              if pinyin_element:
                  result['pinyin'] = pinyin_element.text.strip()

          # Get meanings
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
          # Find "Âm Hán Việt:"
          av_tag = main_details.find(string=lambda x: x and 'Âm Hán Việt:' in x)
          if av_tag:
              parent = av_tag.parent
              spans = parent.find_all('span', class_='hvres-goto-link')
              readings = [span.get_text(strip=True) for span in spans]
              result['han_viet'] = ', '.join(readings)

          # Find "Pinyin:"
          pinyin_tag = main_details.find(string=lambda x: x and 'Âm Pinyin:' in x)
          if pinyin_tag:
              pinyin_element = pinyin_tag.find_next('a')
              if pinyin_element:
                  result['pinyin'] = pinyin_element.text.strip()

          # Find "Tổng nét:"
          tn_tag = main_details.find(string=lambda x: x and 'Tổng nét:' in x)
          if tn_tag:
              tn_text = tn_tag.strip()
              tn = tn_text.split('Tổng nét:')[-1].strip()
              result['total_strokes'] = tn

          # Find "Bộ:"
          b_tag = main_details.find(string=lambda x: x and 'Bộ:' in x)
          if b_tag:
              a_tag = b_tag.find_next('a')
              if a_tag:
                  radical = a_tag.get_text(strip=True)
                  extra_info = a_tag.next_sibling
                  if extra_info:
                      radical += ' ' + extra_info.strip()
                  result['radical'] = radical

      # Process meanings
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
                          if len(meanings) >= 2:  # Adjust if you want more meanings
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