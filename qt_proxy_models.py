# 파일명: qt_proxy_models.py
# 설명: QSortFilterProxyModel을 상속받아 정렬 기능을 확장하는 클래스 모음

import re
from enum import Enum, auto
from PySide6.QtCore import QSortFilterProxyModel, Qt


# 헬퍼 함수 정의 (SearchResultModel 클래스 외부에 추가)
def natural_sort_key(s):
    """자연 정렬을 위한 키 생성 (숫자 부분을 정수로 변환)"""
    if not isinstance(s, str):
        s = str(s)
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r"([0-9]+)", s)
    ]


# ✅ [추가] 정렬 유형을 명확하게 정의하는 Enum 클래스
class SortType(Enum):
    TEXT = auto()
    NUMERIC = auto()
    NATURAL = auto()


class SmartNaturalSortProxyModel(QSortFilterProxyModel):
    """
    [업그레이드] 숫자, 자연정렬, 텍스트를 자동 감지하는 스마트 정렬 프록시 모델
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._column_analysis_cache = {}
        self._sort_key_cache = {}
        self._sort_column = -1
        self._sort_order = Qt.AscendingOrder
        self._sort_type = SortType.TEXT  # ✅ 현재 정렬 유형 저장
        # ✅ [추가] 컬럼별 필터 텍스트를 저장할 딕셔너리
        self.column_filters = {}

    def sort(self, column, order):
        """정렬 시작 전, 컬럼 유형을 분석하고 정렬 키 캐시를 생성합니다."""
        self._sort_column = column
        self._sort_order = order
        # ✅ 컬럼 유형 분석 결과를 self._sort_type에 저장
        self._sort_type = self._analyze_column_sort_type(column)

        self._build_sort_key_cache()
        super().sort(column, order)

    def _build_sort_key_cache(self):
        """분석된 정렬 유형에 따라 최적화된 정렬 키를 미리 계산하여 캐시에 저장합니다."""
        self._sort_key_cache.clear()
        source_model = self.sourceModel()
        if not source_model or self._sort_column < 0:
            return

        for row in range(source_model.rowCount()):
            index = source_model.index(row, self._sort_column)
            data = str(source_model.data(index, Qt.DisplayRole) or "")

            # ✅ [핵심 수정] 분석된 정렬 유형에 따라 다른 키를 생성
            if self._sort_type == SortType.NUMERIC:
                try:
                    # 숫자(소수점 포함)로 변환, 실패 시 0으로 처리
                    self._sort_key_cache[row] = float(data)
                except (ValueError, TypeError):
                    self._sort_key_cache[row] = 0
            elif self._sort_type == SortType.NATURAL:
                self._sort_key_cache[row] = natural_sort_key(data)
            else:  # SortType.TEXT
                self._sort_key_cache[row] = data.lower()

    def lessThan(self, left_index, right_index):
        """미리 캐싱된 정렬 키를 사용하여 매우 빠르게 비교합니다."""
        left_row, right_row = left_index.row(), right_index.row()
        left_key = self._sort_key_cache.get(left_row)
        right_key = self._sort_key_cache.get(right_row)

        if left_key is None or right_key is None:
            return False

        return left_key < right_key

    def _analyze_column_sort_type(self, column):
        """컬럼 데이터 유형을 분석하여 최적의 정렬 방식(TEXT, NUMERIC, NATURAL)을 결정합니다."""
        if column in self._column_analysis_cache:
            return self._column_analysis_cache[column]

        source_model = self.sourceModel()
        if not source_model or source_model.rowCount() == 0:
            self._column_analysis_cache[column] = SortType.TEXT
            return SortType.TEXT

        sample_size = min(100, source_model.rowCount())
        has_numbers, has_letters = False, False
        all_numeric = True  # 모두 숫자라고 가정하고 시작

        for row in range(sample_size):
            data = str(
                source_model.data(source_model.index(row, column), Qt.DisplayRole) or ""
            ).strip()
            if not data:
                continue

            # ✅ [핵심 로직] 현재 값이 숫자인지 확인. 아니라면 all_numeric 플래그를 False로 설정
            if all_numeric:
                try:
                    float(data)
                except (ValueError, TypeError):
                    all_numeric = False

            if not has_numbers and any(c.isdigit() for c in data):
                has_numbers = True
            if not has_letters and any(c.isalpha() for c in data):
                has_letters = True

        # --- 정렬 유형 결정 ---
        if all_numeric and has_numbers:
            result_type = SortType.NUMERIC
        elif has_numbers and has_letters:
            result_type = SortType.NATURAL
        else:
            result_type = SortType.TEXT

        self._column_analysis_cache[column] = result_type

        # --- 디버깅을 위한 로그 출력 ---
        # column_name = str(
        #     source_model.headerData(column, Qt.Horizontal, Qt.DisplayRole)
        #    or f"컬럼{column}"
        # )
        # print(f"📊 컬럼 '{column_name}' 분석 결과 → 정렬 방식: {result_type.name}")
        return result_type

    def invalidate(self):
        """모든 캐시(정렬 키, 컬럼 분석)를 무효화합니다."""
        self._column_analysis_cache.clear()
        self._sort_key_cache.clear()
        self._sort_column = -1
        self._sort_type = SortType.TEXT

    def pre_analyze_all_columns(self):
        """모든 컬럼을 미리 분석하여 정렬 캐시를 준비합니다."""
        source_model = self.sourceModel()
        if not source_model:
            return
        self.invalidate()
        for col in range(source_model.columnCount()):
            self._analyze_column_sort_type(col)  # 이 함수는 결과를 캐시에 저장함
