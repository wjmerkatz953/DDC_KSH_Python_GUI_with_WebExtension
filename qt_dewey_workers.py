"""
파일명: dewey_workers.py
설명: Dewey 탭의 백그라운드 작업을 담당하는 QThread 클래스들
버전: v1.0.0
"""

from PySide6.QtCore import QThread, Signal, QObject
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import cast

from Search_Dewey import (
    search_dewey_hierarchy,
    dewey_get_safe,
    dewey_pick_label,
    normalize_ddc_code,
    get_parent_code,
    search_ksh_for_dewey_tab,
)


class DeweySearchThread(QThread):
    """DDC 계층 검색을 위한 QThread 워커"""

    search_finished = Signal(object)
    search_failed = Signal(str)

    def __init__(self, ddc_code: str, dewey_client, ui_owner: QObject):
        super().__init__(ui_owner)
        self.ddc_code = ddc_code
        self.dewey_client = dewey_client
        self._is_cancelled = False

    def cancel(self):
        """스레드 취소 플래그 설정"""
        self._is_cancelled = True

    def run(self):
        """DDC 검색 실행"""
        try:
            result = search_dewey_hierarchy(
                self.dewey_client,
                self.ddc_code,
                is_cancelled_callback=lambda: self._is_cancelled,
            )
            if self._is_cancelled or result is None:
                return

            self.search_finished.emit(result)

        except Exception as e:
            if not self._is_cancelled:
                self.search_failed.emit(str(e))


class DeweyRangeSearchThread(QThread):
    """DDC 범위 검색을 위한 QThread 워커"""

    search_finished = Signal(dict)
    search_failed = Signal(str)

    def __init__(self, ddc_code, dewey_client, parent=None):
        super().__init__(parent)
        self.base_code = ddc_code
        self.dewey_client = dewey_client
        owner = cast("QtDeweySearchTab", parent)
        self.app_instance = owner.app_instance
        self._is_cancelled = False

    def cancel(self):
        """스레드 취소 플래그 설정"""
        self._is_cancelled = True

    def run(self):
        try:
            if self._is_cancelled:
                return

            main_ctx = self.dewey_client.get_dewey_context(self.base_code)

            if self._is_cancelled:
                return

            main_code = normalize_ddc_code(
                dewey_get_safe(main_ctx.get("main", {}), "notation")
            )
            main_label = dewey_pick_label(main_ctx.get("main", {}).get("prefLabel"))
            range_results = {main_code: main_label or "Label not found"}

            parent_code = get_parent_code(main_code)
            if parent_code and not self._is_cancelled:
                try:
                    parent_ctx = self.dewey_client.get_dewey_context(parent_code)
                    range_results[parent_code] = dewey_pick_label(
                        parent_ctx.get("main", {}).get("prefLabel")
                    )
                except:
                    pass

            if (
                len(self.base_code) == 3
                and self.base_code.isdigit()
                and not self._is_cancelled
            ):
                ten_base = self.base_code[:2]  # ✅ 문자열 그대로 유지 (예: "02")
                sibling_codes = [
                    f"{ten_base}{i}"
                    for i in range(10)
                    if f"{ten_base}{i}" != self.base_code
                ]

                def fetch_single_sibling(sibling_code):
                    if self._is_cancelled:
                        return None, None
                    try:
                        sibling_ctx = self.dewey_client.get_dewey_context(sibling_code)
                        if sibling_ctx.get("main"):
                            label = dewey_pick_label(
                                sibling_ctx["main"].get("prefLabel")
                            )
                            if label:
                                return sibling_code, label
                    except:
                        pass
                    return None, None

                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [
                        executor.submit(fetch_single_sibling, code)
                        for code in sibling_codes
                    ]
                    for future in futures:
                        if self._is_cancelled:
                            executor.shutdown(wait=False, cancel_futures=True)
                            return
                        try:
                            code, label = future.result(timeout=3)
                            if code and label:
                                range_results[code] = label
                        except:
                            continue

            for i in range(1, 10):
                if self._is_cancelled:
                    return
                sub_code = f"{self.base_code}.{i}"
                try:
                    sub_ctx = self.dewey_client.get_dewey_context(sub_code)
                    if sub_ctx.get("main"):
                        range_results[sub_code] = dewey_pick_label(
                            sub_ctx["main"].get("prefLabel")
                        )
                    else:
                        range_results[sub_code] = "(내용 없음)"
                except ValueError as ve:
                    parent_instance = self.parent()
                    if "DLD URL을 찾지 못했습니다" in str(ve):
                        range_results[sub_code] = "(WebDewey에 없음)"
                        if parent_instance and hasattr(parent_instance, "app_instance"):
                            parent_instance.app_instance.log_message(
                                f"정보: DDC {sub_code}는 WebDewey에 없는 번호입니다.",
                                "INFO",
                            )
                    else:
                        range_results[sub_code] = "(값 오류)"
                        if parent_instance and hasattr(parent_instance, "app_instance"):
                            parent_instance.app_instance.log_message(
                                f"DDC {sub_code} 처리 중 값 오류 발생: {ve}", "ERROR"
                            )
                except Exception as e:
                    range_results[sub_code] = "(조회 실패)"
                    if self.app_instance:
                        self.app_instance.log_message(
                            f"DDC {sub_code} API 조회 실패: {e}", "ERROR"
                        )

            for item in main_ctx.get("narrower", []):
                if self._is_cancelled:
                    return
                narrow_code = normalize_ddc_code(dewey_get_safe(item, "notation"))
                if narrow_code and narrow_code.startswith(self.base_code):
                    range_results[narrow_code] = dewey_pick_label(item.get("prefLabel"))

            if self._is_cancelled:
                return

            self.search_finished.emit(
                {
                    "main_code": main_code,
                    "main_label": main_label,
                    "range_results": range_results,
                    "main_ctx": main_ctx,
                }
            )
        except Exception as e:
            if not self._is_cancelled:
                self.search_failed.emit(str(e))  # noqa


class DeweyHundredsSearchThread(QThread):
    """DDC 백의 자리 검색을 위한 QThread 워커"""

    search_finished = Signal(dict)
    search_failed = Signal(str)

    def __init__(self, ddc_code, dewey_client, parent: QObject | None = None):
        super().__init__(parent)
        self.base_code = ddc_code
        self.dewey_client = dewey_client
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            if self._is_cancelled:
                return

            main_ctx = self.dewey_client.get_dewey_context(self.base_code)

            if self._is_cancelled:
                return

            main_code = normalize_ddc_code(
                dewey_get_safe(main_ctx.get("main", {}), "notation")
            )
            main_label = dewey_pick_label(main_ctx.get("main", {}).get("prefLabel"))

            detailed_range = {main_code: main_label or "Label not found"}

            def fetch_detailed(i):
                if self._is_cancelled:
                    return None, None
                sub_code = f"{self.base_code[0]}0{i}"
                try:
                    sub_ctx = self.dewey_client.get_dewey_context(sub_code)
                    if sub_ctx.get("main"):
                        label = dewey_pick_label(sub_ctx["main"].get("prefLabel"))
                        return sub_code, label
                except:
                    pass
                return None, None

            def fetch_major(tens):
                if self._is_cancelled:
                    return None, None
                major_code = f"{self.base_code[0]}{tens}0"
                try:
                    major_ctx = self.dewey_client.get_dewey_context(major_code)
                    if major_ctx.get("main"):
                        label = dewey_pick_label(major_ctx["main"].get("prefLabel"))
                        return major_code, label
                except:
                    pass
                return None, None

            if not self._is_cancelled:
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(fetch_detailed, i) for i in range(1, 10)]
                    for future in as_completed(futures):
                        if self._is_cancelled:
                            executor.shutdown(wait=False, cancel_futures=True)
                            return
                        code, label = future.result()
                        if code and label:
                            detailed_range[code] = label

            major_divisions = {}
            if not self._is_cancelled:
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [
                        executor.submit(fetch_major, tens) for tens in range(1, 10)
                    ]
                    for future in as_completed(futures):
                        if self._is_cancelled:
                            executor.shutdown(wait=False, cancel_futures=True)
                            return
                        code, label = future.result()
                        if code and label:
                            major_divisions[code] = label

            special_ranges = {}
            if not self._is_cancelled:
                for item in main_ctx.get("narrower", []):
                    notation = dewey_get_safe(item, "notation")
                    if notation and "-" in notation:
                        label = dewey_pick_label(item.get("prefLabel"))
                        if label:
                            special_ranges[notation] = label

            if self._is_cancelled:
                return

            self.search_finished.emit(
                {
                    "main_code": main_code,
                    "main_label": main_label,
                    "detailed_range": detailed_range,
                    "major_divisions": major_divisions,
                    "special_ranges": special_ranges,
                    "main_ctx": main_ctx,
                }
            )
        except Exception as e:
            if not self._is_cancelled:
                self.search_failed.emit(str(e))


class DeweyKshSearchThread(QThread):
    """Dewey 탭의 KSH 검색을 위한 QThread 워커"""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, app_instance, search_term, parent=None):
        super().__init__(parent)
        self.app_instance = app_instance
        self.search_term = search_term
        self._is_cancelled = False

    def run(self):
        """백그라운드 KSH 검색 실행"""
        try:
            from search_query_manager import SearchQueryManager

            sqm = SearchQueryManager(self.app_instance.db_manager)

            combined_df = search_ksh_for_dewey_tab(
                sqm,
                self.search_term,
                is_cancelled_callback=lambda: self._is_cancelled,
            )

            if self._is_cancelled:
                return

            self.finished.emit(combined_df)

        except Exception as e:
            import traceback

            self.error.emit(f"{str(e)}\n{traceback.format_exc()}")

    def cancel(self):
        self._is_cancelled = True
