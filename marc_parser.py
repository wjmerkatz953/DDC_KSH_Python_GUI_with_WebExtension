# -*- coding: utf-8 -*-
"""
marc_parser.py - MARC 데이터 파싱 및 F1-F8 추출 로직.
버전: 1.0.0
생성일: 2025-07-19
"""

import re
# app_instance는 GUI의 로그 메시지 출력을 위해 필요합니다.


def extract_subfield(marc_string, subfield_code):
    """
    MARC 필드 문자열에서 특정 서브필드 코드를 추출합니다.
    예: "▼a아토피, 당신 탓이 아닙니다 :▼b100가지 의학 연구로 밝혀낸 아토피 치료의 오해와 진실" 에서 'a'를 추출
    """
    pattern = rf"▼{re.escape(subfield_code)}(.*?)(?:▼\S|$)"
    match = re.search(pattern, marc_string)
    if match:
        return match.group(1).strip()
    return ""


def contains_cjk_characters(text):
    """
    CJK (한글, 한자) 문자가 텍스트에 포함되어 있는지 확인하는 헬퍼 함수.
    Args:
        text (str): 확인할 텍스트.
    Returns:
        boolean: CJK 문자가 있으면 true, 없으면 false.
    """
    if not text or not isinstance(text, str):
        return False
    cjk_regex = re.compile(r'[\uAC00-\uD7AF\u4E00-\u9FFF]')
    return bool(cjk_regex.search(text))


def remove_leading_article(text):
    """
    텍스트에서 선행하는 관사를 제거하는 헬퍼 함수.
    Args:
        text (str): 처리할 텍스트.
    Returns:
        str: 관사가 제거된 텍스트.
    """
    text = text.strip()
    articles = {
        'en': ['the', 'a', 'an'],
        'fr': ['le', 'la', 'les', 'l\'', 'un', 'une', 'des'],
        'es': ['el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas'],
        'de': ['der', 'die', 'das', 'dem', 'den', 'des', 'ein', 'eine', 'einen', 'einem', 'eines'],
        'ru': [],
        'pt': ['o', 'a', 'os', 'as', 'um', 'uma', 'uns', 'umas']
    }

    for lang_code in articles:
        for article in articles[lang_code]:
            regex = re.compile(rf"^{re.escape(article)}\s+", re.IGNORECASE)
            if regex.match(text):
                return regex.sub('', text, 1).strip()
    return text


def extract_marc_data_to_f_fields(raw_marc_text, app_instance):
    """
    원문 MARC 텍스트에서 F1-F10에 해당하는 데이터를 추출합니다.
    (F9: 090 청구기호, F10: 별치기호 판정)
    """
    f_fields = {
        "F1_ISBN": "(ISBN 추출 실패)",
        "F2_Author_SurnameOrCorporate": "(저자 추출 실패)",
        "F3_Author_FullOrMultiple": "(저자 추출 실패)",
        "F4_245_Unprocessed": "(245 필드 추출 실패)",
        "F5_LatinNumericDetection": "",
        "F6_LatinNumericToKorean": "추후 알파벳/숫자 to 한글 변환기능 추가",
        "F7_OriginalTitle_WithArticle": "(원서명 추출 실패)",
        "F8_OriginalTitle_WithoutArticle": "(정관사 제거 원서명 추출 실패)",
        "F9_CallNumber": "(청구기호 추출 실패)",
        "F10_SpecialCallNumber": "",  # F10 추가
        "F11_DDC": "",  # ✅ [추가] F11 DDC 번호 (082 필드)
    }

    # --- 1. MARC 데이터 재구성 로직 (한 번만 실행) ---
    raw_lines = raw_marc_text.split('\n')
    trimmed_lines = [line.strip() for line in raw_lines if line.strip() != ""]
    marc_data_lines = []
    found_marc_start = False
    for i in range(len(trimmed_lines)):
        current_line = trimmed_lines[i]
        if current_line == "LDR":
            if i + 1 < len(trimmed_lines) and trimmed_lines[i + 1] == "상태":
                found_marc_start = True
                marc_data_lines = trimmed_lines[i:]
                break
    if not found_marc_start:
        app_instance.log_message(
            "경고: MARC 데이터 시작점('LDR' 및 '상태' 패턴)을 찾을 수 없습니다. 추출을 건너뜁니다.", level="WARNING")
        return f_fields

    reconstructed_marc_fields = {}
    current_tag = None
    current_field_parts = []
    for line in marc_data_lines:
        stripped_line = line.strip()
        tag_match = re.match(r'^(\d{2,3})', stripped_line)
        if re.match(r'^\d{9,10}$', stripped_line):
            if current_tag and current_field_parts:
                full_content = "".join(current_field_parts).strip().removesuffix('▲')
                if current_tag not in reconstructed_marc_fields:
                    reconstructed_marc_fields[current_tag] = []
                reconstructed_marc_fields[current_tag].append(full_content)
            current_tag = None
            current_field_parts = []
            continue
        if re.match(r'^▲[^\d\s]', stripped_line) or (stripped_line.startswith('▲') and len(stripped_line) < 5 and not re.match(r'^▲\d{3}', stripped_line)):
            app_instance.log_message(
                f"정보: MARC 데이터 끝 패턴 감지: '{stripped_line}'. 필드 재구성을 중단합니다.", level="INFO")
            if current_tag and current_field_parts:
                full_content = "".join(current_field_parts).strip().removesuffix('▲')
                if current_tag not in reconstructed_marc_fields:
                    reconstructed_marc_fields[current_tag] = []
                reconstructed_marc_fields[current_tag].append(full_content)
            break
        if tag_match:
            if current_tag and current_field_parts:
                full_content = "".join(current_field_parts).strip().removesuffix('▲')
                if current_tag not in reconstructed_marc_fields:
                    reconstructed_marc_fields[current_tag] = []
                reconstructed_marc_fields[current_tag].append(full_content)
            current_tag = tag_match.group(1).zfill(3)
            current_field_parts = [stripped_line[len(tag_match.group(1)):]]
        elif current_tag:
            current_field_parts.append(stripped_line)
    if current_tag and current_field_parts:
        full_content = "".join(current_field_parts).strip().removesuffix('▲')
        if current_tag not in reconstructed_marc_fields:
            reconstructed_marc_fields[current_tag] = []
        reconstructed_marc_fields[current_tag].append(full_content)

    if '020' in reconstructed_marc_fields:
        isbn_regex_pattern = r'▼a([\d\-X]{10,17})(?:\s*\(.*?\))?\s*(?:▼g|▲|$)'
        for content in reconstructed_marc_fields['020']:
            isbn_match = re.search(isbn_regex_pattern, content, re.IGNORECASE)
            if isbn_match and isbn_match.group(1):
                f_fields["F1_ISBN"] = isbn_match.group(1).replace('-', '')
                app_instance.log_message(
                    f"정보: F1 (ISBN) 추출 성공: {f_fields['F1_ISBN']}")
                break
        else:
            app_instance.log_message(
                "경고: F1 (ISBN)을 020 필드에서 찾을 수 없습니다.", level="WARNING")
    else:
        app_instance.log_message(
            "경고: 020 (ISBN) 필드를 찾을 수 없습니다.", level="WARNING")
    temp500_original_author = None
    temp1xx7xx_authors = []
    if '500' in reconstructed_marc_fields:
        for content in reconstructed_marc_fields['500']:
            if "원저자명:" in content:
                match = re.search(r'▼a원저자명:\s*([^▲]+)▲?', content)
                if match and match.group(1):
                    temp500_original_author = match.group(1).strip()
                    app_instance.log_message(
                        f"정보: 500 필드에서 원저자명 발견: \"{temp500_original_author}\"")
                    break
    for tag in ['100', '110', '700', '710']:
        if tag in reconstructed_marc_fields:
            for content in reconstructed_marc_fields[tag]:
                extracted_name = ""
                match = None
                if tag in ['100', '700']:
                    match = re.search(r'▼a(.*?)(?:▼\S|▲|$)', content)
                    if match and match.group(1):
                        extracted_name = match.group(1).strip()
                        if '참고정보' in extracted_name:
                            extracted_name = extracted_name.split('참고정보')[
                                0].strip()
                        extracted_name = re.sub(r',?$', '', extracted_name)
                        extracted_name = extracted_name.replace(
                            '▲', '').strip()
                elif tag in ['110', '710']:
                    match = re.search(r'▼a([^▲]+)▲?', content)
                    if match and match.group(1):
                        extracted_name = match.group(1).strip()
                        extracted_name = extracted_name.replace(
                            '▲', '').strip()
                if extracted_name and extracted_name != '▲':
                    temp1xx7xx_authors.append(extracted_name)
                    app_instance.log_message(
                        f"정보: {tag} 필드에서 저자명 추출: \"{extracted_name}\"")
    if temp500_original_author and contains_cjk_characters(temp500_original_author):
        f_fields["F2_Author_SurnameOrCorporate"] = re.sub(
            r'\s*\(.*?\)', '', temp500_original_author.split(',')[0]).strip()
        app_instance.log_message(
            f"정보: F2 (저자-단일) 500 필드 CJK 저자명 사용: \"{f_fields['F2_Author_SurnameOrCorporate']}\"")
    elif temp1xx7xx_authors:
        first_author = temp1xx7xx_authors[0]
        if ',' in first_author:
            f_fields["F2_Author_SurnameOrCorporate"] = first_author.split(',')[
                0].strip()
            app_instance.log_message(
                f"정보: F2 (저자-단일) 1xx/7xx 필드 성 추출: \"{f_fields['F2_Author_SurnameOrCorporate']}\"")
        else:
            f_fields["F2_Author_SurnameOrCorporate"] = first_author
            app_instance.log_message(
                f"정보: F2 (저자-단일) 1xx/7xx 필드 전체 이름/단체명 사용: \"{f_fields['F2_Author_SurnameOrCorporate']}\"")
    else:
        app_instance.log_message(
            "경고: F2 (저자-단일) 추출 실패. 관련 저자 정보를 찾을 수 없습니다.", level="WARNING")
    if temp1xx7xx_authors:
        f_fields["F3_Author_FullOrMultiple"] = ", ".join(temp1xx7xx_authors)
        app_instance.log_message(f"정보: F3 (저자-전체/복수) 추출 성공.")
    else:
        app_instance.log_message(
            "경고: F3 (저자-전체/복수) 추출 실패. 관련 저자 정보를 찾을 수 없습니다.", level="WARNING")
    if '245' in reconstructed_marc_fields:
        for content in reconstructed_marc_fields['245']:
            match_a = None
            if content.startswith("10▼a"):
                f_fields["F4_245_Unprocessed"] = content[len(
                    "10▼a"):].replace('▲', '').strip()
                app_instance.log_message(f"정보: F4 (245 무가공) 추출 성공 (245 10).")
            elif content.startswith("00▼a"):
                f_fields["F4_245_Unprocessed"] = content[len(
                    "00▼a"):].replace('▲', '').strip()
                app_instance.log_message(f"정보: F4 (245 무가공) 추출 성공 (245 00).")
            else:
                match_a = re.search(r'▼a(.*?)(?:▼\S|$)', content)
                if match_a and match_a.group(1):
                    f_fields["F4_245_Unprocessed"] = match_a.group(1).strip()
                    app_instance.log_message(
                        f"정보: F4 (245 무가공) 추출 성공 (일반 245).")
                else:
                    app_instance.log_message(
                        "경고: F4 (245 무가공) 필드에서 ▼a 서브필드를 찾을 수 없습니다.", level="WARNING")
            break
    else:
        app_instance.log_message(
            "경고: 245 필드를 찾을 수 없습니다. F4 (245 무가공) 추출 실패.", level="WARNING")
    if f_fields["F4_245_Unprocessed"] != "(245 필드 추출 실패)":
        text_to_analyze = f_fields["F4_245_Unprocessed"]
        cross_delimiter = "=▼x"
        cross_index = text_to_analyze.find(cross_delimiter)
        if cross_index != -1:
            text_to_analyze = text_to_analyze[:cross_index]
        marc_subfield_delimiter_pattern = re.compile(r'[:;/]?▼[a-z0-9]')
        cleaned_text = marc_subfield_delimiter_pattern.sub('', text_to_analyze)
        latin_numeric_regex = re.compile(
            r'[A-Za-z0-9\u00C0-\u017F]+(?:[\- ]?[A-Za-z0-9\u00C0-\u017F]+)*|\d+(?:[\- ]?\d+)*')
        matches = latin_numeric_regex.findall(cleaned_text)
        filtered_matches = [
            m for m in matches if not contains_cjk_characters(m)]
        if filtered_matches:
            f_fields["F5_LatinNumericDetection"] = " ".join(filtered_matches)
            app_instance.log_message(
                f"정보: F5 (245 라틴/숫자) 추출 성공: \"{f_fields['F5_LatinNumericDetection']}\"")
        else:
            f_fields["F5_LatinNumericDetection"] = ""
            app_instance.log_message(
                "정보: F5 (245 라틴/숫자) 추출된 내용 없음.", level="INFO")
    else:
        app_instance.log_message(
            "경고: F4 (245 무가공) 필드가 없어 F5 (245 라틴/숫자) 추출을 건너킵니다.", level="WARNING")
    found_246_19_content = None
    found_246_39_content = None
    if '246' in reconstructed_marc_fields:
        for content in reconstructed_marc_fields['246']:
            indicator_match_in_content = re.match(
                r'^\s*([0-9#\s]{1,4})▼a', content)
            combined_indicators = ""
            if indicator_match_in_content and indicator_match_in_content.group(1):
                combined_indicators = indicator_match_in_content.group(
                    1).replace(' ', '').replace('#', '')
            match_a = re.search(r'▼a(.*?)(?:▼\S|$)', content)
            extracted_variant_title = ""
            if match_a and match_a.group(1):
                extracted_variant_title = match_a.group(1).strip()
                refine_match = re.match(
                    r'(.*?)(?:\s*:▼b|\s*\/▼d|\s*=\S+|\s*:?\s*▲?$)', extracted_variant_title)
                if refine_match and refine_match.group(1):
                    extracted_variant_title = refine_match.group(1).strip()
                    extracted_variant_title = extracted_variant_title.replace(
                        '▲', '').strip()
            if extracted_variant_title:
                if combined_indicators == "19" and found_246_19_content is None:
                    found_246_19_content = extracted_variant_title
                    app_instance.log_message(
                        f"정보: 246 19 필드에서 원서명 발견: \"{found_246_19_content}\"")
                elif combined_indicators == "39" and found_246_39_content is None:
                    found_246_39_content = extracted_variant_title
                    app_instance.log_message(
                        f"정보: 246 39 필드에서 원서명 발견: \"{found_246_39_content}\"")
    if found_246_19_content:
        f_fields["F7_OriginalTitle_WithArticle"] = found_246_19_content
        app_instance.log_message(f"정보: F7 (원서명-관사 포함) 추출 성공 (246 19 우선).")
    elif found_246_39_content:
        f_fields["F7_OriginalTitle_WithArticle"] = found_246_39_content
        app_instance.log_message(f"정보: F7 (원서명-관사 포함) 추출 성공 (246 39 사용).")
    else:
        f_fields["F7_OriginalTitle_WithArticle"] = "(원서명 추출 실패)"
        app_instance.log_message(
            "경고: F7 (원서명-관사 포함) 추출 실패. 246 19 또는 246 39 필드를 찾을 수 없습니다.", level="WARNING")
    if f_fields["F7_OriginalTitle_WithArticle"] != "(원서명 추출 실패)":
        f_fields["F8_OriginalTitle_WithoutArticle"] = remove_leading_article(
            f_fields["F7_OriginalTitle_WithArticle"])
        app_instance.log_message(f"정보: F8 (원서명-관사 제거) 추출 성공.")
    else:
        app_instance.log_message(
            "경고: F8 (원서명-관사 제거) 추출 실패. F7 필드가 없어 변환할 수 없습니다.", level="WARNING")

    # --- F9 청구기호(Call Number) 추출 로직 ---
    if '090' in reconstructed_marc_fields:
        content_090 = reconstructed_marc_fields['090'][0]
        sub_a = extract_subfield(content_090, 'a')
        sub_b = extract_subfield(content_090, 'b')
        call_number = (sub_a + sub_b).strip()
        if call_number:
            f_fields["F9_CallNumber"] = call_number
            app_instance.log_message(f"정보: F9 (청구기호) 추출 성공: {f_fields['F9_CallNumber']}")
        else:
            app_instance.log_message("경고: F9 (청구기호)를 090 필드에서 찾았으나 내용이 비어있습니다.", level="WARNING")
    else:
        app_instance.log_message("경고: 090 (청구기호) 필드를 찾을 수 없습니다.", level="WARNING")
        
    # --- F10 별치기호 판정 로직 추가 ---
    call_number_for_f10 = f_fields["F9_CallNumber"]
    if call_number_for_f10 != "(청구기호 추출 실패)":
        f_fields["F10_SpecialCallNumber"] = determine_special_call_number(call_number_for_f10)
        app_instance.log_message(f"정보: F10 (별치기호) 판정 완료: {f_fields['F10_SpecialCallNumber']}")
    else:
        f_fields["F10_SpecialCallNumber"] = "DDC 추출 오류"
        app_instance.log_message("정보: F9 청구기호가 없어 F10 판정을 건너뜁니다.")

    # --- 11. F11: 082 필드에서 DDC 번호 추출 (▼a 서브필드) ---
    if '082' in reconstructed_marc_fields:
        for content in reconstructed_marc_fields['082']:
            # 082 필드의 ▼a 서브필드에서 DDC 번호 추출
            ddc_match = re.search(r'▼a([0-9.]+)', content)
            if ddc_match:
                f_fields["F11_DDC"] = ddc_match.group(1)
                app_instance.log_message(f"정보: F11 (DDC 번호) 추출 성공: {f_fields['F11_DDC']}")
                break
        else:
            f_fields["F11_DDC"] = ""
            app_instance.log_message("경고: F11 (DDC 번호)을 082 필드에서 찾을 수 없습니다.", level="WARNING")
    else:
        f_fields["F11_DDC"] = ""
        app_instance.log_message("정보: 082 (DDC) 필드를 찾을 수 없습니다.")

    return f_fields

# marc_parser.py 파일 하단에 추가

def determine_special_call_number(ddc_str):
    """ DDC 분류기호 문자열을 받아 별치기호를 판정합니다. """
    try:
        # DDC 값에서 첫 숫자 부분만 추출 (예: "823.92R353m" -> 823.92)
        ddc_match = re.match(r'^(\d+(\.\d+)?)', ddc_str)
        if not ddc_match:
            return "DDC 추출 오류"
        
        ddc_value = float(ddc_match.group(1))
    except (ValueError, TypeError):
        return "DDC 추출 오류"

    # 제공된 로직을 그대로 Python 코드로 변환
    if 174.2 <= ddc_value < 174.3: return "SDM, SWM 등"
    if 174.3 <= ddc_value < 174.4: return "BDM, BWM 등"
    if 306.44 <= ddc_value < 306.45: return "LDM, LWM 등"
    if 372.3 <= ddc_value < 372.4: return "SDM, SWM 등"
    if 372.4 <= ddc_value < 372.5: return "LDM, LWM 등"
    if 372.5 <= ddc_value < 372.6: return "ADM, AWM 등"
    if 372.6 <= ddc_value < 372.7: return "LDM, LWM 등"
    if 372.7 <= ddc_value < 372.8: return "SDM, SWM 등"
    if 372.86 <= ddc_value < 372.87: return "ADM, AWM 등"
    
    # 375 (교육과정) 세분화
    if 375.3 <= ddc_value < 375.4: return "HDM, HWM 등" # 사회과학
    if 375.4 <= ddc_value < 375.5: return "LDM, LWM 등" # 언어
    if 375.5 <= ddc_value < 375.6: return "SDM, SWM 등" # 과학
    if 375.6 <= ddc_value < 375.7: return "SDM, SWM 등" # 기술
    if 375.7 <= ddc_value < 375.8: return "ADM, AWM 등" # 예술
    if 375.8 <= ddc_value < 375.9: return "LDM, LWM 등" # 문학
    if 375.9 <= ddc_value < 376: return "HDM, HWM 등" # 지리 및 역사
    
    if 612.044 <= ddc_value < 612.045: return "ADM, AWM 등"
    if 613.7 <= ddc_value < 613.8: return "ADM, AWM 등"
    if 617.1027 <= ddc_value < 617.1028: return "ADM, AWM 등"
    if 741.672 <= ddc_value < 741.673: return "SDM, SWM 등"
    if 746.92 <= ddc_value < 746.93: return "SDM, SWM 등"
    if 3 <= ddc_value < 7: return "SDM, SWM 등" # 3-4, 4-5, 5-6, 6-7 통합
    if 310 <= ddc_value < 314: return "SDM, SWM 등"
    if 340 <= ddc_value < 350: return "BDM, BWM 등"
    if 364 <= ddc_value < 366: return "BDM, BWM 등"
    if 389 <= ddc_value < 390: return "SDM, SWM 등"
    if 658.5 <= ddc_value < 658.578: return "SDM, SWM 등"
    if 657 <= ddc_value < 658: return "HDM, HWM 등"
    if 650 <= ddc_value < 660: return "HDM, HWM 등"
    if 668.9 <= ddc_value < 669: return "SDM, SWM 등"
    if 668.5 <= ddc_value < 668.6: return "SDM, SWM 등"
    if 668 <= ddc_value < 669: return "SDM, SWM 등"
    if 660 <= ddc_value < 661: return "SDM, SWM 등"
    if 690 <= ddc_value < 691: return "SDM, SWM 등"
    if 710 <= ddc_value < 730: return "SDM, SWM 등"
    if 0 <= ddc_value < 400: return "HDM, HWM 등"
    if 400 <= ddc_value < 500: return "LDM, LWM 등"
    if 500 <= ddc_value < 700: return "SDM, SWM 등"
    if 700 <= ddc_value < 800: return "ADM, AWM 등"
    if 800 <= ddc_value < 900: return "LDM, LWM 등"
    if 900 <= ddc_value < 1000: return "HDM, HWM 등"
    
    return ""

