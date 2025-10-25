# -*- coding: utf-8 -*-
# 파일명: qt_TabView_Example.py
# 설명: BaseSearchTab을 상속받아 LC 검색 탭을 구현한 최종 자식 클래스 예제 (모델/뷰 버전)
# 버전: 3.0.0 - 모델/뷰 아키텍처 전환
# 생성일: 2025-09-25

# --- ✅ [핵심 변경] 모델/뷰 BaseSearchTab import ---
from qt_base_tab import BaseSearchTab  # 모델/뷰 버전 사용

# -----------------------------------------------------------------------------
# 🚀 실제 서버 / Mock 서버 선택 스위치 (기존 방식 유지)
# -----------------------------------------------------------------------------
USE_MOCK_DATA = False

if USE_MOCK_DATA:
    from mock_backend import search_lc_orchestrated_mock as search_lc_orchestrated
else:
    from search_orchestrator import search_lc_orchestrated


class QtLCSearchTab(BaseSearchTab):
    """✅ [수정] 외부에서 설정을 주입받는 범용 검색 탭"""

    def __init__(self, config, app_instance):
        # -------------------
        # [핵심] 내부에서 설정을 정의하지 않고, 외부에서 받은 config를 그대로 부모에게 전달
        super().__init__(config, app_instance)
        # -------------------

        # ✅ [선택사항] LC 탭 전용 추가 기능이 있다면 여기에 구현
        self._setup_lc_specific_features()

    def _setup_lc_specific_features(self):
        """LC 탭만의 특별한 기능 설정 (선택사항)"""
        # 예시: LC 탭에만 보이는 추가 버튼이나 기능
        # 현재는 BaseSearchTab의 모든 기능을 그대로 사용

        # 로그 메시지
        if hasattr(self.app_instance, "log_message"):
            self.app_instance.log_message("✅ LC 검색 탭 (모델/뷰) 초기화 완료", "INFO")

    def on_item_double_clicked(self, row_index):
        """✅ [LC 전용] 항목 더블클릭 시 LC 상세 링크 열기"""
        try:
            # 상세 링크 컬럼 찾기
            link_column_index = -1
            for i, (key, header) in enumerate(self.config["column_map"]):
                if key == "상세 링크":
                    link_column_index = i
                    break

            if link_column_index >= 0:
                # 모델에서 링크 URL 가져오기
                item = self.table_model.item(row_index, link_column_index)
                if item:
                    link_url = item.text()
                    if link_url and link_url.startswith("http"):
                        self.open_link_in_column(link_url)

                        if hasattr(self.app_instance, "log_message"):
                            self.app_instance.log_message(
                                f"🌐 LC 상세 링크 열기: 행 {row_index+1}", "INFO"
                            )
                    else:
                        # 링크가 없으면 기본 세부 정보 대화상자 표시
                        self.show_item_details(row_index)
                else:
                    self.show_item_details(row_index)
            else:
                # 링크 컬럼이 없으면 기본 세부 정보 대화상자 표시
                self.show_item_details(row_index)

        except Exception as e:
            if hasattr(self.app_instance, "log_message"):
                self.app_instance.log_message(f"❌ LC 링크 열기 실패: {e}", "ERROR")
            # 오류 발생 시 기본 동작
            self.show_item_details(row_index)
