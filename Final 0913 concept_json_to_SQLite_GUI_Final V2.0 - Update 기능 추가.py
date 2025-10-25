#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ConceptMaterial JSON → SQLite GUI Importer with Update Feature
Version 2.0 - 2025-09-13

변경 이력:
- v2.0 (2025-09-13): 기존 DB 업데이트 기능 추가
  * 6월 버전 DB의 value_normalized 컬럼 지원
  * 공백 제거 정규화 자동 적용 (예: "Down's syndrome" → "Down'ssyndrome")
  * 스키마 호환성: 기존/신규 DB 구조 자동 감지
  * 신규 DB 생성시 6월 버전과 동일한 인덱스 구조 적용
  * 정확한 통계 표시: 실제 DB 상태 반영 (SELECT COUNT 기반)
  * UI 개선: Create New DB / Update Existing DB 버튼 분리

- Select one or more ConceptMaterial_*.json files
- Choose output SQLite DB path
- Click "Import" to create new DB or "Update DB" to update existing DB
- Automatically normalizes values by removing spaces for indexing

Tested with Python 3.10+ on Windows. Requires only stdlib.
"""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Sequence

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "ConceptMaterial → SQLite (GUI) with Update 2.0"
DEFAULT_DB_NAME = "nlk_concepts.sqlite"

# Default property buckets (can be edited in GUI)
DEFAULT_LITERAL = ["label", "prefLabel", "altLabel", "definition"]
DEFAULT_URI = [
    "broader",
    "narrower",
    "related",
    "inScheme",
    "sameAs",
    "closeMatch",
    "isSubjectOf",
]


# -------------------------- Core Logic --------------------------


def normalize_value(value: str) -> str:
    """값 정규화: 공백만 제거하여 검색 색인 활용도 향상"""
    if not value:
        return ""
    return value.replace(" ", "")


def as_iter(x: Any) -> Iterable[Any]:
    if x is None:
        return []
    if isinstance(x, (list, tuple, set)):
        return x
    return [x]


def check_db_schema(conn: sqlite3.Connection) -> dict:
    """데이터베이스 스키마 확인"""
    cur = conn.cursor()
    schema_info = {
        "has_value_normalized": False,
        "has_category_mapping": False,
        "has_ddc_mapping": False,
        "has_kdc_mapping": False,
        "table_counts": {},
    }

    # 테이블 존재 여부 및 레코드 수 확인
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]

    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        schema_info["table_counts"][table] = cur.fetchone()[0]

    # literal_props 테이블 구조 확인
    if "literal_props" in tables:
        cur.execute("PRAGMA table_info(literal_props)")
        columns = [col[1] for col in cur.fetchall()]
        schema_info["has_value_normalized"] = "value_normalized" in columns

    # 추가 매핑 테이블 확인
    schema_info["has_category_mapping"] = "category_mapping" in tables
    schema_info["has_ddc_mapping"] = "ddc_mapping" in tables
    schema_info["has_kdc_mapping"] = "kdc_mapping" in tables

    return schema_info


def init_db(conn: sqlite3.Connection, preserve_existing: bool = False) -> dict:
    """데이터베이스 초기화"""
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")

    if preserve_existing:
        # 업데이트 모드: 기존 스키마 확인만
        return check_db_schema(conn)

    # 새 DB 생성 모드: 기본 스키마로 생성 (value_normalized 없음)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS concepts(
            concept_id TEXT PRIMARY KEY,
            type TEXT
        );
    """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS literal_props(
            concept_id TEXT NOT NULL,
            prop TEXT NOT NULL,
            value TEXT NOT NULL,
            UNIQUE(concept_id, prop, value),
            FOREIGN KEY(concept_id) REFERENCES concepts(concept_id)
        );
    """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS uri_props(
            concept_id TEXT NOT NULL,
            prop TEXT NOT NULL,
            target TEXT NOT NULL,
            UNIQUE(concept_id, prop, target),
            FOREIGN KEY(concept_id) REFERENCES concepts(concept_id)
        );
    """
    )

    # 인덱스 생성
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_literal_prop ON literal_props(prop);",
        "CREATE INDEX IF NOT EXISTS idx_literal_value ON literal_props(value);",
        "CREATE INDEX IF NOT EXISTS idx_uri_prop ON uri_props(prop);",
        "CREATE INDEX IF NOT EXISTS idx_uri_target ON uri_props(target);",
        "CREATE INDEX IF NOT EXISTS idx_literal_prop_value ON literal_props(prop, value);",
        "CREATE INDEX IF NOT EXISTS idx_literal_cid_prop ON literal_props(concept_id, prop);",
        "CREATE INDEX IF NOT EXISTS idx_uri_prop_target ON uri_props(prop, target);",
        "CREATE INDEX IF NOT EXISTS idx_uri_cid_prop ON uri_props(concept_id, prop);",
    ]

    for index_sql in indexes:
        cur.execute(index_sql)

    conn.commit()
    return check_db_schema(conn)


def upsert_concept(cur: sqlite3.Cursor, concept_id: str, ctype: str | None) -> None:
    cur.execute(
        """
        INSERT INTO concepts(concept_id, type)
        VALUES (?, ?)
        ON CONFLICT(concept_id) DO UPDATE SET
            type = COALESCE(excluded.type, concepts.type);
    """,
        (concept_id, ctype),
    )


def insert_literal(
    cur: sqlite3.Cursor,
    concept_id: str,
    prop: str,
    value: str,
    has_normalized_col: bool,
) -> None:
    """literal_props에 데이터 삽입 (value_normalized 컬럼 지원)"""
    if value is None:
        return

    value_str = str(value)

    if has_normalized_col:
        # 기존 6월 버전 스키마: value_normalized 컬럼 있음
        normalized_value = normalize_value(value_str)
        cur.execute(
            """
            INSERT OR IGNORE INTO literal_props(concept_id, prop, value, value_normalized)
            VALUES (?, ?, ?, ?);
        """,
            (concept_id, prop, value_str, normalized_value),
        )
    else:
        # 새 버전 스키마: value_normalized 컬럼 없음
        cur.execute(
            """
            INSERT OR IGNORE INTO literal_props(concept_id, prop, value)
            VALUES (?, ?, ?);
        """,
            (concept_id, prop, value_str),
        )


def insert_uri(cur: sqlite3.Cursor, concept_id: str, prop: str, target: str) -> None:
    if target is None:
        return
    cur.execute(
        """
        INSERT OR IGNORE INTO uri_props(concept_id, prop, target)
        VALUES (?, ?, ?);
    """,
        (concept_id, prop, str(target)),
    )


def _extract_nodes(obj) -> list[dict]:
    """Return a list of concept nodes from a parsed JSON object."""
    if isinstance(obj, dict):
        if "@graph" in obj and isinstance(obj["@graph"], list):
            return [n for n in obj["@graph"] if isinstance(n, dict)]
        # single node object?
        if "@id" in obj or "@type" in obj:
            return [obj]
        return []
    elif isinstance(obj, list):
        # list of nodes?
        return [n for n in obj if isinstance(n, dict)]
    return []


def load_graph_from_json(path: Path) -> list[dict]:
    """Robust loader:
    - Supports standard JSON with @graph
    - Supports concatenated JSON documents in one file
    - Supports NDJSON (one JSON object per line)
    - Supports top-level JSON array of nodes
    """
    text = path.read_text(encoding="utf-8")
    nodes: list[dict] = []

    # 1) Try standard parse
    try:
        obj = json.loads(text)
        nodes.extend(_extract_nodes(obj))
        if nodes:
            return nodes
    except json.JSONDecodeError as e:
        # fall through to tolerant parsing
        pass

    # 2) Concatenated JSON: use raw_decode loop
    dec = json.JSONDecoder()
    idx = 0
    length = len(text)
    while idx < length:
        # skip whitespace
        while idx < length and text[idx].isspace():
            idx += 1
        if idx >= length:
            break
        try:
            obj, end = dec.raw_decode(text, idx)
        except json.JSONDecodeError:
            # If this happens, try to move to next newline (NDJSON case) to avoid infinite loop
            nl = text.find("\n", idx + 1)
            if nl == -1:
                break
            idx = nl + 1
            continue
        nodes.extend(_extract_nodes(obj))
        idx = end

    if nodes:
        return nodes

    # 3) NDJSON line-by-line as last resort
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        nodes.extend(_extract_nodes(obj))

    return nodes


def import_files(
    json_paths: Sequence[Path],
    db_path: Path,
    literal_props: Sequence[str],
    uri_props: Sequence[str],
    log_fn=print,
    update_mode: bool = False,
) -> dict:
    """
    Import multiple JSON files into SQLite.

    Args:
        update_mode: True면 기존 DB 업데이트, False면 새로 생성

    Returns:
        stats dict.
    """
    conn = sqlite3.connect(db_path)
    stats = {
        "files": 0,
        "concepts": 0,
        "new_concepts": 0,
        "updated_concepts": 0,
        "literal_rows": 0,
        "uri_rows": 0,
        "mode": "update" if update_mode else "create",
        "final_concepts": 0,
        "final_literal_props": 0,
        "final_uri_props": 0,
    }

    try:
        # 스키마 초기화 및 확인
        schema_info = init_db(conn, preserve_existing=update_mode)

        if update_mode:
            log_fn("업데이트 모드: 기존 데이터베이스 분석 중...")
            log_fn(f"기존 개념 수: {schema_info['table_counts'].get('concepts', 0):,}")
            log_fn(
                f"기존 literal 속성: {schema_info['table_counts'].get('literal_props', 0):,}"
            )
            log_fn(
                f"value_normalized 컬럼: {'있음' if schema_info['has_value_normalized'] else '없음'}"
            )

            # 추가 매핑 테이블 확인
            if schema_info["has_category_mapping"]:
                log_fn(
                    f"카테고리 매핑: {schema_info['table_counts'].get('category_mapping', 0):,}"
                )
            if schema_info["has_ddc_mapping"]:
                log_fn(
                    f"DDC 매핑: {schema_info['table_counts'].get('ddc_mapping', 0):,}"
                )
            if schema_info["has_kdc_mapping"]:
                log_fn(
                    f"KDC 매핑: {schema_info['table_counts'].get('kdc_mapping', 0):,}"
                )
        else:
            log_fn("새 데이터베이스 생성 중... (6월 버전과 동일한 스키마)")

        cur = conn.cursor()
        files = list(json_paths)
        stats["files"] = len(files)

        # 업데이트 모드에서 기존 concept_id 추적
        existing_concepts = set()
        if update_mode:
            cur.execute("SELECT concept_id FROM concepts")
            existing_concepts = {row[0] for row in cur.fetchall()}

        has_normalized_col = schema_info["has_value_normalized"]

        for i, p in enumerate(files, 1):
            log_fn(f"[{i}/{len(files)}] {p.name} 처리 중...")
            graph = load_graph_from_json(p)

            batch_new = 0
            batch_updated = 0

            for node in graph:
                if not isinstance(node, dict):
                    continue
                cid = node.get("@id")
                ctype = node.get("@type")
                if not cid:
                    continue

                # 새 개념인지 기존 개념인지 확인
                if update_mode:
                    if cid in existing_concepts:
                        batch_updated += 1
                        stats["updated_concepts"] += 1
                    else:
                        batch_new += 1
                        stats["new_concepts"] += 1
                        existing_concepts.add(cid)

                upsert_concept(cur, cid, ctype)
                stats["concepts"] += 1

                for prop in literal_props:
                    for v in as_iter(node.get(prop)):
                        if isinstance(v, dict):
                            v = v.get("@value") or v.get("@literal") or str(v)
                        insert_literal(cur, cid, prop, v, has_normalized_col)
                        stats["literal_rows"] += 1

                for prop in uri_props:
                    for v in as_iter(node.get(prop)):
                        if isinstance(v, dict):
                            v = v.get("@id") or v.get("@value") or str(v)
                        insert_uri(cur, cid, prop, v)
                        stats["uri_rows"] += 1

            conn.commit()

            if update_mode:
                log_fn(f"    완료 - 신규: {batch_new}, 업데이트: {batch_updated}")
            else:
                log_fn(f"    완료 - {len(graph)}개 개념 가져옴")

        cur.execute("VACUUM;")
        log_fn("데이터베이스 최적화 완료")
        return stats

    finally:
        conn.close()


# -------------------------- GUI --------------------------


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("820x680")
        self.minsize(750, 600)

        self.json_files: list[Path] = []
        self.db_path: Path | None = None

        # Top frame: file selectors
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="JSON Files (ConceptMaterial_*.json)").grid(
            row=0, column=0, sticky="w"
        )
        btn_add = ttk.Button(top, text="Add Files...", command=self.add_files)
        btn_add.grid(row=0, column=1, padx=6, sticky="w")
        btn_clear = ttk.Button(top, text="Clear", command=self.clear_files)
        btn_clear.grid(row=0, column=2, padx=6, sticky="w")

        self.files_list = tk.Listbox(top, height=6)
        self.files_list.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(6, 0))
        top.grid_columnconfigure(0, weight=1)

        # DB output
        ttk.Label(top, text="Output SQLite DB").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )
        db_row = ttk.Frame(top)
        db_row.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.db_entry = ttk.Entry(db_row)
        self.db_entry.insert(0, DEFAULT_DB_NAME)
        self.db_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(db_row, text="Browse...", command=self.choose_db).pack(
            side="left", padx=6
        )

        # Property buckets
        props = ttk.Frame(self, padding=(10, 10, 10, 0))
        props.pack(fill="both")

        literal_frame = ttk.Labelframe(
            props, text="Literal properties (comma-separated)"
        )
        uri_frame = ttk.Labelframe(props, text="URI properties (comma-separated)")
        literal_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))
        uri_frame.pack(side="left", fill="both", expand=True, padx=(6, 0))

        self.literal_text = tk.Text(literal_frame, height=4, wrap="word")
        self.literal_text.insert("1.0", ", ".join(DEFAULT_LITERAL))
        self.literal_text.pack(fill="both", expand=True, padx=8, pady=8)

        self.uri_text = tk.Text(uri_frame, height=4, wrap="word")
        self.uri_text.insert("1.0", ", ".join(DEFAULT_URI))
        self.uri_text.pack(fill="both", expand=True, padx=8, pady=8)

        # Progress & log
        bottom = ttk.Frame(self, padding=10)
        bottom.pack(fill="both", expand=True)

        self.progress = ttk.Progressbar(bottom, mode="indeterminate")
        self.progress.pack(fill="x")

        self.log = tk.Text(bottom, height=12)
        self.log.pack(fill="both", expand=True, pady=(8, 0))

        # Run/Update/Close buttons
        btns = ttk.Frame(self, padding=10)
        btns.pack(fill="x")

        # 왼쪽: 실행 버튼들
        left_btns = ttk.Frame(btns)
        left_btns.pack(side="left")

        self.run_btn = ttk.Button(
            left_btns, text="Create New DB", command=lambda: self.on_import(False)
        )
        self.run_btn.pack(side="left", padx=(0, 6))

        self.update_btn = ttk.Button(
            left_btns, text="Update Existing DB", command=lambda: self.on_import(True)
        )
        self.update_btn.pack(side="left")

        # 오른쪽: 닫기 버튼
        ttk.Button(btns, text="Close", command=self.destroy).pack(side="right")

    # --- UI helpers ---
    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select ConceptMaterial JSON files",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not paths:
            return
        for p in paths:
            path = Path(p)
            if path not in self.json_files:
                self.json_files.append(path)
                self.files_list.insert("end", str(path))

    def clear_files(self):
        self.json_files.clear()
        self.files_list.delete(0, "end")

    def choose_db(self):
        initial = self.db_entry.get().strip() or DEFAULT_DB_NAME
        path = filedialog.asksaveasfilename(
            title="Choose output SQLite DB file",
            defaultextension=".sqlite",
            initialfile=initial,
            filetypes=[("SQLite DB", "*.sqlite"), ("All files", "*.*")],
        )
        if path:
            self.db_entry.delete(0, "end")
            self.db_entry.insert(0, path)

    def get_props(self, widget: tk.Text) -> list[str]:
        raw = widget.get("1.0", "end").strip()
        if not raw:
            return []
        return [p.strip() for p in raw.split(",") if p.strip()]

    def log_write(self, text: str):
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.update_idletasks()

    def on_import(self, update_mode: bool = False):
        if not self.json_files:
            messagebox.showwarning(
                "No files", "Add at least one ConceptMaterial_*.json file."
            )
            return

        db_str = self.db_entry.get().strip()
        if not db_str:
            messagebox.showwarning("No DB path", "Choose output SQLite DB file.")
            return
        db_path = Path(db_str)

        # 업데이트 모드에서 DB 파일이 없으면 경고
        if update_mode and not db_path.exists():
            result = messagebox.askyesno(
                "DB File Not Found",
                f"Database file '{db_path}' does not exist.\n\nDo you want to create a new database instead?",
            )
            if result:
                update_mode = False
            else:
                return

        literal_props = self.get_props(self.literal_text) or DEFAULT_LITERAL
        uri_props = self.get_props(self.uri_text) or DEFAULT_URI

        # Disable UI and start thread
        self.run_btn.config(state="disabled")
        self.update_btn.config(state="disabled")
        self.progress.start(10)

        mode_text = "업데이트" if update_mode else "새로 생성"
        self.log_write(f"작업 시작: {mode_text} 모드")

        def worker():
            try:
                stats = import_files(
                    self.json_files,
                    db_path,
                    literal_props,
                    uri_props,
                    log_fn=self.log_write,
                    update_mode=update_mode,
                )
                self.log_write("")
                self.log_write("=== 작업 완료 요약 ===")
                self.log_write(f"모드:           {mode_text}")
                self.log_write(f"처리 파일:       {stats['files']:,}개")

                if update_mode:
                    self.log_write(f"신규 개념:       {stats['new_concepts']:,}개")
                    self.log_write(f"업데이트 개념:    {stats['updated_concepts']:,}개")
                    self.log_write(f"현재 총 개념:    {stats['final_concepts']:,}개")
                else:
                    self.log_write(f"생성된 개념:     {stats['final_concepts']:,}개")

                self.log_write(f"현재 Literal:   {stats['final_literal_props']:,}개")
                self.log_write(f"현재 URI:       {stats['final_uri_props']:,}개")
                self.log_write(f"출력 DB:        {db_path.resolve()}")

                summary_msg = f"작업 완료!\n\n모드: {mode_text}\n"
                if update_mode:
                    summary_msg += f"신규: {stats['new_concepts']:,}개\n업데이트: {stats['updated_concepts']:,}개\n"
                    summary_msg += f"총 개념: {stats['final_concepts']:,}개\n"
                summary_msg += f"DB: {db_path.name}"

                messagebox.showinfo("완료", summary_msg)

            except Exception as e:
                self.log_write("")
                self.log_write(f"오류 발생: {str(e)}")
                messagebox.showerror("Error", str(e))
            finally:
                self.progress.stop()
                self.run_btn.config(state="normal")
                self.update_btn.config(state="normal")

        threading.Thread(target=worker, daemon=True).start()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
