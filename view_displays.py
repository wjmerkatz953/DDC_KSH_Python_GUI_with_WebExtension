# -*- coding: utf-8 -*-
# 파일명: view_displays.py
# Version: v2.0.1
# 수정일시: 2025-09-6 16:08 KST
# 변경 요지: 코드 분리

import webbrowser
import pandas as pd
import tempfile
import re
import os
import html
from ui_constants import UI_CONSTANTS
from queue import Queue, Empty
from PySide6.QtWidgets import QMenu, QHeaderView


class NonClosingMenu(QMenu):
    """체크 가능한 액션을 클릭해도 닫히지 않는 커스텀 메뉴"""

    def mouseReleaseEvent(self, event):
        action = self.activeAction()
        # 액션이 존재하고, 체크 가능한 액션일 경우에만 메뉴를 닫지 않음
        if action and action.isCheckable():
            action.trigger()  # 액션의 triggered 시그널만 발생시킴
        else:
            super().mouseReleaseEvent(
                event
            )  # 그 외의 경우(일반 버튼, 메뉴 밖 클릭)에는 원래대로 메뉴를 닫음


def inject_tooltips(html_string):
    return re.sub(
        r"<td>(.*?)</td>",
        lambda match: f'<td title="{html.escape(match.group(1), quote=True)}">{match.group(1)}</td>',
        html_string,
        flags=re.DOTALL,
    )


def infer_column_widths(
    df: pd.DataFrame, display_names: list, min_px=100, max_px=400, px_per_char=8
) -> dict:
    """
    각 컬럼의 문자열 길이에 기반하여 적절한 픽셀 폭을 추론합니다.
    우선순위 필드는 여유 공간 발생 시 가장 먼저 넓어집니다.
    """
    # 우선 넓어져야 할 필드 정의
    high_priority_fields = {
        "직업",
        "활동분야",
        "기관명",
        "관련 기관",
        "최근 저작물",
        "저작물 제목",
        "로마자 이름",
        "TITLE",
        "KAC",
        "제목",
        "저자",
        "서명",
        "저자명",
        "Title",
        "주제어",
        "주제어_원문",
        "245 필드",
        "650 필드",
        "주제",
        "분류기호(DDC)",
        "분류기호(KDC-Like)",
        "주제명",
    }

    column_widths = {}
    for i, col in enumerate(df.columns):
        col_name = display_names[i]
        lengths = df[col].dropna().astype(str).map(len)
        max_len = lengths.quantile(0.9) if not lengths.empty else 10

        base_width = max(min_px, min(max_px, int(max_len * px_per_char)))

        # 🎯 제목 컬럼에 대한 특별 처리 - 폭을 훨씬 더 크게!
        if col_name in ["제목", "저작물 제목", "TITLE", "서명"]:
            base_width = min(base_width, 100)
            base_width = max(base_width, 1000)
        # 우선순위 필드일 경우 최대폭을 늘려 허용
        elif col_name in high_priority_fields:
            base_width = min(base_width, 100)
            base_width = max(base_width, 500)

        column_widths[col_name] = f"{base_width}px"

    return column_widths


def show_in_html_viewer(
    app_instance,
    dataframe: pd.DataFrame,
    title: str,
    columns_to_display: list,
    display_names: list,
    link_column_name: str | list = None,
    sort_by: list = None,
    ascending: list = None,
    separator_column: str = None,
    column_widths: dict = None,
    auto_infer_widths: bool = True,
):
    """
    주어진 데이터프레임을 스타일링된 임시 HTML 파일로 생성하여 웹 브라우저에서 엽니다.
    """
    if dataframe is None or dataframe.empty:
        app_instance.show_messagebox("정보", "분석할 데이터가 없습니다.", "info")
        return

    try:
        # 컬럼 필터링
        if columns_to_display:
            filtered_df = dataframe[columns_to_display].copy()
        else:
            filtered_df = dataframe.copy()

        # 정렬
        if sort_by:
            if isinstance(sort_by, str):
                sort_by = [sort_by]
            if ascending is None:
                ascending = [True] * len(sort_by)
            elif isinstance(ascending, bool):
                ascending = [ascending] * len(sort_by)

            # 정렬할 컬럼이 실제로 존재하는지 확인
            valid_sort_columns = [col for col in sort_by if col in filtered_df.columns]
            if valid_sort_columns:
                filtered_df = filtered_df.sort_values(
                    by=valid_sort_columns,
                    ascending=ascending[: len(valid_sort_columns)],
                )

        # 컬럼명 변경 (display_names가 제공된 경우)
        if display_names and len(display_names) == len(filtered_df.columns):
            filtered_df.columns = display_names

        # 🔧 수정된 부분: column_widths 타입 안전성 검사
        # 함수 시작 부분에서 먼저 column_widths가 None일 경우 빈 딕셔너리로 초기화
        if column_widths is None:
            column_widths = {}

        if auto_infer_widths:
            # column_widths가 dict가 아닌 경우 (초기 None이 아닌 다른 타입) 경고 출력 후 초기화
            if not isinstance(column_widths, dict):
                app_instance.log_message(
                    f"경고: column_widths가 올바르지 않은 타입입니다: {type(column_widths)}. dict로 초기화합니다.",
                    level="WARNING",
                )
                column_widths = {}

            try:
                inferred_widths = infer_column_widths(
                    filtered_df, list(filtered_df.columns)
                )

                # inferred_widths도 dict인지 확인
                if isinstance(inferred_widths, dict):
                    column_widths.update(inferred_widths)
                else:
                    app_instance.log_message(
                        f"경고: inferred_widths가 dict가 아닙니다: {type(inferred_widths)}",
                        level="WARNING",
                    )
            except Exception as width_error:
                app_instance.log_message(
                    f"경고: 컬럼 폭 추론 중 오류: {width_error}", level="WARNING"
                )
                # 오류 발생 시 기본 column_widths 사용

        # HTML 생성
        html_string = filtered_df.to_html(
            index=False, escape=False, classes="table table-striped table-hover"
        )

        # 툴팁 추가
        html_string = inject_tooltips(html_string)

        # 전체 HTML 구조
        full_html = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <style>
                /* 현대적이고 가독성 좋은 테이블 스타일 */
                body {{
                    font-family: 'Segoe UI', Arial, sans-serif;
                    background: linear-gradient(270deg, #151a28 0%, #0e121b 100%);
                    margin: 0;
                    padding: 20px;
                    min-height: 100vh;
                }}

                .container {{
                    background: white;
                    border-radius: 15px;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.15);
                    padding: 30px;
                    margin: 0 auto;
                    max-width: 95%;
                    overflow-x: auto;
                }}

                h1 {{
                    color: #2c3e50;
                    text-align: center;
                    margin-bottom: 30px;
                    font-size: 2.2em;
                    font-weight: 300;
                    border-bottom: 3px solid #3498db;
                    padding-bottom: 15px;
                }}

                .table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                    font-size: 14px;
                    white-space: nowrap;
                }}

                .table th {{
                    background: linear-gradient(135deg, #151a28, #2980b9);
                    color: #cad1d9;
                    font-weight: 600;
                    padding: 15px 12px;
                    text-align: left;
                    border: none;
                    position: sticky;
                    top: 0;
                    z-index: 10;
                    text-shadow: 0 1px 1px rgba(0,0,0,0.3);
                }}

                .table td {{
                    padding: 12px;
                    border-bottom: 1px solid #ecf0f1;
                    transition: all 0.3s ease;
                    max-width: 300px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }}

                .table tbody tr:hover {{
                    background-color: #f8f9fa;
                    transform: scale(1.002);
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }}

                .table tbody tr:nth-child(even) {{
                    background-color: #fafbfc;
                }}

                /* 링크 스타일 */
                .table a {{
                    color: #3498db;
                    text-decoration: none;
                    font-weight: 500;
                    transition: color 0.3s ease;
                }}

                .table a:hover {{
                    color: #2980b9;
                    text-decoration: underline;
                }}

                /* 구분선 컬럼 스타일 */
                .separator-column {{
                    background-color: #f39c12 !important;
                    color: white !important;
                    font-weight: bold;
                    text-align: center;
                }}

                /* 반응형 */
                @media (max-width: 768px) {{
                    .container {{
                        padding: 15px;
                        margin: 10px;
                    }}

                    .table {{
                        font-size: 12px;
                    }}

                    .table th, .table td {{
                        padding: 8px 6px;
                    }}
                }}

                /* 스크롤바 스타일 */
                ::-webkit-scrollbar {{
                    width: 8px;
                    height: 8px;
                }}

                ::-webkit-scrollbar-track {{
                    background: #f1f1f1;
                    border-radius: 4px;
                }}

                ::-webkit-scrollbar-thumb {{
                    background: #3498db;
                    border-radius: 4px;
                }}

                ::-webkit-scrollbar-thumb:hover {{
                    background: #2980b9;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>{title}</h1>
                {html_string}
            </div>

            <script>
                // 테이블 개선 스크립트
                document.addEventListener('DOMContentLoaded', function() {{
                    const table = document.querySelector('.table');
                    if (table) {{
                        // 링크 컬럼 처리
                        const linkColumns = {repr(link_column_name) if link_column_name else 'null'};
                        if (linkColumns) {{
                            const columns = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());
                            const linkColumnIndices = [];

                            if (Array.isArray(linkColumns)) {{
                                linkColumns.forEach(linkCol => {{
                                    const index = columns.indexOf(linkCol);
                                    if (index !== -1) linkColumnIndices.push(index);
                                }});
                            }} else {{
                                const index = columns.indexOf(linkColumns);
                                if (index !== -1) linkColumnIndices.push(index);
                            }}

                            // 링크 컬럼의 셀들을 클릭 가능하게 만들기
                            table.querySelectorAll('tbody tr').forEach(row => {{
                                linkColumnIndices.forEach(colIndex => {{
                                    const cell = row.cells[colIndex];
                                    if (cell && cell.textContent.trim()) {{
                                        const url = cell.textContent.trim();
                                        if (url.startsWith('http')) {{
                                            cell.innerHTML = '<a href="' + url + '" target="_blank">' + url + '</a>';
                                        }}
                                    }}
                                }});
                            }});
                        }}

                        // 구분선 컬럼 처리
                        const separatorColumn = {repr(separator_column) if separator_column else 'null'};
                        if (separatorColumn) {{
                            const columns = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());
                            const separatorIndex = columns.indexOf(separatorColumn);
                            if (separatorIndex !== -1) {{
                                table.querySelectorAll(`th:nth-child(${{separatorIndex + 1}}), td:nth-child(${{separatorIndex + 1}})`).forEach(cell => {{
                                    cell.classList.add('separator-column');
                                }});
                            }}
                        }}
                    }}
                }});
            </script>
        </body>
        </html>
        """

        # 임시 파일 생성 및 열기
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(full_html)
            temp_path = f.name

        # 웹 브라우저에서 열기
        webbrowser.open("file://" + os.path.abspath(temp_path))

        app_instance.log_message(
            f"정보: HTML 뷰어로 {len(filtered_df)}개 행 표시됨", level="INFO"
        )

    except Exception as e:
        app_instance.log_message(f"오류: HTML 뷰어 생성 실패: {e}", level="ERROR")
        app_instance.show_messagebox(
            "오류", f"HTML 뷰어 생성에 실패했습니다: {e}", "error"
        )


def show_in_dropdown_html_viewer(
    app_instance,
    dataframe: pd.DataFrame,
    title: str,
    columns_to_display: list,
    display_names: list,
    link_column_name: str | list = None,
    auto_infer_widths: bool = True,
):  # 기능 제어를 위한 파라미터 추가
    # ✅ 드롭다운 필터 개수를 상수로 정의
    MAX_DROPDOWN_FILTERS = 9
    """
    드롭다운 컬럼 선택 + 다크/라이트 테마 + 자동 컬럼 너비 조절 기능이 포함된 HTML 뷰어
    """
    if dataframe is None or dataframe.empty:
        app_instance.show_messagebox("정보", "분석할 데이터가 없습니다.", "info")
        return

    try:
        # 데이터 준비
        # ✅ [수정] dataframe에 실제로 존재하는 컬럼만 선택하여 KeyError 방지
        existing_columns = [
            col for col in columns_to_display if col in dataframe.columns
        ]
        filtered_df = dataframe[existing_columns].copy()

        # ✅ [수정] display_names도 필터링된 컬럼에 맞춰 조정
        # columns_to_display와 display_names의 순서가 같다고 가정
        new_display_names = [
            display_names[columns_to_display.index(col)] for col in existing_columns
        ]
        filtered_df.columns = new_display_names

        # --- ✅ 컬럼 너비 자동 추론 로직 시작 ---
        column_styles_str = ""
        if auto_infer_widths:
            try:
                # view_displays.py에 이미 있는 함수를 사용하여 너비 추론
                inferred_widths = infer_column_widths(
                    filtered_df, list(filtered_df.columns)
                )

                # 추론된 너비를 기반으로 CSS 스타일 규칙 생성
                column_style_rules = []
                for i, col_name in enumerate(filtered_df.columns):
                    width = inferred_widths.get(col_name)
                    if width:
                        # CSS의 nth-child는 1부터 시작하므로 i + 1
                        # 🎯 제목 컬럼은 max-width 제한 없이 더 넓게!
                        if col_name == "제목":
                            column_style_rules.append(
                                f".table th:nth-child({i + 1}), "
                                f".table td:nth-child({i + 1}) {{ width: {width}; min-width: {width}; max-width: none !important; word-wrap: break-word; }}"
                            )
                        else:
                            # 다른 컬럼들은 기존과 동일
                            column_style_rules.append(
                                f".table th:nth-child({i + 1}), "
                                f".table td:nth-child({i + 1}) {{ width: {width}; max-width: {width}; }}"
                            )

                # ✅ '제어번호' 컬럼은 고정 폭을 더 넓게 강제 + 줄바꿈 방지
                #    - pandas.to_html 결과에 맞춰 nth-child로 지정
                if "제어번호" in list(filtered_df.columns):
                    ctrl_idx = (
                        list(filtered_df.columns).index("제어번호") + 1
                    )  # 1-based
                    column_style_rules.append(
                        f".table th:nth-child({ctrl_idx}), .table td:nth-child({ctrl_idx}) "
                        "{ min-width: 140px; width: 140px; max-width: 140px; white-space: nowrap; }"
                    )

                column_styles_str = "\n".join(column_style_rules)
            except Exception as e:
                app_instance.log_message(
                    f"경고: 컬럼 너비 자동 조정에 실패했습니다: {e}", level="WARNING"
                )
        # --- ✅ 컬럼 너비 자동 추론 로직 끝 ---

        # HTML 테이블 생성
        html_string = filtered_df.to_html(
            index=False, escape=False, classes="table table-striped table-hover"
        )

        # 툴팁 추가
        html_string = inject_tooltips(html_string)

        # 드롭다운 필터 HTML 미리 생성 (이전과 동일)
        dropdown_filters_html_parts = []
        for i in range(MAX_DROPDOWN_FILTERS):  # ✅ 상수 사용
            options_html = []
            for j, col in enumerate(display_names):
                escaped_col = col.replace("'", "\\'")
                options_html.append(
                    f'<div class="dropdown-option" onclick="selectColumn({i}, {j}, \'{escaped_col}\')">{col}</div>'
                )
            options_html_str = "\n".join(options_html)
            initial_title = (
                display_names[min(i, MAX_DROPDOWN_FILTERS - 1)]
                if i < len(display_names)
                else "컬럼 선택"  # ✅ 상수 사용
            )
            initial_data_column = min(i, len(display_names) - 1) if display_names else 0
            dropdown_filters_html_parts.append(
                f"""
            <div class="filter-dropdown">
                <div class="dropdown-header" onclick="toggleDropdown({i})" id="dropdown{i}">
                    <span class="dropdown-title" id="title{i}">{initial_title}</span>
                    <span class="dropdown-arrow">▼</span>
                </div>
                <div class="dropdown-content" id="content{i}">
                    {options_html_str}
                </div>
                <input type="text" class="column-input" id="input{i}" data-column="{initial_data_column}" placeholder="{initial_title} 필터 입력...">
            </div>
            """
            )
        final_dropdowns_html = "\n".join(dropdown_filters_html_parts)

        # 드롭다운 HTML 템플릿
        dropdown_html = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <style>
                :root[data-theme="dark"] {{
                    --bg-primary: #131722; --bg-secondary: #0e121b; --bg-container: #131722;
                    --text-primary: #cad1d9; --text-secondary: #888; --border-color: #333;
                    --accent-color: #0072b3; --accent-hover: #005a91; --table-hover: #1a4b5c;
                    --table-stripe: #131722; --th-bg: linear-gradient(135deg, #0e111a, #1c2338);
                    --shadow: rgba(0,0,0,0.3);
                }}
                :root[data-theme="light"] {{
                    --bg-primary: #f8f9fa; --bg-secondary: #e9ecef; --bg-container: #ffffff;
                    --text-primary: #212529; --text-secondary: #6c757d; --border-color: #dee2e6;
                    --accent-color: #0072b3; --accent-hover: #005a91; --table-hover: #f1f3f5;
                    --table-stripe: #fafbfc; --th-bg: linear-gradient(135deg, #151a28, #2980b9);
                    --shadow: rgba(0,0,0,0.15);
                }}
                * {{ box-sizing: border-box; }}
                body {{
                    font-family: 'Segoe UI', Arial, sans-serif; background: linear-gradient(270deg, var(--bg-primary) 0%, var(--bg-secondary) 100%);
                    margin: 0; padding: 20px; min-height: 100vh; color: var(--text-primary); transition: all 0.3s ease;
                }}
                .container {{
                    background: var(--bg-container); border-radius: 15px; box-shadow: 0 20px 40px var(--shadow);
                    padding: 30px; margin: 0 auto; max-width: 95%; overflow-x: auto;
                }}
                h1 {{
                    color: var(--text-primary); text-align: center; margin-bottom: 10px; font-size: 1.47em;
                    font-weight: 300; border-bottom: 3px solid var(--accent-color); padding-bottom: 13px;
                }}
                .controls {{
                    background: var(--bg-container); padding: 20px; border-radius: 10px; margin-bottom: 20px;
                    border: 1px solid var(--border-color); box-shadow: 0 2px 8px var(--shadow);
                }}
                .control-row {{ display: flex; gap: 15px; align-items: center; margin-bottom: 15px; flex-wrap: wrap; }}
                .global-search {{
                    flex: 1; min-width: 250px; padding: 10px 12px; border: 2px solid var(--border-color);
                    border-radius: 6px; background: var(--bg-container); color: var(--text-primary);
                    font-size: 14px; transition: border-color 0.2s;
                }}
                .global-search:focus {{ outline: none; border-color: var(--accent-color); box-shadow: 0 0 0 3px rgba(0, 114, 179, 0.1); }}
                .btn {{
                    padding: 10px 16px; background: var(--accent-color); color: white; border: none;
                    border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500;
                    transition: all 0.2s; white-space: nowrap;
                }}
                .btn:hover {{ background: var(--accent-hover); transform: translateY(-1px); }}
                .btn-secondary {{ background: var(--text-secondary); }}
                .btn-secondary:hover {{ background: #777; }}
                .theme-toggle {{ background: linear-gradient(45deg, #f39c12, #e67e22); position: relative; overflow: hidden; }}
                .theme-toggle:hover {{ background: linear-gradient(45deg, #e67e22, #d35400); }}
                .dropdown-filters {{
                    display: none;
                    gap: 15px;
                    margin-top: 15px;
                    padding: 15px 0; /* ✨ 상하 패딩으로 변경하고 좌우는 제거 */
                    border-top: 1px solid var(--border-color);
                    overflow-x: auto; /* ✨ 내용이 넘칠 경우 가로 스크롤 생성 */
                    scrollbar-width: thin; /* ✨ 스크롤바 얇게 (Firefox) */
                }}
                .dropdown-filters.show {{
                    display: flex; /* ✨ grid -> flex 로 변경하여 한 줄로 배치 */
                    flex-wrap: nowrap; /* ✨ 줄바꿈 방지 */
                }}
                .filter-dropdown {{
                    position: relative;
                    flex: 0 0 150px; /* ✨ 각 필터의 너비를 150px로 고정 (flex-grow, flex-shrink, flex-basis) */
                }}
                .dropdown-header {{
                    display: flex; align-items: center; padding: 8px 12px; background: var(--bg-container);
                    border: 2px solid var(--border-color); border-radius: 6px; cursor: pointer;
                    transition: all 0.2s; user-select: none; min-height: 40px;
                }}
                .dropdown-header:hover, .dropdown-header.active {{ border-color: var(--accent-color); }}
                .dropdown-title {{ flex: 1; font-size: 13px; font-weight: 500; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; }}
                .dropdown-arrow {{ margin-left: 8px; transition: transform 0.2s; }}
                .dropdown-header.active .dropdown-arrow {{ transform: rotate(180deg); }}
                .dropdown-content {{
                    position: absolute; top: 105%; left: 0; right: 0; background: var(--bg-container);
                    border: 1px solid var(--border-color); border-radius: 6px; z-index: 1000;
                    max-height: 250px; overflow-y: auto; display: none; box-shadow: 0 4px 12px var(--shadow);
                }}
                .dropdown-content.show {{ display: block; }}
                .dropdown-option {{ padding: 8px 12px; cursor: pointer; transition: background 0.2s; font-size: 13px; border-bottom: 1px solid var(--border-color); }}
                .dropdown-option:last-child {{ border-bottom: none; }}
                .dropdown-option:hover {{ background: var(--table-hover); }}
                .dropdown-option.selected {{ background: var(--accent-color); color: white; }}
                .column-input {{ width: 100%; padding: 6px 8px; margin-top: 8px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-container); color: var(--text-primary); font-size: 12px; }}
                .column-input:focus {{ outline: none; border-color: var(--accent-color); }}
                .table {{
                    table-layout: auto;
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                    font-size: 14px;
                    min-width: 100%;
                }}
                .table th {{
                    background: var(--th-bg); color: #ffffff; font-weight: 600; padding: 15px 12px;
                    text-align: left; border: none; position: sticky; top: 0; z-index: 10;
                    text-shadow: 0 1px 1px rgba(0,0,0,0.3); cursor: pointer; user-select: none;
                    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
                }}
                .table th:hover {{ filter: brightness(1.1); }}
                .table td {{
                    padding: 12px; border-bottom: 1px solid var(--border-color); transition: all 0.3s ease;
                    /* max-width는 개별 스타일로 제어하므로 여기서는 제거하거나 유지해도 괜찮습니다. */
                    /* max-width: 300px; */
                    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
                }}
                .table tbody tr:hover {{ background-color: var(--table-hover); }}
                .table tbody tr:nth-child(even) {{ background-color: var(--table-stripe); }}
                .table a {{ color: var(--accent-color); text-decoration: none; font-weight: 500; transition: color 0.3s ease; }}
                .table a:hover {{ color: var(--accent-hover); text-decoration: underline; }}
                .stats {{ text-align: center; margin-top: 20px; padding: 15px; background: var(--bg-container); border-radius: 8px; border: 1px solid var(--border-color); color: var(--text-secondary); }}
                .no-results {{ text-align: center; padding: 40px; color: var(--text-secondary); font-style: italic; font-size: 16px; }}
                .sort-indicator {{ margin-left: 5px; font-size: 12px; }}

                /* ✨ --- 스크롤바 스타일 수정 --- ✨ */
                /* 모든 스크롤바에 대한 기본 스타일 */
                ::-webkit-scrollbar {{
                    width: 10px; /* 너비 살짝 증가 */
                    height: 10px; /* 높이 살짝 증가 */
                }}
                /* 스크롤바 트랙(배경) */
                ::-webkit-scrollbar-track {{
                    background: var(--bg-secondary); /* 다크/라이트 테마 배경색 적용 */
                    border-radius: 5px;
                }}
                /* 스크롤바 핸들(막대) */
                ::-webkit-scrollbar-thumb {{
                    background-color: var(--accent-color); /* 다크/라이트 테마 강조색 적용 */
                    border-radius: 5px;
                    border: 2px solid var(--bg-secondary); /* 트랙과 동일한 색상으로 테두리 추가 */
                }}
                /* ✨ --- [최종] 모든 스크롤바에 테마를 강제 적용하는 통합 스타일 --- ✨ */
                ::-webkit-scrollbar {{
                    width: 10px !important;
                    height: 10px !important;
                }}
                ::-webkit-scrollbar-track {{
                    background: var(--bg-secondary) !important;
                    border-radius: 5px !important;
                }}
                ::-webkit-scrollbar-thumb {{
                    background-color: var(--accent-color) !important;
                    border-radius: 5px !important;
                    border: 2px solid var(--bg-secondary) !important;
                }}
                ::-webkit-scrollbar-thumb:hover {{
                    background-color: var(--accent-hover) !important;
                }}

                /* --- 스크롤바 스타일 수정 끝 --- */

                /* --- ✅ 여기에 동적으로 생성된 컬럼 너비 스타일이 삽입됩니다 --- */
                {column_styles_str}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>{title}</h1>
                <div class="controls">
                    <div class="control-row">
                        <input type="text" id="globalSearch" class="global-search" placeholder="전체 검색 (모든 컬럼에서 검색)">
                        <button class="btn btn-secondary" onclick="toggleDropdownFilters()" id="filterToggle">드롭다운 필터</button>
                        <button class="btn theme-toggle" onclick="toggleTheme()" id="themeToggle">🌙 다크</button>
                        <button class="btn" onclick="clearAllFilters()">초기화</button>
                        <button class="btn" onclick="exportToCSV()">CSV 저장</button>
                    </div>
                    <div class="dropdown-filters show" id="dropdownFilters">
                        {final_dropdowns_html}
                    </div>
                </div>
                <div class="table-wrapper">
                    {html_string}
                    <div id="noResults" class="no-results" style="display: none;">필터 조건에 맞는 항목이 없습니다.</div>
                </div>
                <div class="stats">
                    <strong>표시된 항목:</strong> <span id="visibleRows">{len(filtered_df)}</span> / <span id="totalRows">{len(filtered_df)}</span>
                    <span style="margin-left: 20px;"><strong>활성 필터:</strong> <span id="activeFilters">0</span>개</span>
                    <span style="margin-left: 20px;"><strong>테마:</strong> <span id="currentTheme">다크</span></span>
                </div>
            </div>
            <script>
                // ✅ Python 상수를 JavaScript로 주입
                const MAX_DROPDOWN_FILTERS = {MAX_DROPDOWN_FILTERS};
                let originalRows = [];
                let currentSort = {{ column: -1, ascending: true }};
                let columnFilters = Array(MAX_DROPDOWN_FILTERS).fill('');  // ✅ 상수 사용

                document.addEventListener('DOMContentLoaded', function() {{
                    document.documentElement.setAttribute('data-theme', 'dark');
                    const table = document.querySelector('.table');
                    if (!table) return;
                    const tbody = table.querySelector('tbody');
                    if (!tbody) return;
                    originalRows = Array.from(tbody.querySelectorAll('tr'));

                    document.getElementById('globalSearch').addEventListener('input', performFilter);
                    for(let i = 0; i < MAX_DROPDOWN_FILTERS; i++) {{  // ✅ 상수 사용
                        document.getElementById(`input${{i}}`).addEventListener('input', () => {{
                            columnFilters[i] = document.getElementById(`input${{i}}`).value;
                            performFilter();
                        }});
                    }}
                    table.querySelectorAll('th').forEach((header, index) => {{
                        header.addEventListener('click', () => sortTable(index));
                    }});

                    const linkColumns = {repr(link_column_name) if link_column_name else 'null'};
                    console.log('linkColumns 값:', linkColumns); // ← 디버깅 추가
                    if (linkColumns && linkColumns !== 'null') processLinkColumns(linkColumns);

                    document.addEventListener('click', (e) => {{
                        if (!e.target.closest('.filter-dropdown')) closeAllDropdowns();
                    }});
                }});

                function toggleTheme() {{
                    const root = document.documentElement;
                    const newTheme = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
                    root.setAttribute('data-theme', newTheme);
                    document.getElementById('themeToggle').textContent = newTheme === 'dark' ? '🌙 다크' : '☀️ 라이트';
                    document.getElementById('currentTheme').textContent = newTheme === 'dark' ? '다크' : '라이트';
                }}

                function toggleDropdown(index) {{
                    const header = document.getElementById(`dropdown${{index}}`);
                    const content = document.getElementById(`content${{index}}`);
                    const wasActive = header.classList.contains('active');

                    closeAllDropdowns(); // 먼저 모든 드롭다운을 닫습니다.

                    if (!wasActive) {{
                        // 드롭다운을 열 위치를 계산합니다.
                        const rect = header.getBoundingClientRect();

                        // 메뉴를 body의 직속 자식으로 이동시켜 overflow의 영향을 받지 않게 합니다.
                        document.body.appendChild(content);

                        // 계산된 위치에 메뉴를 고정시킵니다.
                        content.style.position = 'fixed';
                        content.style.top = `${{rect.bottom + 2}}px`; // 헤더 바로 아래
                        content.style.left = `${{rect.left}}px`;
                        content.style.width = `${{rect.width}}px`;

                        content.classList.add('show');
                        header.classList.add('active');
                    }}
                }}

                function closeAllDropdowns() {{
                    // body에 직접 추가된 모든 드롭다운 메뉴를 찾습니다.
                    const openContents = document.querySelectorAll('body > .dropdown-content');

                    openContents.forEach(content => {{
                        // 메뉴를 원래의 부모(.filter-dropdown)에게 돌려줍니다.
                        const index = content.id.replace('content', '');
                        const originalParent = document.querySelector(`#dropdown${{index}}`).parentElement;
                        if (originalParent) {{
                            originalParent.appendChild(content);
                        }}

                        // 동적으로 추가했던 스타일을 제거합니다.
                        content.style.position = '';
                        content.style.top = '';
                        content.style.left = '';
                        content.style.width = '';
                        content.classList.remove('show');
                    }});

                    // 모든 헤더의 'active' 상태를 제거합니다.
                    for(let i = 0; i < MAX_DROPDOWN_FILTERS; i++) {{
                        const header = document.getElementById(`dropdown${{i}}`);
                        if(header) header.classList.remove('active');
                    }}
                }}

                function selectColumn(dropdownIndex, columnIndex, columnName) {{
                    document.getElementById(`title${{dropdownIndex}}`).textContent = columnName;
                    const input = document.getElementById(`input${{dropdownIndex}}`);
                    input.setAttribute('data-column', columnIndex);
                    input.placeholder = `${{columnName}} 필터 입력...`;
                    closeAllDropdowns();
                    performFilter();
                }}

                function toggleDropdownFilters() {{
                    const filters = document.getElementById('dropdownFilters');
                    filters.classList.toggle('show');
                    document.getElementById('filterToggle').textContent = filters.classList.contains('show') ? '필터 숨기기' : '드롭다운 필터';
                }}

                function performFilter() {{
                    const globalSearch = document.getElementById('globalSearch').value.toLowerCase().trim();
                    let activeFilterCount = globalSearch ? 1 : 0;

                    const currentColumnFilters = Array({len(display_names)}).fill('');
                    for(let i = 0; i < MAX_DROPDOWN_FILTERS; i++) {{  // ✅ 상수 사용
                        const input = document.getElementById(`input${{i}}`);
                        const colIndex = parseInt(input.getAttribute('data-column'));
                        const filterValue = input.value.toLowerCase().trim();
                        if(filterValue) {{
                            currentColumnFilters[colIndex] = filterValue;
                            if(!activeFilterCount || i > 0) activeFilterCount++;
                        }}
                    }}

                    let visibleCount = 0;
                    originalRows.forEach(row => {{
                        const cells = Array.from(row.cells).map(cell => cell.textContent.toLowerCase());
                        let show = true;

                        if (globalSearch && !cells.some(cell => cell.includes(globalSearch))) {{
                            show = false;
                        }}

                        if(show) {{
                            for(let i=0; i < currentColumnFilters.length; i++) {{
                                if(currentColumnFilters[i] && cells.length > i && !cells[i].includes(currentColumnFilters[i])) {{
                                    show = false;
                                    break;
                                }}
                            }}
                        }}

                        row.style.display = show ? '' : 'none';
                        if(show) visibleCount++;
                    }});

                    document.getElementById('visibleRows').textContent = visibleCount;
                    document.getElementById('activeFilters').textContent = activeFilterCount;
                    document.getElementById('noResults').style.display = visibleCount === 0 && activeFilterCount > 0 ? 'block' : 'none';
                    document.querySelector('.table').style.display = visibleCount > 0 || activeFilterCount === 0 ? 'table' : 'none';
                }}

                function clearAllFilters() {{
                    document.getElementById('globalSearch').value = '';
                    for(let i = 0; i < MAX_DROPDOWN_FILTERS; i++) document.getElementById(`input${{i}}`).value = '';  // ✅ 상수 사용
                    performFilter();
                }}

                function sortTable(columnIndex) {{
                    const tbody = document.querySelector('.table tbody');
                    currentSort.ascending = currentSort.column === columnIndex ? !currentSort.ascending : true;
                    currentSort.column = columnIndex;

                    document.querySelectorAll('.table th .sort-indicator').forEach(ind => ind.remove());
                    const indicator = document.createElement('span');
                    indicator.className = 'sort-indicator';
                    indicator.textContent = currentSort.ascending ? ' ▲' : ' ▼';
                    document.querySelector(`.table th:nth-child(${{columnIndex + 1}})`).appendChild(indicator);

                    const rowsToSort = Array.from(originalRows);
                    rowsToSort.sort((a, b) => {{
                        const aVal = a.cells[columnIndex].textContent.trim();
                        const bVal = b.cells[columnIndex].textContent.trim();
                        const aNum = parseFloat(aVal.replace(/,/g, ''));
                        const bNum = parseFloat(bVal.replace(/,/g, ''));

                        let comparison = 0;
                        if (!isNaN(aNum) && !isNaN(bNum)) {{
                            comparison = aNum - bNum;
                        }} else {{
                            comparison = aVal.localeCompare(bVal, 'ko-KR', {{numeric: true}});
                        }}
                        return currentSort.ascending ? comparison : -comparison;
                    }});
                    rowsToSort.forEach(row => tbody.appendChild(row));
                }}

                function exportToCSV() {{
                    let csvContent = [];
                    const headers = Array.from(document.querySelectorAll('.table th')).map(th => '"' + th.textContent.replace(/["▲▼\\s]/g, '').trim() + '"');
                    csvContent.push(headers.join(','));

                    originalRows.forEach(row => {{
                        if (row.style.display !== 'none') {{
                            const rowData = Array.from(row.cells).map(cell => '"' + cell.textContent.replace(/"/g, '""') + '"');
                            csvContent.push(rowData.join(','));
                        }}
                    }});

                    const blob = new Blob(["\\uFEFF" + csvContent.join('\\n')], {{ type: 'text/csv;charset=utf-8;' }});
                    const link = document.createElement('a');
                    link.href = URL.createObjectURL(blob);
                    link.download = "{title}".replace(/[^a-zA-Z0-9]/g, '_') + '_export.csv';
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                }}

                    function processLinkColumns(linkColumns) {{
                        console.log('processLinkColumns 호출됨:', linkColumns);
                        const table = document.querySelector('.table');  // ← table 변수 정의 추가!
                        if (table && linkColumns) {{
                            const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());
                            const linkColumnIndices = [];

                            if (Array.isArray(linkColumns)) {{
                                linkColumns.forEach(linkCol => {{
                                    const index = headers.indexOf(linkCol);
                                    if (index !== -1) linkColumnIndices.push(index);
                                }});
                            }} else {{
                                const index = headers.indexOf(linkColumns);
                                if (index !== -1) linkColumnIndices.push(index);
                            }}

                            console.log('linkColumnIndices:', linkColumnIndices);

                            // 링크 컬럼의 셀들을 클릭 가능하게 만들기
                            table.querySelectorAll('tbody tr').forEach(row => {{
                                linkColumnIndices.forEach(colIndex => {{
                                    const cell = row.cells[colIndex];
                                    if (cell && cell.textContent.trim()) {{
                                        const url = cell.textContent.trim();
                                        if (url.startsWith('http')) {{
                                            cell.innerHTML = '<a href="' + url + '" target="_blank">' + url + '</a>';
                                        }}
                                    }}
                                }});
                            }});
                        }}
                    }}
            </script>
        </body>
        </html>
        """

        # 임시 파일 생성 및 열기
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(dropdown_html)
            temp_path = f.name

        webbrowser.open("file://" + os.path.abspath(temp_path))

        app_instance.log_message(
            f"정보: 드롭다운 HTML 뷰어로 {len(filtered_df)}개 행 표시됨 (자동 너비 조절 적용)",
            level="INFO",
        )

    except Exception as e:
        app_instance.log_message(
            f"오류: 드롭다운 HTML 뷰어 생성 실패: {e}", level="ERROR"
        )
        app_instance.show_messagebox(
            "오류", f"HTML 뷰어 생성에 실패했습니다: {e}", "error"
        )


def adjust_qtableview_columns(
    table_view,
    current_dataframe=None,
    column_keys=None,
    column_headers=None,
    min_width=60,
    max_width=400,
):
    """✅ [최종 수정] 자동 조정 후에도 사용자의 수동 조정을 완벽하게 보장합니다."""
    if not table_view or not table_view.model():
        return

    try:
        model = table_view.model()
        header = table_view.horizontalHeader()
        column_count = model.columnCount() if model else 0

        # 1. Qt의 내용 기반 리사이즈 기능을 실행합니다.
        table_view.resizeColumnsToContents()

        # 2. 모든 컬럼을 순회하며 최종 상태를 설정합니다.
        for i in range(column_count):
            current_width = header.sectionSize(i)
            final_width = current_width

            # 최소/최대 너비 제한 적용
            if final_width < min_width:
                final_width = min_width
            elif final_width > max_width:
                final_width = max_width

            # -------------------
            # ✅ [핵심 수정]
            # 너비를 먼저 설정한 후, 모든 컬럼의 모드를 예외 없이 'Interactive'로 설정합니다.
            # 이렇게 하면 Qt가 렌더링 상태를 갱신하고 수동 조작을 완벽하게 받아들입니다.
            header.resizeSection(i, final_width)
            header.setSectionResizeMode(i, QHeaderView.Interactive)
            # -------------------

    except Exception as e:
        print(f"❌ QTableView 컬럼 조정 실패: {e}")
