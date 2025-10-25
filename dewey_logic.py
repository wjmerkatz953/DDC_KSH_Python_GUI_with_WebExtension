"""
파일명: dewey_logic.py
설명: Dewey 탭의 UI 업데이트, 네비게이션, 검색 로직을 담당
버전: v1.0.0
"""

import re
import webbrowser
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QMenu,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, Slot, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QStandardItem

import qt_api_settings
from ui_constants import UI_CONSTANTS
from Search_Dewey import (
    DeweyClient,
    extract_all_ksh_concept_ids,
    format_ksh_content_for_preview,
    normalize_ddc_code,
    get_parent_code,
    is_table_notation,
    format_ddc_for_display,
    should_lazy_expand,
    preprocess_dewey_description_for_ksh,
    get_ksh_detailed_info,
    dewey_get_safe,
    dewey_pick_label,
)
from dewey_workers import (
    DeweySearchThread,
    DeweyRangeSearchThread,
    DeweyHundredsSearchThread,
    DeweyKshSearchThread,
)
from qt_widget_events import focus_on_first_table_view_item
from view_displays import adjust_qtableview_columns
from qt_copy_feedback import show_copy_feedback
from qt_context_menus import show_cell_detail_dialog
from text_utils import open_dictionary, open_google_translate, open_naver_dictionary


def _as_list(value):
    """Helper to ensure a value is a list."""
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


# ========================================
# 1. 이벤트 핸들러
# ========================================


def _on_interlock_toggled(tab, checked):
    tab.is_interlock_enabled = checked
    if checked:
        tab.dewey_interlock_button.setText("연동검색 ON")
    else:
        tab.dewey_interlock_button.setText("연동검색 OFF")


def _update_detail_view(tab, current, previous, proxy_model, table_model):
    """[수정] 부모 클래스와 동일한 인자를 받도록 시그니처 변경"""
    if not current.isValid():
        if hasattr(tab.app_instance, "main_window"):
            tab.app_instance.main_window.detail_display.clear()
        return

    # ✅ 전달받은 proxy_model과 table_model을 사용하도록 수정
    source_index = proxy_model.mapToSource(current)
    row_data = table_model.get_row_data(source_index.row())
    if not row_data:
        return

    model = table_model
    row = source_index.row()

    from ui_constants import UI_CONSTANTS

    U = UI_CONSTANTS
    import re

    header_style = f"color: {U.ACCENT_GREEN}; font-weight: bold;"
    url_pattern = re.compile(r"(https?://[^\\s<>\"]+|www\\.[^\\s<>\"]+)")

    content_lines = []
    for col in range(model.columnCount()):
        column_name = (
            model.headerData(
                col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
            )
            or ""
        )
        value_content = (
            model.data(model.index(row, col), Qt.ItemDataRole.DisplayRole) or ""
        )
        value_content = str(value_content).replace("\u2029", "")

        is_ksh_content = "▼a" in value_content and "▲" in value_content
        is_url_content = bool(url_pattern.search(str(value_content)))
        styled_header = f'▶ <span style="{header_style}">{column_name}:</span>'

        if is_ksh_content or is_url_content:
            if is_ksh_content:
                value_content = value_content.replace("▲; ▼a", "▲\n▼a").replace(
                    "▲, ▼a", "▲\n▼a"
                )
            formatted_line = f"{styled_header}\n{value_content}"
            content_lines.append(formatted_line)
        else:
            from qt_context_menus import _format_text_for_detail_view

            formatted_value = _format_text_for_detail_view(value_content)
            if "\n" in formatted_value:
                formatted_line = f"{styled_header}\n{formatted_value}"
            else:
                formatted_line = f"{styled_header} {formatted_value}"
            content_lines.append(formatted_line)

    final_text = "\n".join(content_lines)

    if hasattr(tab.app_instance, "main_window"):
        main_window = tab.app_instance.main_window
        if hasattr(main_window, "detail_display"):
            from qt_utils import linkify_text

            main_window.detail_display.setOpenExternalLinks(True)

            lines = final_text.split("\n")
            html_lines = []

            for line in lines:
                temp_line = line.strip()
                if not temp_line:
                    continue

                if '<span style="' in line:
                    linked_line = line
                else:
                    linked_line = linkify_text(line)

                link_style = f'style="color: {U.ACCENT_BLUE}; text-decoration: none;"'
                linked_line = linked_line.replace("<a href=", f"<a {link_style} href=")

                linked_line = (
                    linked_line.replace("\r", "")
                    .replace("\u2029", "")
                    .replace("\xa0", " ")
                    .strip()
                )

                html_lines.append(
                    f'<div style="white-space: pre-wrap; margin: 0; padding: 0; line-height: 1.0; user-select: text; display: block;">{linked_line}</div>'
                )

            final_html = "".join(html_lines)
            main_window.detail_display.setHtml(final_html)


# 2. API 설정 관련


def _show_api_settings(tab):
    qt_api_settings.show_api_settings_modal(
        "Web Dewey",
        tab.app_instance.db_manager,
        tab.app_instance,
        parent_window=tab,
    )


def _update_api_status(tab):
    try:
        is_configured = qt_api_settings.check_api_configured(
            "Web Dewey", tab.app_instance.db_manager
        )
        if is_configured:
            tab.app_instance.log_message("✅ Web Dewey API가 설정되었습니다.", "INFO")
        else:
            tab.app_instance.log_message(
                "⚠️ Web Dewey API가 설정되지 않았습니다. [API 설정] 버튼을 눌러 설정해주세요.",
                "WARNING",
            )
    except Exception as e:
        tab.app_instance.log_message(
            f"❌ Web Dewey API 상태 확인 중 오류 발생: {e}", "ERROR"
        )


# 3. 네비게이션/히스토리 관련


def _init_dewey_navigation(tab):
    tab._dewey_nav_back_stack = []
    tab._dewey_nav_forward_stack = []
    tab._dewey_nav_current = None
    tab._dewey_nav_debounce_timer = None

    QTimer.singleShot(50, tab._update_nav_buttons)


def _update_nav_buttons(tab):
    tab.dewey_nav_back_button.setEnabled(bool(tab._dewey_nav_back_stack))
    tab.dewey_nav_forward_button.setEnabled(bool(tab._dewey_nav_forward_stack))


def _navigate_to_code(tab, raw_code: str, add_to_history: bool):
    code = normalize_ddc_code(re.sub(r"[^0-9.\-–—]", "", str(raw_code)).strip())
    if not code:
        tab.app_instance.log_message("DDC 코드를 입력해주세요.", level="WARNING")
        return

    if add_to_history:
        cur = tab._dewey_nav_current
        if cur and cur != code:
            tab._dewey_nav_back_stack.append(cur)
            tab._dewey_nav_forward_stack.clear()

        tab._add_to_search_history(code)

    tab._dewey_nav_current = code
    tab._update_nav_buttons()

    tab.dewey_ddc_entry.setText(code)

    tab._start_fetch_dewey()


def _nav_go_back(tab):
    if not tab._dewey_nav_back_stack:
        return

    cur = tab._dewey_nav_current
    prev_code = tab._dewey_nav_back_stack.pop()

    if cur:
        tab._dewey_nav_forward_stack.append(cur)

    tab._dewey_nav_current = prev_code
    tab._update_nav_buttons()

    tab.dewey_ddc_entry.setText(prev_code)

    if tab._dewey_nav_debounce_timer:
        tab._dewey_nav_debounce_timer.stop()

    tab._dewey_nav_debounce_timer = QTimer()
    tab._dewey_nav_debounce_timer.setSingleShot(True)
    tab._dewey_nav_debounce_timer.timeout.connect(tab._start_fetch_dewey)
    tab._dewey_nav_debounce_timer.start(2000)


def _nav_go_forward(tab):
    if not tab._dewey_nav_forward_stack:
        return

    cur = tab._dewey_nav_current
    next_code = tab._dewey_nav_forward_stack.pop()

    if cur:
        tab._dewey_nav_back_stack.append(cur)

    tab._dewey_nav_current = next_code
    tab._update_nav_buttons()

    tab.dewey_ddc_entry.setText(next_code)

    if tab._dewey_nav_debounce_timer:
        tab._dewey_nav_debounce_timer.stop()

    tab._dewey_nav_debounce_timer = QTimer()
    tab._dewey_nav_debounce_timer.setSingleShot(True)
    tab._dewey_nav_debounce_timer.timeout.connect(tab._start_fetch_dewey)
    tab._dewey_nav_debounce_timer.start(2000)


def _init_search_history_db(tab):
    import sqlite3

    db_path = "dewey_cache.db"
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ddc_code TEXT NOT NULL,
                searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_search_history_time
            ON search_history(searched_at DESC)
        """
        )
        conn.commit()
        conn.close()
    except Exception as e:
        tab.app_instance.log_message(
            f"검색 히스토리 DB 초기화 실패: {e}", level="ERROR"
        )


def _add_to_search_history(tab, code: str):
    import sqlite3
    from datetime import datetime

    db_path = "dewey_cache.db"
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO search_history (ddc_code, searched_at) VALUES (?, ?)",
            (code, datetime.now()),
        )
        conn.commit()

        cursor.execute(
            """
            DELETE FROM search_history
            WHERE id NOT IN (
                SELECT id FROM search_history
                ORDER BY searched_at DESC
                LIMIT 300
            )
        """
        )
        conn.commit()
        conn.close()

        tab._load_search_history()

    except Exception as e:
        tab.app_instance.log_message(f"검색 히스토리 저장 실패: {e}", level="ERROR")


def _load_search_history(tab):
    import sqlite3

    if not hasattr(tab, "dewey_history_combo"):
        return

    db_path = "dewey_cache.db"
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT ddc_code
            FROM search_history
            ORDER BY searched_at DESC
            LIMIT 20
        """
        )
        rows = cursor.fetchall()
        conn.close()

        tab.dewey_history_combo.blockSignals(True)
        tab.dewey_history_combo.clear()
        tab.dewey_history_combo.addItem("검색 내역")
        for row in rows:
            tab.dewey_history_combo.addItem(row[0])
        tab.dewey_history_combo.setCurrentIndex(0)
        tab.dewey_history_combo.blockSignals(False)

    except Exception as e:
        tab.app_instance.log_message(f"검색 히스토리 로드 실패: {e}", level="ERROR")


def _on_history_selected(tab, index):
    if index <= 0:
        return

    code = tab.dewey_history_combo.itemText(index)
    if code:
        tab._navigate_to_code(code, add_to_history=True)
        tab.dewey_history_combo.setCurrentIndex(0)


# 4. DDC 검색 관련


def _start_fetch_dewey(tab):
    ddc = tab.dewey_ddc_entry.text().strip()
    if not ddc:
        tab.app_instance.log_message("DDC 코드를 입력해주세요.", level="WARNING")
        return

    if tab.dewey_search_thread and tab.dewey_search_thread.isRunning():
        tab.app_instance.log_message("이전 DDC 검색을 취소합니다.", "INFO")
        tab.dewey_search_thread.quit()
        tab.dewey_search_thread.wait()

    normalized_ddc = normalize_ddc_code(ddc)
    if normalized_ddc.isdigit() and len(normalized_ddc) < 3:
        normalized_ddc = normalized_ddc.zfill(3)

    if normalized_ddc != ddc:
        tab.app_instance.log_message(
            f"정보: DDC 코드 정규화 - {ddc} → {normalized_ddc}", level="INFO"
        )
        tab.dewey_ddc_entry.setText(normalized_ddc)
        ddc = normalized_ddc
    else:
        ddc = normalized_ddc

    tab.progress_bar.setVisible(True)
    tab.progress_bar.setRange(0, 100)
    tab.progress_bar.setValue(0)

    tab.dewey_classify_button.setEnabled(False)
    tab.dewey_classify_cancel_button.setEnabled(True)

    client = getattr(tab.app_instance, "dewey_client", None)
    if client is None or not isinstance(client, DeweyClient):
        client = DeweyClient(tab.app_instance.db_manager)
        tab.app_instance.dewey_client = client

    if (
        len(normalized_ddc) == 3
        and normalized_ddc.isdigit()
        and normalized_ddc.endswith("00")
    ):
        tab.dewey_search_thread = DeweyHundredsSearchThread(normalized_ddc, client, tab)
    elif (
        len(normalized_ddc) == 3
        and normalized_ddc.isdigit()
        and normalized_ddc.endswith("0")
    ):
        tab.dewey_search_thread = DeweyRangeSearchThread(normalized_ddc, client, tab)
    else:
        tab.dewey_search_thread = DeweySearchThread(normalized_ddc, client, tab)

    tab.dewey_search_thread.search_finished.connect(tab._on_ddc_search_finished)
    tab.dewey_search_thread.search_failed.connect(tab._on_ddc_search_failed)

    tab.dewey_search_thread.start()


def _cancel_fetch_dewey(tab):
    if tab.dewey_search_thread and tab.dewey_search_thread.isRunning():
        tab.dewey_search_thread.cancel()
        tab.dewey_search_thread.quit()
        tab.dewey_search_thread.wait(2000)
        tab.app_instance.log_message("DDC 검색이 취소되었습니다.", "INFO")
    tab._finalize_fetch_dewey()


def _finalize_fetch_dewey(tab):
    # tab.progress_bar.hide() # 👈 [삭제] 애니메이션 후 숨기지 않도록 변경
    tab.dewey_classify_button.setEnabled(True)
    tab.dewey_classify_cancel_button.setEnabled(False)
    if tab.dewey_search_thread:
        tab.dewey_search_thread = None


@Slot(dict)
def _on_ddc_search_finished(tab, result):
    # 🔥 [핵심 추가] 애니메이션으로 부드럽게 100%로 채우기
    tab.animation = QPropertyAnimation(tab.progress_bar, b"value")
    tab.animation.setDuration(800)
    tab.animation.setStartValue(tab.progress_bar.value())
    tab.animation.setEndValue(100)
    tab.animation.setEasingCurve(QEasingCurve.InOutCubic)
    tab.animation.start()

    try:
        if (
            "detailed_range" in result
            and "major_divisions" in result
            and "special_ranges" in result
        ):
            tab._update_hundreds_display(
                result["main_code"],
                result["main_label"],
                result["detailed_range"],
                result["major_divisions"],
                result["special_ranges"],
                result["main_ctx"],
            )
        elif "range_results" in result:
            tab._update_range_results_display(
                result["main_code"],
                result["main_label"],
                result["range_results"],
                result["main_ctx"],
            )
        else:
            tab._populate_ui_from_context(
                result["main_ctx"], result["hierarchy_data"], result["path_codes"]
            )
    except Exception as e:
        tab.app_instance.log_message(
            f"오류: DDC 검색 결과 처리 실패 - {e}", level="ERROR"
        )
    finally:
        tab._finalize_fetch_dewey()


@Slot(str)
def _on_ddc_search_failed(tab, error_message):
    tab.app_instance.log_message(
        f"오류: DDC 검색 실패 - {error_message}", level="ERROR"
    )
    tab._finalize_fetch_dewey()


@Slot()
def _on_ksh_selection_changed(tab):
    selected_indexes = tab.ksh_table.selectionModel().selectedIndexes()
    if not selected_indexes:
        tab.dewey_preview_text.clear()
        return

    source_index = tab.ksh_proxy.mapToSource(selected_indexes[0])
    row_data = tab.ksh_model.get_row_data(source_index.row())

    if not row_data:
        return

    ksh_text = row_data.get("ksh", row_data.get("KSH", ""))
    title_text = row_data.get("title", row_data.get("서명/매칭", ""))

    concept_ids = extract_all_ksh_concept_ids(ksh_text)

    preview_lines = [f"Matched: {title_text}", ""]
    ksh_terms = re.findall(r"▼a([^▼]+)▼0(KSH\d+)▲", ksh_text)
    if ksh_terms:
        preview_lines.append("사용된 주제어:")
        for term, ksh_code in ksh_terms:
            preview_lines.append(f"▼a{term}▼0{ksh_code}▲")
        preview_lines.append("")

    for i, concept_id in enumerate(concept_ids):
        ksh_info = get_ksh_detailed_info(
            concept_id, tab.app_instance.db_manager, tab.app_instance.log_message
        )
        current_term, current_ksh_code = None, concept_id.replace("nlk:", "")

        for term, ksh_code in ksh_terms:
            if ksh_code == current_ksh_code:
                current_term = term
                break

        preview_lines.append(f"{i + 1}. 주제어 상세 정보")
        if current_term:
            preview_lines.append(f"▼a{current_term}▼0{current_ksh_code}▲")
        else:
            preview_lines.append(f"KSH 코드: {current_ksh_code}")
        preview_lines.append("")

        if ksh_info.get("pref"):
            formatted_pref = f"▼a{ksh_info['pref']}▼0{current_ksh_code}▲"
            preview_lines.extend(["우선어:", formatted_pref, ""])

        if ksh_info.get("definition"):
            preview_lines.extend([f"Definition: {ksh_info['definition']}", ""])

        for rel_type in ["related", "broader", "narrower", "synonyms"]:
            if ksh_info.get(rel_type):
                label = {
                    "related": "관련어",
                    "broader": "상위어",
                    "narrower": "하위어",
                    "synonyms": "동의어",
                }.get(rel_type)
                preview_lines.extend(
                    [
                        f"{label}:",
                        format_ksh_content_for_preview(ksh_info[rel_type]),
                        "",
                    ]
                )

        if ksh_info.get("ksh_link_url"):
            preview_lines.append(f"KSH 링크: {ksh_info['ksh_link_url']}")

        if i < len(concept_ids) - 1:
            preview_lines.extend(["", "=" * 70, ""])

    from qt_utils import linkify_text

    final_text = "\n".join(preview_lines)
    lines = final_text.split("\n")
    html_lines = []

    for line in lines:
        if not line.strip():
            continue

        linked_line = linkify_text(line)

        link_style = (
            f'style="color: {UI_CONSTANTS.ACCENT_BLUE}; text-decoration: none;"'
        )
        linked_line = linked_line.replace("<a href=", f"<a {link_style} href=")

        linked_line = (
            linked_line.replace("\r", "")
            .replace("\u2029", "")
            .replace("\xa0", " ")
            .strip()
        )

        html_lines.append(
            f'<div style="white-space: pre-wrap; margin: 0; padding: 0; line-height: 1.0; user-select: text; display: block;">{linked_line}</div>'
        )

    tables = [
        f'<table cellspacing="0" cellpadding="0" style="border:none;margin:0;padding:0;"><tr><td style="padding:0;border:none;">{line}</td></tr></table>'
        for line in html_lines
    ]
    final_html = "".join(tables)
    tab.dewey_preview_text.setHtml(final_html)


def _start_ksh_search(tab):
    raw_search_term = tab.dewey_ksh_search_entry.text().strip()
    if not raw_search_term:
        QMessageBox.warning(tab, "알림", "KSH 검색어를 입력해주세요.")
        return

    tab._cancel_ksh_search()

    tab.progress_bar.setVisible(True)
    tab.progress_bar.setRange(0, 100)
    tab.progress_bar.setValue(0)
    tab.dewey_ksh_search_button.setEnabled(False)
    tab.dewey_ksh_cancel_button.setEnabled(True)
    tab.app_instance.log_message(
        f"Dewey 탭: KSH Local DB 검색 시작: '{raw_search_term}'", "INFO"
    )

    tab.ksh_search_thread = DeweyKshSearchThread(tab.app_instance, raw_search_term, tab)
    tab.ksh_search_thread.finished.connect(tab._on_ksh_search_completed)
    tab.ksh_search_thread.error.connect(tab._on_ksh_search_failed)
    tab.ksh_search_thread.start()


def _start_dewey_tab_ksh_search(tab):
    raw_search_term = tab.dewey_ksh_search_entry.text().strip()
    if not raw_search_term:
        return

    tab._cancel_ksh_search()

    # ✅ [수정] 프로그레스 바를 0~100 범위로 설정하고 0%에서 시작
    tab.progress_bar.setVisible(True)
    tab.progress_bar.setRange(0, 100)
    tab.progress_bar.setValue(0)
    tab.dewey_ksh_search_button.setEnabled(False)
    tab.dewey_ksh_cancel_button.setEnabled(True)
    tab.app_instance.log_message(
        f"Dewey 탭: 자동 KSH 검색 시작: '{raw_search_term}'", "INFO"
    )

    tab.ksh_search_thread = DeweyKshSearchThread(tab.app_instance, raw_search_term, tab)
    tab.ksh_search_thread.finished.connect(tab._on_ksh_search_completed)
    tab.ksh_search_thread.error.connect(tab._on_ksh_search_failed)
    tab.ksh_search_thread.start()


def _cancel_ksh_search(tab):
    if tab.ksh_search_thread and tab.ksh_search_thread.isRunning():
        tab.ksh_search_thread.cancel()
    tab._finalize_ksh_search()


@Slot(object)
def _on_ksh_search_completed(tab, df_results):
    tab.ksh_model.clear_data()

    if df_results is not None and not df_results.empty:
        tab.app_instance.log_message(
            f"Dewey 탭: KSH 검색 완료 ({len(df_results)}개 결과)", "INFO"
        )
        records = df_results.to_dict("records")
        tab.ksh_model.add_multiple_rows(records, column_keys=tab.ksh_column_keys)
        adjust_qtableview_columns(
            tab.ksh_table,
            df_results,
            tab.ksh_column_keys,
            tab.ksh_column_headers,
            min_width=60,
            max_width=350,
        )
        focus_on_first_table_view_item(tab.ksh_table)
    else:
        tab.app_instance.log_message("Dewey 탭: KSH 검색 결과가 없습니다.", "INFO")

    # 🔥 [핵심 추가] 애니메이션으로 부드럽게 100%로 채우기
    tab.animation = QPropertyAnimation(tab.progress_bar, b"value")
    tab.animation.setDuration(800)
    tab.animation.setStartValue(tab.progress_bar.value())
    tab.animation.setEndValue(100)
    tab.animation.setEasingCurve(QEasingCurve.InOutCubic)
    tab.animation.start()

    tab._finalize_ksh_search()


@Slot(str)
def _on_ksh_search_failed(tab, error_message):
    tab.app_instance.log_message(f"Dewey 탭: KSH 검색 실패: {error_message}", "ERROR")
    tab._finalize_ksh_search()


def _finalize_ksh_search(tab):
    tab.dewey_ksh_search_button.setEnabled(True)
    tab.dewey_ksh_cancel_button.setEnabled(False)
    if tab.ksh_search_thread:
        tab.ksh_search_thread.wait()
        tab.ksh_search_thread = None


# 6. UI 업데이트 관련 (중요!)


def _update_hundreds_display(
    tab,
    main_code,
    main_label,
    detailed_range,
    major_divisions,
    special_ranges,
    main_ctx,
):
    tab.dewey_context_model.clear()
    tab.dewey_context_model.setHorizontalHeaderLabels(["DDC Hierarchy"])
    root_item = tab.dewey_context_model.invisibleRootItem()

    short_label = main_label.split("(")[0].strip() if "(" in main_label else main_label

    root_node = QStandardItem(f"{main_code} {short_label}")
    root_node.setEditable(False)
    root_item.appendRow(root_node)

    detail_group = QStandardItem(f"{main_code} {short_label}")
    detail_group.setEditable(False)
    root_node.appendRow(detail_group)

    if special_ranges:
        for code, label in sorted(special_ranges.items()):
            range_item = QStandardItem(f"{code} {label}")
            range_item.setEditable(False)
            detail_group.appendRow(range_item)
            tab._add_dummy_child(range_item)

    sorted_details = sorted([code for code in detailed_range.keys()])
    for code in sorted_details:
        label = detailed_range[code]
        detail_item = QStandardItem(f"{code} {label}")
        detail_item.setEditable(False)
        detail_group.appendRow(detail_item)
        tab._add_dummy_child(detail_item)

    sorted_majors = sorted([code for code in major_divisions.keys()])
    for code in sorted_majors:
        label = major_divisions[code]
        short_major_label = label.split("(")[0].strip() if "(" in label else label
        major_item = QStandardItem(f"{code} {short_major_label}")
        major_item.setEditable(False)
        root_node.appendRow(major_item)
        tab._add_dummy_child(major_item)

    related_items = main_ctx.get("related", [])
    related_header = None
    if related_items:
        related_header = QStandardItem("  + 관련 개념")
        related_header.setEditable(False)
        related_header.setData(
            {"code": "", "type": "related_header", "label": "관련 개념"},
            Qt.ItemDataRole.UserRole,
        )
        detail_group.appendRow(related_header)

        for item_data in related_items:
            code = normalize_ddc_code(dewey_get_safe(item_data, "notation"))
            label = dewey_pick_label(item_data.get("prefLabel"))

            if not (code and label):
                continue

            item = QStandardItem(f"    └ {code}  {label}")
            item.setEditable(False)
            item.setData(
                {"code": code, "type": "related", "label": label},
                Qt.ItemDataRole.UserRole,
            )
            related_header.appendRow(item)

    root_index = tab.dewey_context_model.indexFromItem(root_node)
    tab.dewey_context_tree.expand(root_index)

    detail_group_index = tab.dewey_context_model.indexFromItem(detail_group)
    tab.dewey_context_tree.expand(detail_group_index)

    if related_header:
        related_index = tab.dewey_context_model.indexFromItem(related_header)

    tab.dewey_context_tree.resizeColumnToContents(0)

    tab._fill_detail_text(main_ctx)
    tab._update_range_navigation(main_code)

    try:
        if tab.is_interlock_enabled:
            if main_label and main_label != "Label not found":
                processed_label = preprocess_dewey_description_for_ksh(
                    tab.app_instance, main_label
                )
                hybrid_search_term = f"{main_code}, {processed_label}"
                tab.dewey_ksh_search_entry.setText(hybrid_search_term)
            tab._start_dewey_tab_ksh_search()
    except Exception as e:
        tab.app_instance.log_message(f"오류: KSH 연동 실패 - {e}", level="ERROR")

    total_items = len(detailed_range) + len(major_divisions) + len(special_ranges)
    tab.app_instance.log_message(
        f"정보: {main_code} 백의자리 검색 완료 ({total_items}개 항목)", level="INFO"
    )


def _update_range_navigation(tab, main_code):
    cur = tab._dewey_nav_current
    if cur and cur != main_code:
        tab._dewey_nav_back_stack.append(cur)
        tab._dewey_nav_forward_stack.clear()

    tab._dewey_nav_current = main_code
    tab._update_nav_buttons()


def _update_range_results_display(
    tab,
    main_code,
    main_label,
    range_results,
    main_ctx,
):
    tab.dewey_context_model.clear()
    tab.dewey_context_model.setHorizontalHeaderLabels(["DDC Hierarchy"])
    root_item = tab.dewey_context_model.invisibleRootItem()

    parent_code = get_parent_code(main_code)
    if parent_code and parent_code in range_results:
        parent_label = range_results[parent_code]
        parent_node = QStandardItem(f"{parent_code}  {parent_label}")
        parent_node.setEditable(False)
        parent_node.setData(
            {"code": parent_code, "type": "parent", "label": parent_label},
            Qt.ItemDataRole.UserRole,
        )
        root_item.appendRow(parent_node)
    else:
        parent_node = root_item

    siblings = {}
    children = {}
    for code, label in range_results.items():
        if code == main_code or code == parent_code:
            continue
        if get_parent_code(code) == parent_code:
            siblings[code] = label
        elif code.startswith(main_code):
            children[code] = label
        else:
            siblings[code] = label

    main_node = QStandardItem(f"{main_code}  {main_label}")
    main_node.setEditable(False)
    main_node.setData(
        {"code": main_code, "type": "main", "label": main_label},
        Qt.ItemDataRole.UserRole,
    )
    parent_node.appendRow(main_node)

    for code in sorted(siblings.keys()):
        label = siblings[code]
        sibling_item = QStandardItem(f"{code}  {label}")
        sibling_item.setData(
            {"code": code, "type": "sibling", "label": label},
            Qt.ItemDataRole.UserRole,
        )
        sibling_item.setEditable(False)
        parent_node.appendRow(sibling_item)
        tab._add_dummy_child(sibling_item)

    for code in sorted(children.keys()):
        label = range_results[code]
        child_item = QStandardItem(f"{code}  {label}")
        child_item.setEditable(False)
        child_item.setData(
            {"code": code, "type": "child", "label": label},
            Qt.ItemDataRole.UserRole,
        )
        main_node.appendRow(child_item)

        tab._add_dummy_child(child_item)

    related = main_ctx.get("related", [])
    related_header = None
    if related:
        related_header = QStandardItem("  + 관련 개념")
        related_header.setEditable(False)
        related_header.setData(
            {"code": "", "type": "related_header", "label": "관련 개념"},
            Qt.ItemDataRole.UserRole,
        )
        main_node.appendRow(related_header)

        for item in related:
            rel_code = normalize_ddc_code(dewey_get_safe(item, "notation"))
            rel_label = dewey_pick_label(item.get("prefLabel"))
            if rel_code and rel_label:
                rel_display_code = format_ddc_for_display(rel_code)
                rel_item = QStandardItem(f"    └ {rel_display_code} {rel_label}")
                rel_item.setData(
                    {"code": rel_code, "type": "related", "label": rel_label},
                    Qt.ItemDataRole.UserRole,
                )
                rel_item.setEditable(False)
                related_header.appendRow(rel_item)

    if parent_node != root_item:
        parent_index = tab.dewey_context_model.indexFromItem(parent_node)
        tab.dewey_context_tree.expand(parent_index)
    main_index = tab.dewey_context_model.indexFromItem(main_node)
    tab.dewey_context_tree.expand(main_index)
    if related_header:
        related_index = tab.dewey_context_model.indexFromItem(related_header)
        tab.dewey_context_tree.expand(related_index)

    tab.dewey_context_tree.resizeColumnToContents(0)

    tab._fill_detail_text(main_ctx)

    try:
        if tab.is_interlock_enabled:
            if main_label and main_label != "Label not found":
                processed_label = preprocess_dewey_description_for_ksh(
                    tab.app_instance, main_label
                )
                hybrid_search_term = f"{main_code}, {processed_label}"
                tab.dewey_ksh_search_entry.setText(hybrid_search_term)
                tab.app_instance.log_message(
                    f"정보: 범위 검색 기반 KSH 검색어 생성: '{hybrid_search_term}'",
                    level="INFO",
                )
            else:
                tab.dewey_ksh_search_entry.setText(main_code)

            tab._start_dewey_tab_ksh_search()
    except Exception as e:
        tab.app_instance.log_message(
            f"오류: 범위 검색 KSH 연동 실패 - {e}", level="ERROR"
        )

    tab.app_instance.log_message(
        f"정보: {main_code} 범위 검색 완료 ({len(range_results)}개 항목)",
        level="INFO",
    )


def _populate_ui_from_context(tab, ctx, hierarchy_data, path_codes):
    tab._populate_context_hierarchical(ctx, hierarchy_data, path_codes)
    tab._fill_detail_text(ctx)

    try:
        ddc_code = normalize_ddc_code(dewey_get_safe(ctx.get("main", {}), "notation"))
        if ddc_code and not tab._dewey_nav_current:
            tab._dewey_nav_current = ddc_code
            tab._update_nav_buttons()
    except:
        pass

    try:
        if tab.is_interlock_enabled:
            ddc_code = tab.dewey_ddc_entry.text().strip()
            main_label = dewey_pick_label(ctx.get("main", {}).get("prefLabel"))

            if ddc_code:
                if main_label and main_label != "Label not found":
                    processed_label = preprocess_dewey_description_for_ksh(
                        tab.app_instance, main_label
                    )
                    hybrid_search_term = f"{ddc_code}, {processed_label}"
                    tab.dewey_ksh_search_entry.setText(hybrid_search_term)
                    tab.app_instance.log_message(
                        f"정보: 자동 하이브리드 KSH 검색어 생성: '{hybrid_search_term}'",
                        level="INFO",
                    )
                else:
                    tab.dewey_ksh_search_entry.setText(ddc_code)
                    tab.app_instance.log_message(
                        f"정보: DDC 코드 전용 KSH 검색어 생성: '{ddc_code}' (레이블 없음)",
                        level="INFO",
                    )
                tab._start_dewey_tab_ksh_search()
    except Exception as e:
        tab.app_instance.log_message(
            f"오류: 자동 KSH 검색 연동 실패 - {e}", level="ERROR"
        )


def _populate_context_hierarchical(
    tab,
    ctx: dict,
    hierarchy_data: dict,
    path_codes: list,
):
    tab.dewey_context_model.clear()
    tab.dewey_context_model.setHorizontalHeaderLabels(["DDC Hierarchy"])
    root_item = tab.dewey_context_model.invisibleRootItem()

    main = ctx.get("main")
    if not main:
        tab.app_instance.log_message(
            "오류: API 응답에 'main' 데이터가 없습니다.", level="ERROR"
        )
        return

    raw_main_code = dewey_get_safe(main, "notation")
    main_code = normalize_ddc_code(raw_main_code)

    parent_items = {"": root_item}

    for code in path_codes:
        if not code:
            continue

        # ✅ [수정] get_parent_code()가 반환한 코드(예: "641.50")를
        # 한번 더 정규화(예: "641.5")하여 부모 노드를 정확히 찾도록 수정
        raw_parent_code = get_parent_code(code)
        parent_code = normalize_ddc_code(raw_parent_code)
        parent_node = parent_items.get(parent_code, root_item)
        label = hierarchy_data.get(code, "Label not found")

        item = QStandardItem(f"{code}  {label}")
        item.setEditable(False)
        item.setData(
            {"code": code, "type": "hierarchy", "label": label},
            Qt.ItemDataRole.UserRole,
        )
        parent_node.appendRow(item)
        parent_items[code] = item

    main_node = parent_items.get(main_code, root_item)

    narrower_list = ctx.get("narrower", [])
    narrower_sorted = sorted(
        narrower_list,
        key=lambda x: normalize_ddc_code(dewey_get_safe(x, "notation")),
    )

    for item_data in narrower_sorted:
        code = normalize_ddc_code(dewey_get_safe(item_data, "notation"))
        label = dewey_pick_label(item_data.get("prefLabel"))

        if not (code and label):
            continue

        item = QStandardItem(f"  └ {code}  {label}")
        item.setEditable(False)
        item.setData(
            {"code": code, "type": "narrower", "label": label},
            Qt.ItemDataRole.UserRole,
        )
        main_node.appendRow(item)

        tab._add_dummy_child(item)

    related_items = ctx.get("related", [])
    if related_items:
        related_header = QStandardItem("  + 관련 개념")
        related_header.setEditable(False)
        related_header.setData(
            {"code": "", "type": "related_header", "label": "관련 개념"},
            Qt.ItemDataRole.UserRole,
        )
        main_node.appendRow(related_header)

        for item_data in related_items:
            code = normalize_ddc_code(dewey_get_safe(item_data, "notation"))
            label = dewey_pick_label(item_data.get("prefLabel"))

            if not (code and label):
                continue

            item = QStandardItem(f"    └ {code}  {label}")
            item.setEditable(False)
            item.setData(
                {"code": code, "type": "related", "label": label},
                Qt.ItemDataRole.UserRole,
            )
            related_header.appendRow(item)

    for code in path_codes:
        if code in parent_items:
            item = parent_items[code]
            index = tab.dewey_context_model.indexFromItem(item)
            tab.dewey_context_tree.expand(index)


def _fill_detail_text(tab, ctx: dict):
    lines = []
    main = ctx.get("main", {})

    code = normalize_ddc_code(dewey_get_safe(main, "notation"))
    disp_code = format_ddc_for_display(code)
    label = dewey_pick_label(main.get("prefLabel"))

    lines.append(f"[분류 코드]: {disp_code or ''}")
    lines.append(f"[기본 설명]: {label or ''}")

    scope = _as_list(main.get("scopeNote"))
    if scope:
        lines.append("[상세 노트]:")
        for s in scope:
            lines.append(f"- {dewey_pick_label(s)}")

    alts = _as_list(ctx.get("altLabels") or main.get("altLabel"))
    if alts:
        lines.append("[대체 용어]:")
        for a in alts:
            lines.append(f"- {dewey_pick_label(a)}")

    rels = ctx.get("related", [])
    if rels:
        lines.append("\n[관련 개념]:")
        for r in rels:
            r_code_raw = dewey_get_safe(r, "notation")
            r_code = normalize_ddc_code(r_code_raw)
            r_disp = format_ddc_for_display(r_code)
            lines.append(f"- {r_disp} {dewey_pick_label(r.get('prefLabel'))}")

    tab.dewey_detail_text.setPlainText("\n".join(lines))


# 7. 트리 이벤트 관련


def _on_tree_expand(tab, index):
    if not index.isValid():
        return

    item = tab.dewey_context_model.itemFromIndex(index)
    if not item or item.rowCount() == 0:
        return

    first_child = item.child(0)
    if not first_child or first_child.text() != "...":
        return

    text = item.text()
    code_match = re.match(r"^\s*[\-\+]?└?\s*(\d+(?:\.\d+)?)", text)
    if not code_match:
        item.removeRow(0)
        return

    ddc_to_load = normalize_ddc_code(code_match.group(1))

    first_child.setText("... 로딩 중 ...")

    client = getattr(tab.app_instance, "dewey_client", None)
    if client is None or not isinstance(client, DeweyClient):
        client = DeweyClient(tab.app_instance.db_manager)
        tab.app_instance.dewey_client = client

    tab._lazy_load_thread = DeweySearchThread(ddc_to_load, client, tab)
    tab._lazy_load_thread.search_finished.connect(
        lambda result: tab._on_lazy_load_finished(item, result)
    )
    tab._lazy_load_thread.search_failed.connect(
        lambda error: tab._on_lazy_load_failed(item, error)
    )
    tab._lazy_load_thread.start()


def _on_tree_collapse(tab, index):
    pass


def _on_lazy_load_finished(tab, parent_item, result):
    # ✅ [안정성 개선] QStandardItem이 이미 삭제되었을 수 있음
    try:
        if parent_item.rowCount() > 0:
            parent_item.removeRow(0)
    except RuntimeError:
        # 아이템이 이미 삭제됨 (사용자가 트리를 접거나 다른 검색 시작)
        return

    ctx = result.get("main_ctx", {})
    narrower_list = ctx.get("narrower", [])
    narrower_sorted = sorted(
        narrower_list,
        key=lambda x: normalize_ddc_code(dewey_get_safe(x, "notation")),
    )

    for item_data in narrower_sorted:
        code = normalize_ddc_code(dewey_get_safe(item_data, "notation"))
        label = dewey_pick_label(item_data.get("prefLabel"))

        if not (code and label):
            continue

        try:
            child_item = QStandardItem(f"  └ {code}  {label}")
            child_item.setEditable(False)
            parent_item.appendRow(child_item)
            tab._add_dummy_child(child_item)
        except RuntimeError:
            # parent_item이 중간에 삭제됨
            return


def _on_lazy_load_failed(tab, parent_item, error):
    # ✅ [안정성 개선] QStandardItem이 이미 삭제되었을 수 있음
    try:
        if parent_item.rowCount() > 0:
            parent_item.removeRow(0)
    except RuntimeError:
        # 아이템이 이미 삭제됨 (무시하고 계속)
        pass

    tab.app_instance.log_message(f"오류: 하위 항목 로딩 실패 - {error}", level="ERROR")


def _add_dummy_child(tab, item):
    dummy = QStandardItem("...")
    dummy.setEditable(False)
    item.appendRow(dummy)


def _open_selected_ddc(tab, index=None):
    if index is None or not index.isValid():
        indexes = tab.dewey_context_tree.selectedIndexes()
        if not indexes:
            return
        index = indexes[0]

    item = tab.dewey_context_model.itemFromIndex(index)
    if not item:
        return

    text = item.text()

    code_match = re.match(
        r"^\s*[\-\+]?└?\s*(\d+(?:\.\d+)?(?:[~\-–—]+\d+(?:\.\d+)?)?)", text
    )
    if not code_match:
        return

    code = normalize_ddc_code(code_match.group(1))

    if is_table_notation(code):
        tab.app_instance.log_message(
            "정보: 보조표 표목은 직접 조회하지 않습니다.", level="INFO"
        )
        return

    if code.isdigit() and len(code) < 3:
        code = code.zfill(3)

    try:
        if hasattr(tab.app_instance, "dewey_client") and hasattr(
            tab.app_instance.dewey_client,
            "get_ddc_with_parents",
        ):
            tab.app_instance.dewey_client.get_ddc_with_parents(code)
    except Exception as _e:
        tab.app_instance.log_message(f"경고: DDC 프리패치 실패: {_e}", level="WARNING")

    tab._navigate_to_code(code, add_to_history=True)


# 8. 검색 시작/데이터 수신


def start_search(tab):
    """BaseSearchTab의 start_search를 오버라이드하여 KSH 검색 실행"""
    tab._start_ksh_search()


# ✅ [신규 추가] MARC 추출 탭 등으로부터 데이터를 수신하는 메서드


def receive_data(tab, ddc=None, isbn=None, author=None, title=None, **kwargs):
    """
    다른 탭에서 전송된 데이터를 해당 탭의 입력 필드에 설정하고,
    관련 검색을 자동으로 시작합니다.
    """
    if ddc and hasattr(tab, "dewey_ddc_entry"):
        tab.app_instance.log_message(f"✅ MARC 추출: DDC '{ddc}' 수신", "INFO")
        # 1. 메인 윈도우 탭 전환 (주석 처리 - 자동 전환 안 함)
        # if hasattr(tab.app_instance, "main_window"):
        #     tab.app_instance.main_window.switch_to_tab_by_name("Dewey 분류 검색")
        # 2. DDC 입력창에 값 설정
        tab.dewey_ddc_entry.setText(ddc)
        # 3. 0.1초 후 DDC 검색 자동 시작
        QTimer.singleShot(100, lambda: tab._navigate_to_code(ddc, add_to_history=True))


# 9. 컨텍스트 메뉴 관련


def _on_ddc_entry_context_menu(tab, pos):
    menu = QMenu(tab.dewey_ddc_entry)

    selected_text = tab.dewey_ddc_entry.selectedText().strip()
    if selected_text:
        menu.addAction(
            f"🔍 선택된 DDC 번호 검색 ({selected_text})",
            lambda: tab._navigate_to_code(selected_text, add_to_history=True),
        )
        menu.addSeparator()

    full_text = tab.dewey_ddc_entry.text().strip()
    if full_text:
        menu.addAction(
            f"🔍 입력된 DDC 번호 검색 ({full_text})",
            lambda: tab._navigate_to_code(full_text, add_to_history=True),
        )
        menu.addSeparator()

    menu.addAction("✂️ 잘라내기", tab.dewey_ddc_entry.cut)
    menu.addAction("📋 복사", tab.dewey_ddc_entry.copy)
    menu.addAction("📄 붙여넣기", tab.dewey_ddc_entry.paste)
    menu.addAction("🗑️ 삭제", tab.dewey_ddc_entry.clear)

    menu.exec_(tab.dewey_ddc_entry.mapToGlobal(pos))


def _on_dewey_context_tree_right_click(tab, pos):
    try:
        index = tab.dewey_context_tree.indexAt(pos)
        if not index.isValid():
            return

        item = tab.dewey_context_model.itemFromIndex(index)
        if not item:
            return

        data = item.data(Qt.ItemDataRole.UserRole)

        if not data:
            text = item.text()
            code_match = re.match(
                r"^\s*[\-\+]?└?\s*(\d+(?:\.\d+)?(?:[~\-–—]+\d+(?:\.\d+)?)?)", text
            )
            if code_match:
                extracted_code = code_match.group(1)
                data = {"code": extracted_code, "type": "extracted"}
            else:
                return

        ddc_code = data.get("code", "")
        ddc_disp = format_ddc_for_display(ddc_code) if ddc_code else ""
        is_related_header = data.get("type") == "related_header"

        item_text = item.text()
        label_text = None

        if not is_related_header:
            t = item_text.replace("└", " ").strip()
            if ddc_disp and ddc_disp in t:
                label_text = t.split(ddc_disp, 1)[-1].strip()
            else:
                label_text = re.sub(
                    r"^\s*(T\d+--\d+|\d+(?:\.\d+)*(?:-\d+(?:\.\d+)*)?)\s*", "", t
                ).strip()

        menu = QMenu(tab.dewey_context_tree)

        if ddc_code:
            menu.addAction(
                f"🔍 선택된 DDC 번호 검색 ({ddc_disp or ddc_code})",
                lambda: tab._navigate_to_code(ddc_code, add_to_history=True),
            )
            menu.addSeparator()

        if ddc_code:
            menu.addAction(
                f"📋 DDC 코드 복사 ({ddc_disp or ddc_code})",
                lambda: _copy_text_to_clipboard(
                    ddc_disp or ddc_code, tab.app_instance, "DDC"
                ),
            )

        if label_text:
            preview = (label_text[:20] + "...") if len(label_text) > 20 else label_text
            menu.addAction(
                f"📋 레이블 복사 ({preview})",
                lambda: _copy_text_to_clipboard(label_text, tab.app_instance, "레이블"),
            )

        menu.addAction(
            "📋 전체 텍스트 복사",
            lambda: _copy_text_to_clipboard(
                item_text.strip(), tab.app_instance, "전체 텍스트"
            ),
        )

        menu.addAction(
            "📄 선택된 모든 항목 복사", lambda: tab._copy_tree_selection("left")
        )

        menu.addSeparator()

        if label_text:
            processed_label = preprocess_dewey_description_for_ksh(
                tab.app_instance, label_text
            )
            combined_term = f"{ddc_disp or ddc_code}, {processed_label}"
            preview_combined = (
                (combined_term[:30] + "...")
                if len(combined_term) > 30
                else combined_term
            )
            menu.addAction(
                f"🔍 '{preview_combined}' 복합 KSH 검색",
                lambda: _search_ksh_with_combined_term(
                    combined_term, tab.app_instance, tab
                ),
            )

        menu.addSeparator()

        if ddc_code:
            menu.addAction(
                f"🔍 DDC {ddc_disp or ddc_code}로 KSH 검색",
                lambda: _search_ksh_with_ddc(ddc_code, tab.app_instance, tab),
            )
            menu.addAction(
                f"🌐 DDC {ddc_disp or ddc_code} LibraryThing 검색",
                lambda: _open_ddc_online_info(ddc_code),
            )

        if label_text:
            preview = (label_text[:20] + "...") if len(label_text) > 20 else label_text
            menu.addAction(
                f"🔍 '{preview}'로 KSH 검색",
                lambda: _search_ksh_with_processed_label(
                    label_text, tab.app_instance, tab
                ),
            )
        elif is_related_header:
            menu.addAction(
                "🔍 모든 관련 개념으로 다중 KSH 검색",
                lambda: _search_ksh_with_all_related_concepts(
                    item, tab.dewey_context_tree, tab.app_instance, tab
                ),
            )

        menu.addSeparator()

        text_for_translation = label_text if label_text else item_text.strip()

        menu.addAction(
            "🌐 인앱 번역",
            lambda: _dewey_open_inapp_translate(text_for_translation, tab.app_instance),
        )
        menu.addAction(
            "🌐 롱맨 영영사전 검색",
            lambda: _dewey_open_dictionary(text_for_translation, tab.app_instance),
        )
        menu.addAction(
            "🌐 Google 번역 (Auto→한)",
            lambda: _dewey_open_google_translate_auto_ko(
                text_for_translation, tab.app_instance
            ),
        )
        menu.addAction(
            "🌐 Google 번역 (한→영)",
            lambda: _dewey_open_google_translate_ko_en(
                text_for_translation, tab.app_instance
            ),
        )
        menu.addAction(
            "🌐 네이버 사전 검색",
            lambda: _dewey_open_naver_dictionary(
                text_for_translation, tab.app_instance
            ),
        )

        menu.addSeparator()

        menu.addAction(
            "📊 DDC 계층 정보 보기",
            lambda: _show_ddc_hierarchy_info(
                item, tab.dewey_context_tree, tab.app_instance
            ),
        )
        menu.addAction(
            "📋 계층 경로 복사",
            lambda: _copy_hierarchy_path(
                item, tab.dewey_context_tree, tab.app_instance
            ),
        )

        menu.addSeparator()

        parent_ddc = (
            get_parent_code(ddc_code)
            if ddc_code and should_lazy_expand(ddc_code)
            else ""
        )
        if parent_ddc:
            menu.addAction(
                f"🔼 상위 단계로 ({parent_ddc})",
                lambda: tab._navigate_to_code(parent_ddc, add_to_history=True),
            )

        menu.exec_(tab.dewey_context_tree.mapToGlobal(pos))

    except Exception as e:
        tab.app_instance.log_message(
            f"오류: DDC 트리뷰 컨텍스트 메뉴 실패: {e}", level="ERROR"
        )


# 10. 복사 관련


def handle_copy(tab):
    from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit, QPlainTextEdit

    focused_widget = QApplication.focusWidget()
    clipboard = QApplication.clipboard()
    copied_text = ""

    try:
        if isinstance(focused_widget, QLineEdit):
            copied_text = (
                focused_widget.selectedText() or focused_widget.text() or ""
            ).strip()

        elif isinstance(focused_widget, (QTextEdit, QPlainTextEdit)):
            try:
                cursor = focused_widget.textCursor()
                selected = cursor.selectedText()
            except Exception:
                selected = ""

            if selected:
                copied_text = selected
            else:
                if isinstance(focused_widget, QTextEdit):
                    copied_text = focused_widget.toPlainText()
                else:
                    copied_text = focused_widget.toPlainText()
            copied_text = (copied_text or "").strip()

        elif (
            focused_widget == getattr(tab, "dewey_context_tree", None)
            and tab.dewey_context_tree
        ):
            tab._copy_tree_selection("left")
            copied_text = (clipboard.text() or "").strip()

        elif focused_widget == getattr(tab, "ksh_table", None) and tab.ksh_table:
            copied_text = (tab._copy_table_selection() or "").strip()

        else:
            if (
                getattr(tab, "ksh_table", None)
                and tab.ksh_table.selectionModel()
                and tab.ksh_table.selectionModel().hasSelection()
            ):
                copied_text = (tab._copy_table_selection() or "").strip()
            elif (
                getattr(tab, "dewey_context_tree", None)
                and tab.dewey_context_tree.selectionModel()
                and tab.dewey_context_tree.selectionModel().hasSelection()
            ):
                tab._copy_tree_selection("left")
                copied_text = (clipboard.text() or "").strip()

    except Exception as e:
        if hasattr(tab, "app_instance") and hasattr(tab.app_instance, "log_message"):
            tab.app_instance.log_message(f"오류: 복사 처리 중 예외 - {e}", "ERROR")
        copied_text = ""

    if copied_text:
        clipboard.setText(copied_text)

        try:
            from qt_copy_feedback import copy_to_clipboard_with_feedback

            copy_to_clipboard_with_feedback(copied_text, tab.app_instance, tab)
        except Exception as _e:
            if hasattr(tab, "app_instance") and hasattr(
                tab.app_instance, "log_message"
            ):
                tab.app_instance.log_message(
                    f"경고: 복사 피드백 표시 실패 - {_e}", "WARNING"
                )

        if hasattr(tab, "app_instance") and hasattr(tab.app_instance, "log_message"):
            num_lines = copied_text.count("\n") + 1 if copied_text else 0
            preview = copied_text.replace("\n", " ")
            if len(preview) > 40:
                preview = preview[:40] + "..."
            tab.app_instance.log_message(
                f"정보: {num_lines}줄 복사됨: '{preview}' [Ctrl+C]",
                "INFO",
            )
    else:
        if hasattr(tab, "app_instance") and hasattr(tab.app_instance, "log_message"):
            tab.app_instance.log_message("⚠️ 복사: 복사할 텍스트가 없습니다", "WARNING")


def _copy_table_selection(tab) -> str:
    selection_model = tab.ksh_table.selectionModel()
    if not selection_model or not selection_model.hasSelection():
        return ""

    selected_indexes = selection_model.selectedIndexes()
    if not selected_indexes:
        return ""

    rows_data = {}
    for index in selected_indexes:
        source_index = tab.ksh_proxy.mapToSource(index)
        row, col = source_index.row(), source_index.column()
        if row not in rows_data:
            rows_data[row] = {}
        rows_data[row][col] = tab.ksh_model.data(
            source_index, Qt.ItemDataRole.DisplayRole
        )

    text_lines = []
    for row in sorted(rows_data.keys()):
        row_cells = []
        for col in sorted(rows_data[row].keys()):
            row_cells.append(str(rows_data[row][col] or ""))
        text_lines.append("\t".join(row_cells))

    return "\n".join(text_lines)


def _copy_tree_selection(tab, side="left"):
    tree = tab.dewey_context_tree

    unique_row_indexes = tree.selectionModel().selectedRows()

    if not unique_row_indexes:
        tab.app_instance.log_message("복사할 항목이 선택되지 않았습니다.", level="INFO")
        return

    copy_lines = []
    if side == "left":
        for index in unique_row_indexes:
            item = tab.dewey_context_model.itemFromIndex(index)

            if not item:
                continue

            text = item.text().strip()
            data = item.data(Qt.ItemDataRole.UserRole)
            code = data.get("code", "") if data else ""
            disp = format_ddc_for_display(code) if code else ""

            label = text
            if disp and disp in text:
                label = text.split(disp, 1)[-1].strip()
            label = label.lstrip("└").strip()
            copy_lines.append(f"{disp or code} {label}".strip())

    if copy_lines:
        out = "\n".join(copy_lines)
        QApplication.clipboard().setText(out)

        from qt_copy_feedback import copy_to_clipboard_with_feedback

        copy_to_clipboard_with_feedback(out, tab.app_instance, tab)

        tab.app_instance.log_message(
            f"정보: {len(copy_lines)}개 항목을 클립보드에 복사했습니다.",
            level="INFO",
        )


def _make_widget_copyable(tab, widget):
    widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def copy_text(pos):
        try:
            text = widget.text()
            QApplication.clipboard().setText(text)
            tab.app_instance.log_message(f"정보: '{text}' 복사됨", level="INFO")
        except Exception as e:
            tab.app_instance.log_message(f"오류: 텍스트 복사 실패 - {e}", level="ERROR")

    widget.customContextMenuRequested.connect(copy_text)


def _copy_text_to_clipboard(text, app_instance, text_type="텍스트"):
    """클립보드 복사"""
    try:
        if text:
            # -------------------
            # ✅ [핵심 수정 1] 복사 피드백 함수를 호출하는 모듈 레벨 헬퍼 함수의 인자 순서 수정
            from qt_copy_feedback import copy_to_clipboard_with_feedback

            # 이 함수는 DDC 트리뷰의 컨텍스트 메뉴에서 사용되며,
            # DDC 코드나 레이블 같은 단일 텍스트 복사를 위해 클립보드 복사 로직과 피드백을 모두 포함합니다.

            # **주의**: 이 함수는 이미 텍스트가 복사되었다고 가정하고, 피드백만 요청하는 래퍼 함수로 사용되어야 합니다.
            # 하지만 안전을 위해 클립보드 복사 후 피드백을 표시하는 방식으로 재구성합니다.

            QApplication.clipboard().setText(text)

            # 피드백 함수 호출 (parent_widget=None)
            copy_to_clipboard_with_feedback(
                text=text,
                app_instance=app_instance,
                parent_widget=None,  # 모듈 레벨에서 호출되므로 parent는 None
            )

            preview = (text[:15] + "...") if len(text) > 15 else text
            app_instance.log_message(
                f"정보: {text_type} '{preview}'가 복사되었습니다.", level="INFO"
            )
            # -------------------
    except Exception as e:
        app_instance.log_message(f"오류: {text_type} 복사 실패: {e}", level="ERROR")


def _search_ksh_with_ddc(ddc_code, app_instance, tab_instance):
    """DDC로 KSH 검색"""
    try:
        tab_instance.dewey_ksh_search_entry.setText(ddc_code)
        tab_instance._start_dewey_tab_ksh_search()
        app_instance.log_message(
            f"정보: DDC {ddc_code}로 KSH 검색을 시작합니다.", level="INFO"
        )
    except Exception as e:
        app_instance.log_message(f"오류: DDC로 KSH 검색 실패: {e}", level="ERROR")


def _search_ksh_with_processed_label(label_text, app_instance, tab_instance):
    """레이블로 KSH 검색"""
    try:
        # -------------------
        # ✅ [수정] import한 함수를 사용하고, 올바른 인자(db_manager)를 전달합니다.
        processed_label = preprocess_dewey_description_for_ksh(
            app_instance.db_manager, label_text
        )
        # -------------------
        tab_instance.dewey_ksh_search_entry.setText(processed_label)
        tab_instance._start_dewey_tab_ksh_search()
        app_instance.log_message(
            f"정보: '{processed_label}'로 KSH 검색을 시작합니다.", level="INFO"
        )
    except Exception as e:
        app_instance.log_message(f"오류: 레이블로 KSH 검색 실패: {e}", level="ERROR")


def _search_ksh_with_combined_term(combined_term, app_instance, tab_instance):
    """복합 검색어로 KSH 검색"""
    try:
        tab_instance.dewey_ksh_search_entry.setText(combined_term)
        tab_instance._start_dewey_tab_ksh_search()
        app_instance.log_message(
            f"정보: 복합 검색어로 KSH 검색 시작: '{combined_term}'", level="INFO"
        )
    except Exception as e:
        app_instance.log_message(f"오류: 복합 KSH 검색 실패: {e}", level="ERROR")


def _search_ksh_with_all_related_concepts(
    item: QStandardItem, treeview, app_instance, tab_instance
):
    try:
        if item.rowCount() == 0:
            app_instance.log_message("관련 개념이 없습니다.", level="WARNING")
            return

        terms = []
        for i in range(item.rowCount()):
            child = item.child(i)
            text = child.text().strip()
            # "    └ 123.4  Label" 형식에서 라벨만 추출
            label = re.sub(r".*?└\s*\d+(?:\.\d+)*\s*", "", text).strip()
            if label:
                # -------------------
                # ✅ [수정] import한 함수를 사용하고, 올바른 인자(db_manager)를 전달합니다.
                processed = preprocess_dewey_description_for_ksh(
                    app_instance.db_manager, label
                )
                # -------------------
                if processed:
                    terms.append(processed)

        if not terms:
            app_instance.log_message("추출된 관련 개념이 없습니다.", level="WARNING")
            return

        multi = ", ".join(terms)
        tab_instance.dewey_ksh_search_entry.setText(multi)
        tab_instance._start_dewey_tab_ksh_search()
        app_instance.log_message(
            f"정보: {len(terms)}개 관련 개념으로 다중 KSH 검색 시작: {multi}", "INFO"
        )
    except Exception as e:
        app_instance.log_message(f"오류: 모든 관련 개념 KSH 검색 실패: {e}", "ERROR")


def _open_ddc_online_info(ddc_code):
    """LibraryThing에서 DDC 검색"""
    try:
        url = f"https://www.librarything.com/mds/{ddc_code}"
        webbrowser.open(url)
    except Exception as e:
        print(f"오류: DDC 온라인 정보 열기 실패: {e}")


def _show_ddc_hierarchy_info(item, treeview, app_instance):
    """QStandardItem 또는 QTreeWidgetItem 모두 지원"""
    try:
        hierarchy_info = []
        current_item = item

        # QStandardItem일 때
        if hasattr(current_item, "text") and callable(current_item.text):
            while current_item:
                # QStandardItem.data(role)
                data = current_item.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict) and data.get("label"):
                    ddc_code = data.get("code", "코드 없음")
                    full_label = data.get("label")
                    display_text = f"{ddc_code}  {full_label}"
                else:
                    display_text = current_item.text().strip()
                hierarchy_info.insert(0, f"• {display_text}")
                current_item = current_item.parent()

        # QTreeWidgetItem일 때 (레거시)
        else:
            while current_item:
                data = current_item.data(0, Qt.ItemDataRole.UserRole)
                if data and data.get("label"):
                    ddc_code = data.get("code", "코드 없음")
                    full_label = data.get("label")
                    display_text = f"{ddc_code}  {full_label}"
                else:
                    display_text = current_item.text(0).strip()
                hierarchy_info.insert(0, f"• {display_text}")
                current_item = current_item.parent()

        full_info = "DDC 계층 구조:\n\n" + "\n".join(hierarchy_info)

        # 추가 정보 (가능한 경우)
        if hasattr(item, "data"):
            data = item.data(Qt.ItemDataRole.UserRole)
        else:
            data = item.data(0, Qt.ItemDataRole.UserRole)

        if data:
            full_info += f"\n\n추가 정보:\n• 타입: {data.get('type', 'N/A')}"

        show_cell_detail_dialog(full_info, "DDC 계층 정보", app_instance)

    except Exception as e:
        app_instance.log_message(f"오류: DDC 계층 정보 표시 실패: {e}", level="ERROR")


def _copy_hierarchy_path(item, treeview, app_instance):
    """QStandardItem/QTreeWidgetItem 모두 지원"""
    try:
        path_parts = []
        current_item = item

        if hasattr(current_item, "text") and callable(current_item.text):
            while current_item:
                path_parts.insert(0, current_item.text().strip())
                current_item = current_item.parent()
        else:
            while current_item:
                path_parts.insert(0, current_item.text(0).strip())
                current_item = current_item.parent()

        hierarchy_path = " > ".join(path_parts)
        QApplication.clipboard().setText(hierarchy_path)
        show_copy_feedback(app_instance, f"계층 경로: {len(path_parts)}단계")
        app_instance.log_message("정보: DDC 계층 경로가 복사되었습니다.", level="INFO")
    except Exception as e:
        app_instance.log_message(f"오류: 계층 경로 복사 실패: {e}", level="ERROR")


def _dewey_open_inapp_translate(text, app_instance):
    """인앱 번역"""
    try:
        from api_clients import translate_text

        translation = translate_text(text, db_manager=app_instance.db_manager)
        # ✅ 통일: 단일 셀 상세 모달로 출력
        body = f"원문\n-----\n{text}\n\n번역\n-----\n{translation}"
        show_cell_detail_dialog(body, "번역 결과", app_instance)
    except Exception as e:
        app_instance.log_message(f"오류: 인앱 번역 실패: {e}", level="ERROR")


def _dewey_open_naver_dictionary(text, app_instance):
    """네이버 사전 검색"""
    try:
        open_naver_dictionary(text, app_instance)
    except Exception as e:
        app_instance.log_message(f"오류: 네이버 사전 검색 실패: {e}", level="ERROR")


def _dewey_open_dictionary(text, app_instance):
    """롱맨 영영사전 검색"""
    try:
        open_dictionary(text, app_instance)
    except Exception as e:
        app_instance.log_message(f"오류: 롱맨 영영사전 검색 실패: {e}", level="ERROR")


def _dewey_open_google_translate_auto_ko(text, app_instance):
    """Google 번역 (Auto→한)"""
    try:
        open_google_translate(text, app_instance, source_lang="auto", target_lang="ko")
    except Exception as e:
        app_instance.log_message(
            f"오류: Google 번역 (자동→한) 실패: {e}", level="ERROR"
        )


def _dewey_open_google_translate_ko_en(text, app_instance):
    """Google 번역 (한→영)"""
    try:
        open_google_translate(text, app_instance, source_lang="ko", target_lang="en")
    except Exception as e:
        app_instance.log_message(f"오류: Google 번역 (한→영) 실패: {e}", level="ERROR")
