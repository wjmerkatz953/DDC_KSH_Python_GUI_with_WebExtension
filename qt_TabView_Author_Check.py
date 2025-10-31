# -*- coding: utf-8 -*-
# 파일명: qt_TabView_Author_Check.py
# 설명: 저자 확인 탭 (BaseSearchTab 상속)
# 버전: 1.0.0
# 생성일: 2025-10-31

from PySide6.QtWidgets import QCheckBox
from PySide6.QtCore import Qt
from qt_base_tab import BaseSearchTab
from qt_utils import SelectAllLineEdit


class QtAuthorCheckTab(BaseSearchTab):
    """
    저자 확인 탭

    BaseSearchTab을 상속받아 nlk_biblio.sqlite 검색 기능을 제공합니다.
    제목, 저자, KAC 코드, 연도 검색을 지원하며 복수 제목 일괄 검색이 가능합니다.
    """

    def __init__(self, config, app_instance):
        """
        저자 확인 탭 초기화

        Args:
            config (dict): qt_Tab_configs.py의 AUTHOR_CHECK_SEARCH 설정
            app_instance: 메인 앱 인스턴스
        """
        # 부모 클래스 초기화 (모든 기본 UI와 기능은 여기서 자동 생성됨)
        super().__init__(config, app_instance)

    def _create_extra_inputs(self):
        """
        ✅ [오버라이드] 저자 확인 탭 전용 추가 입력 필드 생성

        BaseSearchTab의 기본 입력 필드(제목, 저자, ISBN, Year) 외에
        KAC 코드 검색 필드를 추가합니다.

        추가되는 필드:
        - KAC 코드: KAC 코드 검색
        """
        # KAC 코드 체크박스 생성
        self.kac_check = QCheckBox("KAC:")
        self.kac_check.setChecked(True)

        # KAC 코드 입력창 생성
        self.kac_input = SelectAllLineEdit()
        self.kac_input.setPlaceholderText("e.g. nlk:KAC200702805")

        # 레이아웃에 추가 (행=0, 컬럼=8,9)
        self.input_layout.addWidget(self.kac_check, 0, 8)
        self.input_layout.addWidget(self.kac_input, 0, 9)

        # KAC 입력창도 Enter 키로 검색 시작 가능하도록 연결
        self.kac_input.returnPressed.connect(self.start_search)

        # ✅ 컬럼 stretch 조정 (KAC 입력창도 같은 비율로 확장)
        self.input_layout.setColumnStretch(9, 1)

    def _create_extra_buttons(self):
        """
        ✅ [오버라이드] 버튼 위치를 KAC 필드 이후로 조정

        BaseSearchTab에서 생성된 버튼(컬럼 8,9)을 컬럼 10,11로 이동합니다.
        """
        # 기존 버튼들을 레이아웃에서 제거
        self.input_layout.removeWidget(self.search_button)
        self.input_layout.removeWidget(self.stop_button)

        # KAC 필드(8,9) 다음인 컬럼 10,11에 다시 추가
        self.input_layout.addWidget(self.search_button, 0, 10)
        self.input_layout.addWidget(self.stop_button, 0, 11)

    def get_search_params(self):
        """
        ✅ [오버라이드] 저자 확인 검색에 필요한 파라미터를 수집합니다.

        BaseSearchTab의 기본 파라미터(title_query, author_query, isbn_query, year_query)에
        저자 확인 전용 파라미터(kac_query, db_manager)를 추가합니다.

        주의: app_instance는 SearchThread가 자동으로 추가하므로 여기서 추가하지 않음!

        Returns:
            dict: 검색 파라미터 딕셔너리
        """
        # 부모 클래스의 기본 파라미터 가져오기
        params = super().get_search_params()

        if params is None:
            return None

        # ✅ 저자 확인 전용 파라미터 추가
        params.update(
            {
                # KAC 코드 검색어 추가
                "kac_query": (
                    self.kac_input.text().strip()
                    if hasattr(self, "kac_check") and self.kac_check.isChecked()
                    else ""
                ),
                # db_manager만 추가 (app_instance는 SearchThread가 자동 추가!)
                "db_manager": (
                    self.app_instance.db_manager
                    if hasattr(self.app_instance, "db_manager")
                    else None
                ),
            }
        )

        # ✅ ISBN 파라미터 제거 (이 탭에서는 사용 안 함)
        if "isbn_query" in params:
            del params["isbn_query"]

        return params

    def clear_search_inputs(self):
        """
        ✅ [오버라이드] 검색어 입력 위젯들을 초기화합니다.

        MARC 데이터 전송 시 호출됩니다.
        """
        # 부모 클래스의 기본 필드 초기화
        super().clear_search_inputs()

        # 저자 확인 탭 전용 필드 초기화
        if hasattr(self, "kac_input"):
            self.kac_input.clear()
