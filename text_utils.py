# text_utils.py
# -*- coding: utf-8 -*-
"""
text_utils.py - 텍스트 처리 및 외부 서비스 연동 유틸리티
Version: v1.0.0
생성일: 2025-09-06

기능:
- 웹 사전/번역 서비스 연동
- 텍스트 정리 및 포맷팅
- URL 인코딩 헬퍼
"""
import threading
import webbrowser
import urllib.parse
import pandas as pd
import re
import html


def open_naver_dictionary(text, app_instance):
    """네이버 영어사전에서 텍스트를 검색합니다."""
    try:
        # 텍스트 정리 및 URL 인코딩
        clean_text = text.strip()
        encoded_text = urllib.parse.quote(clean_text)

        # 네이버 영어사전 URL 구성
        url = f"https://en.dict.naver.com/#/search?query={encoded_text}&range=all"

        # -------------------
        # 🔥 핵심 해결: webbrowser.open을 별도 스레드에서 실행
        def _open_browser():
            try:
                webbrowser.open(url, new=2)
            except Exception as browser_error:
                app_instance.log_message(
                    f"오류: 브라우저 열기 실패: {browser_error}", level="ERROR"
                )

        # 데몬 스레드로 실행하여 메인 스레드 블로킹 방지
        browser_thread = threading.Thread(target=_open_browser, daemon=True)
        browser_thread.start()
        # -------------------

        app_instance.log_message(
            f"정보: 네이버 사전 검색 - '{clean_text}' -> {url}", level="INFO"
        )

    except Exception as e:
        app_instance.log_message(f"오류: 네이버 사전 검색 실패: {e}", level="ERROR")


def open_google_translate(text, app_instance, source_lang="en", target_lang="ko"):
    """Google 번역으로 텍스트를 번역합니다."""
    try:
        # URL 인코딩
        encoded_text = urllib.parse.quote(text)

        url = f"https://translate.google.com/?hl=ko&sl={source_lang}&tl={target_lang}&text={encoded_text}&op=translate"

        # -------------------
        # 🔥 핵심 해결: webbrowser.open을 별도 스레드에서 실행
        def _open_browser():
            try:
                webbrowser.open(url, new=2)
            except Exception as browser_error:
                app_instance.log_message(
                    f"오류: 브라우저 열기 실패: {browser_error}", level="ERROR"
                )

        browser_thread = threading.Thread(target=_open_browser, daemon=True)
        browser_thread.start()
        # -------------------

        direction = f"{source_lang.upper()}→{target_lang.upper()}"
        app_instance.log_message(
            f"정보: Google 번역 열기 ({direction}) - '{text}' -> {url}", level="INFO"
        )

    except Exception as e:
        app_instance.log_message(f"오류: 번역 열기 실패: {e}", level="ERROR")


def open_dictionary(text, app_instance):
    """롱맨 영영사전에서 단어를 찾습니다."""
    try:
        # 텍스트 정리 (특수문자 제거, 공백을 하이픈으로)
        clean_text = clean_text_for_url(text)

        url = f"https://www.ldoceonline.com/dictionary/{clean_text}"

        # -------------------
        # 🔥 핵심 해결: webbrowser.open을 별도 스레드에서 실행
        def _open_browser():
            try:
                webbrowser.open(url, new=2)
            except Exception as browser_error:
                app_instance.log_message(
                    f"오류: 브라우저 열기 실패: {browser_error}", level="ERROR"
                )

        browser_thread = threading.Thread(target=_open_browser, daemon=True)
        browser_thread.start()
        # -------------------

        app_instance.log_message(
            f"정보: 영영사전 열기 - '{text}' -> {url}", level="INFO"
        )

    except Exception as e:
        app_instance.log_message(f"오류: 사전 열기 실패: {e}", level="ERROR")


def clean_text_for_url(text):
    """URL에 사용할 수 있도록 텍스트를 정리합니다."""
    clean_text = text.strip().lower()
    clean_text = "".join(c for c in clean_text if c.isalnum() or c.isspace())
    clean_text = clean_text.replace(" ", "-")
    return clean_text


def format_text_preview(text, max_length=20):
    """텍스트를 미리보기용으로 포맷팅합니다."""
    if not text:
        return ""
    text_str = str(text).strip()
    if len(text_str) <= max_length:
        return text_str
    return text_str[:max_length] + "..."


def clean_ksh_search_input(search_input):
    """
    KSH 검색어 입력을 정리하여 가장 핵심적인 주제어만 추출합니다.
    (v1.2.0: 특수문자 기반 검색어 분할 기능 추가)
    """
    if not search_input or pd.isna(search_input):
        return ""

    text = str(search_input).strip()

    # 🆕 1단계: 특수문자 기반 검색어 전처리 (▼a건강관리▼a러닝▼a조깅▼a운동법▲ 패턴)
    if "▼a" in text and any(c in text for c in "▼▲"):
        # ▼a...▼a... 패턴에서 키워드들을 추출하여 쉼표로 연결
        keywords = []
        # ▼a로 시작하는 모든 키워드를 찾아 추출
        pattern = r"▼a([^▼▲]+)"
        matches = re.findall(pattern, text)

        for match in matches:
            # 각 키워드에서 불필요한 기호와 공백 정리
            # 🎯 개선: 한글+한자/괄호 제거 후 CJK 내부 공백 제거
            # -------------------
            cleaned_keyword = re.sub(r"[▼▲]", "", match)
            cleaned_keyword = re.sub(r"\[.*?\]|\(.*?\)", "", cleaned_keyword).strip()
            # CJK(한글/한자)가 하나라도 있으면 내부 공백을 모두 제거 → '자기 계발' -> '자기계발'
            if re.search(r"[\uAC00-\uD7AF\u4E00-\u9FFF]", cleaned_keyword):
                cleaned_keyword = re.sub(r"\s+", "", cleaned_keyword)
            else:
                # 비-CJK는 다중 공백만 정규화
                cleaned_keyword = re.sub(r"\s{2,}", " ", cleaned_keyword)
            # -------------------

            if cleaned_keyword:
                keywords.append(cleaned_keyword)

        if keywords:
            return ", ".join(keywords)

    # 2단계: 기존 KSH 형식 특수문자 처리 로직 (기존과 동일)
    if any(c in text for c in "▼▲[]"):
        # KSH 형식 문자열일 경우: 모든 서식과 공백을 적극적으로 제거
        if ";" in text:
            text = text.split(";")[0].strip()
        if ":" in text:
            text = text.split(":")[0].strip()

        text = re.sub(r"▼0[^▲]*▲", "", text).strip()
        text = re.sub(r"▼a", "", text).strip()
        # -------------------
        text = re.sub(r"\[.*?\]|\(.*?\)", "", text).strip()  # 대괄호/소괄호 내용 제거
        text = re.sub(r"[▼▲\[\]]", "", text).strip()
        # CJK가 포함되면 내부 공백 제거 (예: '자기 계발' -> '자기계발')
        if re.search(r"[\uAC00-\uD7AF\u4E00-\u9FFF]", text):
            text = re.sub(r"\s+", "", text)
        else:
            text = re.sub(r"\s{2,}", " ", text)
        # -------------------
        return text
    else:
        # 순수 키워드일 경우: 양 끝 공백만 제거하여 원본 유지
        return text.strip()
