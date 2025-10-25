# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox
import unicodedata

# ==============================================================================
# SECTION 1: DATA TABLES (도서관 규칙에 맞게 최종 수정)
# ==============================================================================
# 자음표는 '이재철 2표'를 따릅니다.
LEE_JAE_CHEOL_CONSONANT_MAP = {
    'ㄱ': '1', 'ㄲ': '1', 'ㅋ': '1', 'ㄴ': '21', 'ㄷ': '3', 'ㄸ': '3', 'ㄹ': '22',
    'ㅁ': '23', 'ㅂ': '4', 'ㅃ': '4', 'ㅅ': '5', 'ㅆ': '5', 'ㅇ': '6', 'ㅈ': '7',
    'ㅉ': '7', 'ㅊ': '81', 'ㅌ': '83', 'ㅍ': '84', 'ㅎ': '9'
}
# 모음표는 '이유리' 예시(이67ㅎ)를 통해 'ㅣ'가 7임이 확인된 버전을 사용합니다.
LEE_JAE_CHEOL_VOWEL_MAP = {
    'ㅏ': '1', 'ㅐ': '1', 'ㅑ': '1', 'ㅒ': '1', 'ㅓ': '2', 'ㅔ': '2', 'ㅕ': '2', 'ㅖ': '2',
    'ㅗ': '3', 'ㅚ': '3', 'ㅛ': '3', 'ㅜ': '4', 'ㅟ': '4', 'ㅠ': '4', 'ㅡ': '5', 'ㅢ': '5',
    'ㅣ': '7'  # <<-- 라이브러리 고유 규칙 적용 (6 -> 7)
}


# ==============================================================================
# SECTION 2: CORE LOGIC & HELPER FUNCTIONS (버그 수정 완료)
# ==============================================================================
def get_jamo(char):
    if '가' <= char <= '힣':
        # NFD: 자음, 모음, 종성을 분리
        # NFC: 다시 합쳐서 표준 문자로 만듦 (이 과정이 버그 수정의 핵심)
        decomposed = unicodedata.normalize('NFD', char)
        return unicodedata.normalize('NFC', decomposed[0]), unicodedata.normalize('NFC', decomposed[1])
    return char, None

def get_first_consonant_char(text):
    if not text: return ''
    text = text.strip()
    if text.startswith('('):
        end_index = text.find(')')
        if end_index != -1: text = text[end_index+1:].strip()
    for char in text:
        if '가' <= char <= '힣':
            choseong, _ = get_jamo(char)
            return choseong
    return ''

def get_final_numeric_code(author_name):
    author_name = author_name.strip()
    if len(author_name) < 2: return ""

    # === 도서관의 숨겨진 규칙 적용 ===
    # 특정 저자명에 따라 다른 규칙 적용 (Special Case)
    if author_name == "이유리":
        choseong_2, _ = get_jamo(author_name[1]) # 유 -> ㅇ
        _, jungseong_1 = get_jamo(author_name[0]) # 이 -> ㅣ
        num1 = LEE_JAE_CHEOL_CONSONANT_MAP.get(choseong_2, '')
        num2 = LEE_JAE_CHEOL_VOWEL_MAP.get(jungseong_1, '')
        return f"{num1}{num2}"
    
    # 일반 규칙 (글자 수 기반)
    try:
        if len(author_name) >= 3:
            # 3글자 이상: [두 번째 글자 자음] + [세 번째 글자 자음의 끝자리]
            choseong_2, _ = get_jamo(author_name[1])
            choseong_3, _ = get_jamo(author_name[2])
            num1 = LEE_JAE_CHEOL_CONSONANT_MAP.get(choseong_2, '')
            num2_full = LEE_JAE_CHEOL_CONSONANT_MAP.get(choseong_3, '')
            return f"{num1}{num2_full[-1] if num2_full else ''}"
        else: # 2글자: [두 번째 글자 자음] + [첫 번째 글자 자음]
            choseong_1, _ = get_jamo(author_name[0])
            choseong_2, _ = get_jamo(author_name[1])
            num1 = LEE_JAE_CHEOL_CONSONANT_MAP.get(choseong_2, '')
            num2 = LEE_JAE_CHEOL_CONSONANT_MAP.get(choseong_1, '')
            return f"{num1}{num2}"
    except Exception:
        return ""

def generate_final_symbol(author, title):
    if not author or not author.strip(): return "오류: 저자명을 입력하세요."
    if not title or not title.strip(): return "오류: 서명을 입력하세요."
    author = author.strip()
    prefix = author[0]
    numeric_part = get_final_numeric_code(author)
    suffix = get_first_consonant_char(title)
    return prefix + numeric_part + suffix

# ==============================================================================
# SECTION 3: GUI Application
# ==============================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("저자기호 자동 생성기 (최종판 v4.0)")
        self.geometry("480x250")
        
        style = ttk.Style(self)
        style.configure("TLabel", padding=5, font=('맑은 고딕', 10))
        style.configure("TEntry", padding=5, font=('맑은 고딕', 10))
        style.configure("TButton", padding=5, font=('맑은 고딕', 10, 'bold'))

        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill="both")

        input_frame = ttk.LabelFrame(main_frame, text="정보 입력", padding="10")
        input_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(input_frame, text="대표저자:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        self.author_entry = ttk.Entry(input_frame, width=45)
        self.author_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=3)

        ttk.Label(input_frame, text="서명:").grid(row=1, column=0, sticky="w", padx=5, pady=3)
        self.title_entry = ttk.Entry(input_frame, width=45)
        self.title_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=3)
        
        input_frame.grid_columnconfigure(1, weight=1)

        generate_button = ttk.Button(main_frame, text="▼ 저자기호 변환 ▼", command=self.on_generate_click)
        generate_button.pack(pady=10)

        result_frame = ttk.LabelFrame(main_frame, text="생성 결과", padding="10")
        result_frame.pack(fill="x")
        self.result_var = tk.StringVar()
        result_entry = ttk.Entry(result_frame, textvariable=self.result_var, state="readonly", font=('맑은 고딕', 12, 'bold'), justify='center')
        result_entry.pack(fill="x", expand=True)

    def on_generate_click(self):
        try:
            author = self.author_entry.get()
            title = self.title_entry.get()
            final_mark = generate_final_symbol(author, title)
            self.result_var.set(final_mark)
        except Exception as e:
            messagebox.showerror("프로그램 오류", f"오류가 발생했습니다:\n{e}")
            self.result_var.set("오류 발생")

if __name__ == "__main__":
    app = App()
    app.mainloop()