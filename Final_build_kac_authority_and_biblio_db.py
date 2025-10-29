# -*- coding: utf-8 -*-
"""
KAC/KAB Authority & NLK Biblio — Batch JSON → SQLite Builder (PySide6)
Version: 2.1.0 (2025-10-26)

▶ 목적
- NLK 전거 JSON의 **KAC(개인)·KAB(기관)** 레코드에서 `create` 배열을 빠짐없이 추출해
  `authority_create(kac_id_full, identifier)`로 저장(핵심 조인 키).
- Biblio(JSON)도 함께 SQLite에 적재하여 `identifier`로 고속 조인.
- 2개월 주기 스냅샷을 위해 **안전/반복 가능한(idempotent)** 빌드.

▶ 특징
- 대용량 스트리밍 파서: JSONL / 배열 / { "@graph": [...] } / **연속(concatenated) JSON** 모두 처리
- GUI 배치: 다수 파일 + 폴더(패턴, 재귀) → 한 DB로 연속 처리
- 스키마: 정규화 + 보조 테이블 복합 PK + WITHOUT ROWID + 인덱스 + FTS5
- PRAGMA 튜닝: WAL, NORMAL, cache, temp_store=MEMORY
- 진행률: 총량 미지 시에도 1,000건마다 진행 로그/라벨 갱신

▶ 변경 이력
[2025-10-26] v2.1.0
- biblio 테이블에 author_names, kac_codes 컬럼 추가
  * 기존: creator, dc:creator, dcterms:creator에 저자명과 KAC 코드가 혼재
  * 개선: 모든 creator 필드를 취합하여 저자명과 KAC 코드를 별도 컬럼으로 분리 저장
  * author_names: 실제 저자 이름들 (세미콜론 구분, 정렬됨)
  * kac_codes: nlk:KAC*/nlk:KAB* 형식의 전거 코드들 (세미콜론 구분, 정렬됨)
- 양 컬럼에 대한 인덱스 추가로 검색 성능 향상
- BIBLIO_SCHEMA 및 BIBLIO_SCHEMA_LIGHT 스키마 동기화
- upsert_biblio 함수에서 light/normal 모드 모두 새 컬럼 지원

실행:
    python Final_build_kac_authority_and_biblio_db.py

의존:
    pip install PySide6 ijson
"""
from __future__ import annotations
import fnmatch
import json
import os
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
import ijson

# optional accelerators
try:
    import ijson  # type: ignore

    HAS_IJSON = True
except Exception:
    HAS_IJSON = False

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# =====================
# SQLite helpers & tuning
# =====================


def _apply_sqlite_tuning(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA temp_store=MEMORY;")
    cur.execute("PRAGMA cache_size=-200000;")  # about 200MB
    cur.execute("PRAGMA locking_mode=EXCLUSIVE;")
    conn.commit()


def _norm_year(v: Union[str, int, None]) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, int):
        return v
    s = str(v)
    if "^^" in s:
        s = s.split("^^", 1)[0]
    s = s.strip()
    if s.isdigit():
        try:
            return int(s)
        except Exception:
            return None
    return None


def _as_list(x) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(v) for v in x if v is not None]
    return [str(x)]


def _extract_kac_code(nlk_id: str) -> str:
    if not nlk_id:
        return ""
    return nlk_id.split(":", 1)[1] if ":" in nlk_id else nlk_id


def _join_non_empty(parts: List[str], sep=", ") -> str:
    return sep.join([p for p in parts if p and str(p).strip()])


# ---------- text normalization ----------


def _strip_lang_tag(s: str) -> str:
    """Remove trailing @lang (e.g., "이름@ko")."""
    try:
        if isinstance(s, str) and "@" in s:
            base, tag = s.rsplit("@", 1)
            if 1 <= len(tag) <= 5:
                return base
    except Exception:
        pass
    return s if isinstance(s, str) else str(s)


def _norm_text(v) -> Optional[str]:
    """Ensure SQLite-friendly scalar string. Lists are joined with " | "."""
    if v is None:
        return None
    if isinstance(v, list):
        return " | ".join(_strip_lang_tag(str(x)) for x in v if x is not None)
    return _strip_lang_tag(str(v))


def _pick_best_text(v, preferred=("ko", "en")) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, list):
        for lang in preferred:
            for s in v:
                if isinstance(s, str) and s.endswith(f"@{lang}"):
                    return _strip_lang_tag(s)
        for s in v:
            if isinstance(s, str):
                return _strip_lang_tag(s)
        return _strip_lang_tag(str(v[0])) if v else None
    if isinstance(v, str):
        return _strip_lang_tag(v)
    return _strip_lang_tag(str(v))


# =====================
# DB schemas
# =====================

AUTHORITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS authority (
  kac_id_full TEXT PRIMARY KEY,
  kac_id TEXT,
  type TEXT,
  name TEXT,
  pref_label TEXT,
  label TEXT,
  gender TEXT,
  associated_language TEXT,
  corporate_name TEXT,
  isni TEXT,
  birth_year INTEGER,
  death_year INTEGER,
  date_published TEXT,
  modified TEXT,
  source_all TEXT,
  create_all TEXT,
  raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_authority_kac_id ON authority(kac_id);
CREATE INDEX IF NOT EXISTS idx_authority_name   ON authority(name);

CREATE TABLE IF NOT EXISTS authority_altlabel (
  kac_id_full TEXT NOT NULL,
  alt_label   TEXT NOT NULL,
  PRIMARY KEY (kac_id_full, alt_label)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_authority_altlabel_kac ON authority_altlabel(kac_id_full);

CREATE TABLE IF NOT EXISTS authority_sameas (
  kac_id_full TEXT NOT NULL,
  uri         TEXT NOT NULL,
  PRIMARY KEY (kac_id_full, uri)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_authority_sameas_kac ON authority_sameas(kac_id_full);

CREATE TABLE IF NOT EXISTS authority_source (
  kac_id_full TEXT NOT NULL,
  source      TEXT NOT NULL,
  PRIMARY KEY (kac_id_full, source)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_authority_source_kac ON authority_source(kac_id_full);

CREATE TABLE IF NOT EXISTS authority_job (
  kac_id_full TEXT NOT NULL,
  job_title   TEXT NOT NULL,
  PRIMARY KEY (kac_id_full, job_title)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_authority_job_kac ON authority_job(kac_id_full);

CREATE TABLE IF NOT EXISTS authority_field (
  kac_id_full TEXT NOT NULL,
  field       TEXT NOT NULL,
  PRIMARY KEY (kac_id_full, field)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_authority_field_kac ON authority_field(kac_id_full);

CREATE TABLE IF NOT EXISTS authority_create (
  kac_id_full TEXT NOT NULL,
  identifier  TEXT NOT NULL,
  PRIMARY KEY (kac_id_full, identifier)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_authority_create_kac ON authority_create(kac_id_full);
CREATE INDEX IF NOT EXISTS idx_authority_create_id  ON authority_create(identifier);

CREATE VIRTUAL TABLE IF NOT EXISTS authority_fts USING fts5(
  kac_id_full UNINDEXED,
  name, pref_label, label,
  alt_labels, job_titles, fields, sources,
  content=''
);
"""

AUTHORITY_SCHEMA_LIGHT = """
CREATE TABLE IF NOT EXISTS authority (
  kac_id_full TEXT PRIMARY KEY,
  kac_id TEXT,
  type TEXT,
  name TEXT,
  pref_label TEXT,
  label TEXT,
  gender TEXT,
  associated_language TEXT,
  corporate_name TEXT,
  isni TEXT,
  birth_year INTEGER,
  death_year INTEGER,
  date_published TEXT,
  modified TEXT,
  source_all TEXT,
  create_all TEXT
);

CREATE TABLE IF NOT EXISTS authority_altlabel (
  kac_id_full TEXT NOT NULL,
  alt_label   TEXT NOT NULL,
  PRIMARY KEY (kac_id_full, alt_label)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS authority_sameas (
  kac_id_full TEXT NOT NULL,
  uri         TEXT NOT NULL,
  PRIMARY KEY (kac_id_full, uri)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS authority_source (
  kac_id_full TEXT NOT NULL,
  source      TEXT NOT NULL,
  PRIMARY KEY (kac_id_full, source)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS authority_job (
  kac_id_full TEXT NOT NULL,
  job_title   TEXT NOT NULL,
  PRIMARY KEY (kac_id_full, job_title)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS authority_field (
  kac_id_full TEXT NOT NULL,
  field       TEXT NOT NULL,
  PRIMARY KEY (kac_id_full, field)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS authority_create (
  kac_id_full TEXT NOT NULL,
  identifier  TEXT NOT NULL,
  PRIMARY KEY (kac_id_full, identifier)
) WITHOUT ROWID;
"""

BIBLIO_SCHEMA = """
CREATE TABLE IF NOT EXISTS biblio (
    nlk_id TEXT PRIMARY KEY,
    year INTEGER,
    creator TEXT,
    dc_creator TEXT,
    dcterms_creator TEXT,
    title TEXT,
    author_names TEXT,
    kac_codes TEXT,
    raw_json TEXT
);
-- FTS5가 커버하므로 title, creator, author_names, kac_codes 인덱스 제거
CREATE INDEX IF NOT EXISTS idx_biblio_year ON biblio(year);

/* [최종 FTS5 전략]
  - 검색이 필요한 모든 텍스트 필드를 통합.
  - tokenize='unicode61': CJK 및 세미콜론(;) 분리 지원.
  - tokenchars=':': 'nlk:KAC...'를 단일 토큰으로 처리.
*/
CREATE VIRTUAL TABLE IF NOT EXISTS biblio_fts USING fts5(
    title,
    creator,
    dc_creator,
    dcterms_creator,
    author_names,
    kac_codes,
    content='biblio',
    content_rowid='rowid', -- biblio 테이블의 내부 rowid와 연결
    tokenize = 'unicode61 remove_diacritics 0 tokenchars ":"'
);
"""

BIBLIO_SCHEMA_LIGHT = """
CREATE TABLE IF NOT EXISTS biblio (
    nlk_id TEXT PRIMARY KEY,
    year INTEGER,
    creator TEXT,
    dc_creator TEXT,
    dcterms_creator TEXT,
    title TEXT,
    author_names TEXT,
    kac_codes TEXT
);
"""

# =====================
# Open/init DB
# =====================


def init_authority_db(path: str, light_mode: bool = False) -> sqlite3.Connection:
    is_new = (not os.path.exists(path)) or (os.path.getsize(path) == 0)
    conn = sqlite3.connect(path)
    if is_new:
        try:
            conn.execute("PRAGMA page_size=65536;")
        except Exception:
            pass
    _apply_sqlite_tuning(conn)
    # Use Light Mode schema without indexes and FTS
    conn.executescript(AUTHORITY_SCHEMA_LIGHT if light_mode else AUTHORITY_SCHEMA)
    return conn


def init_biblio_db(path: str, light_mode: bool = False) -> sqlite3.Connection:
    is_new = (not os.path.exists(path)) or (os.path.getsize(path) == 0)
    conn = sqlite3.connect(path)
    if is_new:
        try:
            conn.execute("PRAGMA page_size=65536;")
        except Exception:
            pass
    _apply_sqlite_tuning(conn)
    # Use Light Mode schema without indexes and FTS
    conn.executescript(BIBLIO_SCHEMA_LIGHT if light_mode else BIBLIO_SCHEMA)
    return conn


# =====================
# Upserters
# =====================


def upsert_authority(
    conn: sqlite3.Connection, rec: Dict[str, Any], build_fts: bool = True
):
    kac_id_full = rec.get("@id") or ""
    # Accept both KAC (persons) and KAB (corporate bodies). Skip others (e.g., FOAF without NLK id).
    if not (kac_id_full.startswith("nlk:KAC") or kac_id_full.startswith("nlk:KAB")):
        return

    cur = conn.cursor()
    kac_id = _extract_kac_code(kac_id_full)
    atype = rec.get("@type") or rec.get("rdf:type")

    name = _pick_best_text(rec.get("name") or rec.get("label") or rec.get("prefLabel"))
    pref_label = _pick_best_text(rec.get("prefLabel"))
    label = _pick_best_text(rec.get("label"))
    gender = _norm_text(rec.get("gender"))
    associated_language = _norm_text(rec.get("associatedLanguage"))
    corporate_name = _norm_text(rec.get("corporateName"))
    isni = _norm_text(rec.get("isni"))
    birth_year = _norm_year(rec.get("birthYear"))
    death_year = _norm_year(rec.get("deathYear"))
    date_published = _norm_text(rec.get("datePublished"))
    modified = _norm_text(rec.get("modified"))

    alt_labels = [_strip_lang_tag(x) for x in _as_list(rec.get("altLabel"))]
    same_as = _as_list(rec.get("sameAs"))
    job_titles = _as_list(rec.get("jobTitle"))
    fields = _as_list(rec.get("fieldOfActivity"))
    creates = _as_list(rec.get("create"))
    sources = _as_list(rec.get("source"))

    create_all_json = json.dumps(creates, ensure_ascii=False) if creates else None
    source_all_json = json.dumps(sources, ensure_ascii=False) if sources else None

    cur.execute(
        """
        INSERT INTO authority (
        kac_id_full, kac_id, type, name, pref_label, label, gender,
        associated_language, corporate_name, isni, birth_year, death_year,
        date_published, modified, source_all, create_all, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(kac_id_full) DO UPDATE SET
        kac_id=excluded.kac_id,
        type=excluded.type,
        name=excluded.name,
        pref_label=excluded.pref_label,
        label=excluded.label,
        gender=excluded.gender,
        associated_language=excluded.associated_language,
        corporate_name=excluded.corporate_name,
        isni=excluded.isni,
        birth_year=excluded.birth_year,
        death_year=excluded.death_year,
        date_published=excluded.date_published,
        modified=excluded.modified,
        source_all=excluded.source_all,
        create_all=excluded.create_all,
        raw_json=excluded.raw_json
        """,
        (
            kac_id_full,
            kac_id,
            (
                json.dumps(atype, ensure_ascii=False)
                if isinstance(atype, list)
                else str(atype) if atype else None
            ),
            name,
            pref_label,
            label,
            gender,
            associated_language,
            corporate_name,
            isni,
            birth_year,
            death_year,
            date_published,
            modified,
            source_all_json,
            create_all_json,
            json.dumps(rec, ensure_ascii=False),
        ),
    )

    # child tables: OR IGNORE 로 누적 (중복 제거)
    if alt_labels:
        cur.executemany(
            "INSERT OR IGNORE INTO authority_altlabel (kac_id_full, alt_label) VALUES (?, ?)",
            [(kac_id_full, v) for v in alt_labels],
        )
    if same_as:
        cur.executemany(
            "INSERT OR IGNORE INTO authority_sameas (kac_id_full, uri) VALUES (?, ?)",
            [(kac_id_full, v) for v in same_as],
        )
    if sources:
        cur.executemany(
            "INSERT OR IGNORE INTO authority_source (kac_id_full, source) VALUES (?, ?)",
            [(kac_id_full, v) for v in sources],
        )
    if job_titles:
        cur.executemany(
            "INSERT OR IGNORE INTO authority_job (kac_id_full, job_title) VALUES (?, ?)",
            [(kac_id_full, v) for v in job_titles],
        )
    if fields:
        cur.executemany(
            "INSERT OR IGNORE INTO authority_field (kac_id_full, field) VALUES (?, ?)",
            [(kac_id_full, v) for v in fields],
        )
    if creates:
        cur.executemany(
            "INSERT OR IGNORE INTO authority_create (kac_id_full, identifier) VALUES (?, ?)",
            [(kac_id_full, v) for v in creates],
        )

    # FTS: 즉시 구축은 옵션 (대량 적재시 지연 재구축 권장)
    if build_fts:
        cur.execute("DELETE FROM authority_fts WHERE kac_id_full=?", (kac_id_full,))
        cur.execute(
            "INSERT INTO authority_fts (kac_id_full, name, pref_label, label, alt_labels, job_titles, fields, sources) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                kac_id_full,
                name or "",
                pref_label or "",
                label or "",
                _join_non_empty(alt_labels),
                _join_non_empty(job_titles),
                _join_non_empty(fields),
                _join_non_empty(sources),
            ),
        )


def upsert_biblio(
    conn: sqlite3.Connection,
    rec: Dict[str, Any],
    build_fts: bool = True,
    light_mode: bool = False,
):
    cur = conn.cursor()
    nlk_id = rec.get("@id")
    if not nlk_id:
        return

    # Year: issuedYear > datePublished > issued
    year = _norm_year(
        rec.get("issuedYear") or rec.get("datePublished") or rec.get("issued")
    )

    # creator
    creator_list = _as_list(rec.get("creator"))
    creator_str = ";".join(creator_list) if creator_list else None

    # dc:creator
    dc_creator_list = _as_list(rec.get("dc:creator"))
    dc_creator_str = ";".join(dc_creator_list) if dc_creator_list else None

    # dcterms:creator (extract @id value if dict)
    dcterms_creator_raw = rec.get("dcterms:creator")
    dcterms_creator_list = []
    if isinstance(dcterms_creator_raw, list):
        for v in dcterms_creator_raw:
            if isinstance(v, dict) and "@id" in v:
                dcterms_creator_list.append(str(v["@id"]))
            else:
                dcterms_creator_list.append(str(v))
    elif isinstance(dcterms_creator_raw, dict) and "@id" in dcterms_creator_raw:
        dcterms_creator_list.append(str(dcterms_creator_raw["@id"]))
    elif dcterms_creator_raw:
        dcterms_creator_list.append(str(dcterms_creator_raw))
    dcterms_creator_str = (
        ";".join(dcterms_creator_list) if dcterms_creator_list else None
    )

    # -------------------
    # ✅ [핵심 추가] 모든 저자 관련 정보를 취합하여 이름과 KAC 코드로 분리
    all_items = set()
    if creator_str:
        all_items.update(item.strip() for item in creator_str.split(";"))
    if dc_creator_str:
        all_items.update(item.strip() for item in dc_creator_str.split(";"))
    if dcterms_creator_str:
        all_items.update(item.strip() for item in dcterms_creator_str.split(";"))

    author_names_list = []
    kac_codes_list = []
    for item in all_items:
        if item.startswith("nlk:KAC") or item.startswith("nlk:KAB"):
            kac_codes_list.append(item)
        elif item and item != "NULL":
            author_names_list.append(item)

    # 최종적으로 정렬된 문자열로 저장
    final_author_names = ";".join(sorted(author_names_list))
    final_kac_codes = ";".join(sorted(kac_codes_list))
    # -------------------

    title = _pick_best_text(rec.get("title"))
    raw_json_str = json.dumps(rec, ensure_ascii=False)

    if light_mode:
        cur.execute(
            """
            INSERT INTO biblio (nlk_id, year, creator, dc_creator, dcterms_creator, title, author_names, kac_codes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(nlk_id) DO UPDATE SET
                year=excluded.year,
                creator=excluded.creator,
                dc_creator=excluded.dc_creator,
                dcterms_creator=excluded.dcterms_creator,
                title=excluded.title,
                author_names=excluded.author_names,
                kac_codes=excluded.kac_codes
            """,
            (
                nlk_id,
                year,
                creator_str,
                dc_creator_str,
                dcterms_creator_str,
                title,
                final_author_names,
                final_kac_codes,
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO biblio (nlk_id, year, creator, dc_creator, dcterms_creator, title, author_names, kac_codes, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(nlk_id) DO UPDATE SET
              year=excluded.year,
              creator=excluded.creator,
              dc_creator=excluded.dc_creator,
              dcterms_creator=excluded.dcterms_creator,
              title=excluded.title,
              author_names=excluded.author_names,
              kac_codes=excluded.kac_codes,
              raw_json=excluded.raw_json
            """,
            (
                nlk_id,
                year,
                creator_str,
                dc_creator_str,
                dcterms_creator_str,
                title,
                final_author_names,
                final_kac_codes,
                raw_json_str,
            ),
        )
        if build_fts:
            # content='biblio', content_rowid='rowid' 옵션 사용 시,
            # FTS 테이블은 biblio 테이블의 rowid와 자동 연결됩니다.
            # 따라서 별도로 DELETE/INSERT 할 필요 없이, biblio 테이블 INSERT/UPDATE 시
            # 트리거가 자동으로 FTS 내용을 동기화합니다.
            # 만약 트리거를 사용하지 않고 직접 FTS를 채우려면 아래 코드를 사용하되,
            # biblio 테이블의 rowid를 알아내야 합니다.

            # === 트리거를 사용하지 않고 *수동*으로 FTS를 채우는 경우 ===
            # 먼저 biblio 테이블의 rowid를 가져옵니다.
            cur.execute("SELECT rowid FROM biblio WHERE nlk_id = ?", (nlk_id,))
            rowid_result = cur.fetchone()
            if rowid_result:
                biblio_rowid = rowid_result[0]
                # 기존 FTS 데이터 삭제 (rowid 기준)
                cur.execute("DELETE FROM biblio_fts WHERE rowid=?", (biblio_rowid,))
                # 새 FTS 데이터 삽입 (rowid 기준)
                cur.execute(
                    """INSERT INTO biblio_fts (
                                rowid, title, creator, dc_creator, dcterms_creator, author_names, kac_codes
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        biblio_rowid,
                        title or "",
                        creator_str or "",
                        dc_creator_str or "",
                        dcterms_creator_str or "",
                        final_author_names or "",  # ✅ author_names 추가
                        final_kac_codes or "",  # ✅ kac_codes 추가
                    ),
                )
            # =======================================================
            # !!! 중요: 하지만 우리는 트리거를 정의했으므로, 이 Python 코드 블록은
            #     실제로는 필요하지 않거나 주석 처리해야 합니다.
            #     트리거가 이 역할을 대신 수행합니다.
            #     build_fts 플래그는 Fast Mode 후처리에서만 의미를 가집니다.
            pass  # 트리거가 처리하므로 Python에서는 아무것도 안 함


# =====================
# Streaming JSON reader (handles concatenated values & @graph)
# =====================

import json as _json


def _yield_records_from_value(val):
    if isinstance(val, list):
        for obj in val:
            if isinstance(obj, dict):
                yield obj
    elif isinstance(val, dict):
        if "@graph" in val and isinstance(val["@graph"], list):
            for obj in val["@graph"]:
                if isinstance(obj, dict):
                    yield obj
        else:
            yield val


def _iter_json_records(path: str, log: callable) -> Iterable[Dict[str, Any]]:
    """High-performance streaming reader.
    Uses ijson if available (fast, incremental),
    otherwise falls back to a robust raw_decode-based concatenated parser.
    """
    if HAS_IJSON:
        try:
            # Try fast path: top-level array(s) OR concatenated values
            with open(path, "rb") as f:
                any_yielded = False
                for obj in ijson.items(f, "item", multiple_values=True):
                    if isinstance(obj, dict):
                        any_yielded = True
                        yield obj
                if any_yielded:
                    return
            # Try @graph streaming
            with open(path, "rb") as f:
                for obj in ijson.items(f, "@graph.item", multiple_values=True):
                    if isinstance(obj, dict):
                        yield obj
                return
        except Exception as e:
            log(f"[i] ijson fallback: {e}")
    # ---- fallback raw_decode (concatenated) ----
    dec = _json.JSONDecoder()
    buf = ""
    pos = 0
    CHUNK = 4 * 1024 * 1024
    with open(path, "r", encoding="utf-8") as f:
        first = f.read(1)
        if first and first != "﻿":
            buf = first
        while True:
            if pos >= len(buf):
                chunk = f.read(CHUNK)
                if not chunk:
                    break
                buf = buf[pos:] + chunk
                pos = 0
            while pos < len(buf) and buf[pos].isspace():
                pos += 1
            if pos >= len(buf):
                continue
            try:
                val, end = dec.raw_decode(buf, pos)
            except _json.JSONDecodeError:
                more = f.read(CHUNK)
                if more:
                    buf += more
                    continue
                else:
                    break
            # yield dicts (including @graph items)
            for rec in _yield_records_from_value(val):
                if isinstance(rec, dict):
                    yield rec
            pos = end


# =====================
# Batch worker
# =====================


@dataclass
@dataclass
class TaskConfig:
    authority_files: List[str]
    authority_db: Optional[str]
    biblio_files: List[str]
    biblio_db: Optional[str]
    batch_size: int = 2000
    fast_mode: bool = False  # safer default for big files
    light_mode: bool = False  # Light Mode: no index, FTS, raw_json


class BuildWorker(QThread):
    sig_progress = Signal(int, int)  # current, total (-1 if unknown)
    sig_phase = Signal(str)
    sig_log = Signal(str)
    sig_done = Signal(bool, str)

    def __init__(self, cfg: TaskConfig, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.cfg = cfg
        self._cancel = threading.Event()
        self._build_fts_inline = not cfg.fast_mode
        self.light_mode = cfg.light_mode  # Add light_mode from config

    def cancel(self):
        self._cancel.set()

    def _log(self, m: str):
        self.sig_log.emit(m)

    def _process_many(self, files: List[str], db_path: str, kind: str) -> int:
        if not files:
            return 0

        light_mode = getattr(self.cfg, "light_mode", False)

        if kind == "authority":
            conn = init_authority_db(db_path, light_mode=light_mode)
        else:
            conn = init_biblio_db(db_path, light_mode=light_mode)

        # When in light mode, skip all index and FTS operations
        if light_mode:
            self._build_fts_inline = False  # Disable inline FTS
        if not light_mode:
            if kind == "authority":
                if self.cfg.fast_mode:
                    conn.executescript(
                        """
PRAGMA synchronous=OFF;
DROP INDEX IF EXISTS idx_authority_kac_id;
DROP INDEX IF EXISTS idx_authority_name;
DROP INDEX IF EXISTS idx_authority_altlabel_kac;
DROP INDEX IF EXISTS idx_authority_sameas_kac;
DROP INDEX IF EXISTS idx_authority_job_kac;
DROP INDEX IF EXISTS idx_authority_field_kac;
DROP INDEX IF EXISTS idx_authority_create_kac;
DROP INDEX IF EXISTS idx_authority_create_id;
DROP INDEX IF EXISTS idx_authority_source_kac;
DELETE FROM authority_fts;
"""
                    )
                else:
                    conn.execute("DELETE FROM authority_fts;")
            else:
                if self.cfg.fast_mode:
                    conn.executescript(
                        """
PRAGMA synchronous=OFF;
DROP INDEX IF EXISTS idx_biblio_year;
DROP INDEX IF EXISTS idx_biblio_kac_creator;
DROP INDEX IF EXISTS idx_biblio_title;
DELETE FROM biblio_fts;
"""
                    )
                else:
                    conn.execute("DELETE FROM biblio_fts;")
        conn.commit()

        processed = 0
        self.sig_progress.emit(0, -1)  # unknown total → indeterminate

        try:
            with conn:
                for path in files:
                    if self._cancel.is_set():
                        self._log("[!] Cancel requested. Aborting…")
                        break
                    self.sig_phase.emit(f"{kind}: {os.path.basename(path)}")
                    self._log(f"[*] {kind} → {path}")
                    batch = 0
                    for rec in _iter_json_records(path, self._log):
                        if self._cancel.is_set():
                            break
                        if kind == "authority":
                            upsert_authority(
                                conn, rec, build_fts=self._build_fts_inline
                            )
                        else:
                            upsert_biblio(
                                conn,
                                rec,
                                build_fts=self._build_fts_inline,
                                light_mode=self.light_mode,
                            )
                        processed += 1
                        batch += 1

                        # show some heartbeat for unknown total
                        if processed % 1000 == 0:
                            self.sig_phase.emit(
                                f"{kind}: {os.path.basename(path)} · {processed:,} rec"
                            )
                            self.sig_log.emit(
                                f"[i] {kind} processed so far: {processed:,}"
                            )
                            self.sig_progress.emit(processed, -1)

                        if batch >= self.cfg.batch_size:
                            conn.commit()
                            batch = 0
                    if batch:
                        conn.commit()
        finally:
            # post steps for fast mode: rebuild indexes & FTS
            if self.cfg.fast_mode:
                try:
                    if kind == "authority":
                        conn.executescript(
                            """
-- recreate indexes
CREATE INDEX IF NOT EXISTS idx_authority_kac_id ON authority(kac_id);
CREATE INDEX IF NOT EXISTS idx_authority_name   ON authority(name);
CREATE INDEX IF NOT EXISTS idx_authority_altlabel_kac ON authority_altlabel(kac_id_full);
CREATE INDEX IF NOT EXISTS idx_authority_sameas_kac  ON authority_sameas(kac_id_full);
CREATE INDEX IF NOT EXISTS idx_authority_job_kac     ON authority_job(kac_id_full);
CREATE INDEX IF NOT EXISTS idx_authority_field_kac   ON authority_field(kac_id_full);
CREATE INDEX IF NOT EXISTS idx_authority_create_kac  ON authority_create(kac_id_full);
CREATE INDEX IF NOT EXISTS idx_authority_create_id   ON authority_create(identifier);
CREATE INDEX IF NOT EXISTS idx_authority_source_kac  ON authority_source(kac_id_full);
-- bulk build FTS
DELETE FROM authority_fts;

INSERT INTO authority_fts
  (kac_id_full, name, pref_label, label, alt_labels, job_titles, fields, sources)
SELECT
  a.kac_id_full,
  COALESCE(a.name, ''),
  COALESCE(a.pref_label, ''),
  COALESCE(a.label, ''),
  COALESCE((SELECT GROUP_CONCAT(alt_label, ', ')
            FROM authority_altlabel x WHERE x.kac_id_full=a.kac_id_full), ''),
  COALESCE((SELECT GROUP_CONCAT(job_title, ', ')
            FROM authority_job x WHERE x.kac_id_full=a.kac_id_full), ''),
  COALESCE((SELECT GROUP_CONCAT(field, ', ')
            FROM authority_field x WHERE x.kac_id_full=a.kac_id_full), ''),
  COALESCE((SELECT GROUP_CONCAT(source, ', ')
            FROM authority_source x WHERE x.kac_id_full=a.kac_id_full), '')
FROM authority AS a;   -- ← 이 줄 추가

INSERT INTO authority_fts(authority_fts) VALUES('optimize');
PRAGMA synchronous=NORMAL;
"""
                        )
                    else:  # kind == 'biblio'
                        self._log(
                            "[i] Biblio: Rebuilding indexes and FTS table (Fast Mode)..."
                        )
                        conn.executescript(
                            """
/* --- Recreate non-FTS indexes --- */
CREATE INDEX IF NOT EXISTS idx_biblio_year ON biblio(year);
/* FTS가 커버하므로 title, creator 등 텍스트 인덱스는 제거 */

/* --- Bulk rebuild FTS table --- */
-- 1. 기존 FTS 데이터 삭제
DELETE FROM biblio_fts;

-- 2. biblio 테이블에서 모든 데이터를 읽어 FTS 테이블 재구성
--    (rowid를 사용하여 원본 테이블과 연결)
INSERT INTO biblio_fts (
    rowid, title, creator, dc_creator, dcterms_creator, author_names, kac_codes
)
SELECT
    rowid,
    COALESCE(title, ''),
    COALESCE(creator, ''),
    COALESCE(dc_creator, ''),
    COALESCE(dcterms_creator, ''),
    COALESCE(author_names, ''), -- ✅ author_names 추가
    COALESCE(kac_codes, '')     -- ✅ kac_codes 추가
FROM biblio;

-- 3. FTS 인덱스 최적화
INSERT INTO biblio_fts(biblio_fts) VALUES('optimize');

-- 4. 동기화 모드 복원
PRAGMA synchronous=NORMAL;
"""
                        )
                        self._log("[✓] Biblio: Indexes and FTS table rebuilt.")
                except Exception as e:
                    self._log(f"[WARN] post-build optimize failed: {e}")
                finally:
                    conn.commit()
            conn.close()
        self._log(f"[✓] {kind} processed: {processed}")
        return processed

    def run(self):
        try:
            grand_total_processed = 0
            if self.cfg.authority_files and self.cfg.authority_db:
                processed = self._process_many(
                    self.cfg.authority_files, self.cfg.authority_db, "authority"
                )
                grand_total_processed += processed
                if self._cancel.is_set():
                    self.sig_done.emit(False, "Canceled during authority phase")
                    return

                # ✅ [추가] 실제 DB에 저장된 고유 레코드 수 확인
                try:
                    conn = sqlite3.connect(self.cfg.authority_db)
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM authority")
                    actual_count = cur.fetchone()[0]
                    conn.close()
                    self.sig_log.emit(
                        f"[i] Authority: Processed {processed:,} records → {actual_count:,} unique records in DB"
                    )
                except Exception as e:
                    self.sig_log.emit(f"[WARN] Could not count authority records: {e}")

            if self.cfg.biblio_files and self.cfg.biblio_db:
                processed = self._process_many(
                    self.cfg.biblio_files, self.cfg.biblio_db, "biblio"
                )
                grand_total_processed += processed
                if self._cancel.is_set():
                    self.sig_done.emit(False, "Canceled during biblio phase")
                    return

                # ✅ [추가] 실제 DB에 저장된 고유 레코드 수 확인
                try:
                    conn = sqlite3.connect(self.cfg.biblio_db)
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM biblio")
                    actual_count = cur.fetchone()[0]
                    conn.close()
                    self.sig_log.emit(
                        f"[i] Biblio: Processed {processed:,} records → {actual_count:,} unique records in DB"
                    )
                except Exception as e:
                    self.sig_log.emit(f"[WARN] Could not count biblio records: {e}")

            self.sig_done.emit(
                True,
                f"Completed. Total processed: {grand_total_processed:,} records (check log for unique counts)",
            )
        except Exception as e:
            self.sig_log.emit(f"[ERROR] {e}")
            self.sig_done.emit(False, str(e))


# =====================
# GUI
# =====================


class BuilderGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KAC Authority & NLK Biblio — Batch JSON → SQLite Builder")
        self.resize(1120, 780)

        # Authority widgets
        self.auth_list = QListWidget()
        self.auth_add_files = QPushButton("Add files…")
        self.auth_add_folder = QPushButton("Add folder…")
        self.auth_clear = QPushButton("Clear")
        self.auth_pattern = QLineEdit("*.json;*.jsonl")
        self.auth_recursive = QCheckBox("Recursive")
        self.auth_db = QLineEdit()
        self.auth_db_btn = QPushButton("DB…")

        g1 = QGridLayout()
        g1.addWidget(QLabel("Files"), 0, 0)
        g1.addWidget(self.auth_list, 1, 0, 1, 4)
        g1.addWidget(self.auth_add_files, 2, 0)
        g1.addWidget(self.auth_add_folder, 2, 1)
        g1.addWidget(self.auth_clear, 2, 2)
        g1.addWidget(self.auth_recursive, 2, 3)
        g1.addWidget(QLabel("Pattern"), 3, 0)
        g1.addWidget(self.auth_pattern, 3, 1)
        g1.addWidget(QLabel("DB"), 4, 0)
        g1.addWidget(self.auth_db, 4, 1, 1, 2)
        g1.addWidget(self.auth_db_btn, 4, 3)
        box1 = QGroupBox("Authority (KAC/KAB)")
        box1.setLayout(g1)

        # Biblio widgets
        self.bib_list = QListWidget()
        self.bib_add_files = QPushButton("Add files…")
        self.bib_add_folder = QPushButton("Add folder…")
        self.bib_clear = QPushButton("Clear")
        self.bib_pattern = QLineEdit("*.json;*.jsonl")
        self.bib_recursive = QCheckBox("Recursive")
        self.bib_db = QLineEdit()
        self.bib_db_btn = QPushButton("DB…")

        g2 = QGridLayout()
        g2.addWidget(QLabel("Files"), 0, 0)
        g2.addWidget(self.bib_list, 1, 0, 1, 4)
        g2.addWidget(self.bib_add_files, 2, 0)
        g2.addWidget(self.bib_add_folder, 2, 1)
        g2.addWidget(self.bib_clear, 2, 2)
        g2.addWidget(self.bib_recursive, 2, 3)
        g2.addWidget(QLabel("Pattern"), 3, 0)
        g2.addWidget(self.bib_pattern, 3, 1)
        g2.addWidget(QLabel("DB"), 4, 0)
        g2.addWidget(self.bib_db, 4, 1, 1, 2)
        g2.addWidget(self.bib_db_btn, 4, 3)
        box2 = QGroupBox("Biblio (Bibliographic Records)")
        box2.setLayout(g2)

        # Controls
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.lbl_phase = QLabel("Idle")
        self.btn_start = QPushButton("Start")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_add_indexes = QPushButton("Add Indexes && FTS")
        self.chk_light = QCheckBox("Light Mode (no index, FTS, raw_json)")
        self.chk_fast = QCheckBox("Turbo build (drop/rebuild indexes & FTS, sync=OFF)")
        self.btn_cancel.setEnabled(False)
        self.btn_add_indexes.setEnabled(True)

        ctl = QHBoxLayout()
        ctl.addWidget(self.lbl_phase)
        ctl.addStretch(1)
        ctl.addWidget(self.chk_light)
        ctl.addWidget(self.chk_fast)
        ctl.addWidget(self.btn_add_indexes)
        ctl.addWidget(self.btn_start)
        ctl.addWidget(self.btn_cancel)

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        top = QVBoxLayout(self)
        top.addWidget(box1)
        top.addWidget(box2)
        top.addWidget(self.progress)
        top.addLayout(ctl)
        top.addWidget(self.log, 1)

        # Signals
        self.auth_add_files.clicked.connect(lambda: self.add_files(self.auth_list))
        self.auth_add_folder.clicked.connect(
            lambda: self.add_folder(
                self.auth_list, self.auth_pattern, self.auth_recursive
            )
        )
        self.auth_clear.clicked.connect(lambda: self.auth_list.clear())
        self.auth_db_btn.clicked.connect(self.pick_auth_db)

        self.bib_add_files.clicked.connect(lambda: self.add_files(self.bib_list))
        self.bib_add_folder.clicked.connect(
            lambda: self.add_folder(self.bib_list, self.bib_pattern, self.bib_recursive)
        )
        self.bib_clear.clicked.connect(lambda: self.bib_list.clear())
        self.bib_db_btn.clicked.connect(self.pick_bib_db)

        self.btn_start.clicked.connect(self.on_start)
        self.btn_cancel.clicked.connect(self.on_cancel)
        self.btn_add_indexes.clicked.connect(self.on_add_indexes)

        self.worker: Optional[BuildWorker] = None

    def on_add_indexes(self):
        """Apply final FTS strategy and indexes to existing DBs."""
        auth_path = self.auth_db.text().strip()
        bib_path = self.bib_db.text().strip()

        if not (auth_path or bib_path):
            QMessageBox.warning(self, "Error", "Select at least one DB path")
            return

        reply = QMessageBox.question(
            self,
            "Apply Final Indexes & FTS",
            "This will apply the final indexing and FTS5 strategy (potentially replacing existing ones) to the selected DBs. Ensure you have backups. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,  # Default to No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.log.clear()  # 로그 초기화
        self.append_log("[i] Starting to apply indexes and FTS...")
        self.progress.setRange(0, 0)  # Indicate busy state
        self.btn_add_indexes.setEnabled(False)  # Disable button during operation

        try:
            # --- Authority DB ---
            if auth_path and os.path.exists(auth_path):
                self.append_log(f"[*] Processing Authority DB: {auth_path}")
                conn = sqlite3.connect(auth_path)
                # (Authority 부분은 이전 코드와 동일하게 유지 - 필요시 이 부분도 업데이트 가능)
                conn.executescript(
                    """
                    -- recreate indexes
                    CREATE INDEX IF NOT EXISTS idx_authority_kac_id ON authority(kac_id);
                    CREATE INDEX IF NOT EXISTS idx_authority_name ON authority(name);
                    CREATE INDEX IF NOT EXISTS idx_authority_altlabel_kac ON authority_altlabel(kac_id_full);
                    CREATE INDEX IF NOT EXISTS idx_authority_sameas_kac ON authority_sameas(kac_id_full);
                    CREATE INDEX IF NOT EXISTS idx_authority_job_kac ON authority_job(kac_id_full);
                    CREATE INDEX IF NOT EXISTS idx_authority_field_kac ON authority_field(kac_id_full);
                    CREATE INDEX IF NOT EXISTS idx_authority_create_kac ON authority_create(kac_id_full);
                    CREATE INDEX IF NOT EXISTS idx_authority_create_id ON authority_create(identifier);
                    CREATE INDEX IF NOT EXISTS idx_authority_source_kac ON authority_source(kac_id_full);
                    -- add FTS
                    CREATE VIRTUAL TABLE IF NOT EXISTS authority_fts USING fts5(
                        kac_id_full UNINDEXED,
                        name, pref_label, label,
                        alt_labels, job_titles, fields, sources,
                        content='authority', -- Assuming content/content_rowid needed if using triggers
                        content_rowid='rowid' -- Assuming rowid PK for authority table
                    );
                    DELETE FROM authority_fts;
                    INSERT INTO authority_fts (rowid, kac_id_full, name, pref_label, label, alt_labels, job_titles, fields, sources)
                    SELECT
                        a.rowid, -- Use rowid for content_rowid
                        a.kac_id_full,
                        COALESCE(a.name, ''),
                        COALESCE(a.pref_label, ''),
                        COALESCE(a.label, ''),
                        COALESCE((SELECT GROUP_CONCAT(alt_label, ', ')
                                FROM authority_altlabel x WHERE x.kac_id_full=a.kac_id_full), ''),
                        COALESCE((SELECT GROUP_CONCAT(job_title, ', ')
                                FROM authority_job x WHERE x.kac_id_full=a.kac_id_full), ''),
                        COALESCE((SELECT GROUP_CONCAT(field, ', ')
                                FROM authority_field x WHERE x.kac_id_full=a.kac_id_full), ''),
                        COALESCE((SELECT GROUP_CONCAT(source, ', ')
                                FROM authority_source x WHERE x.kac_id_full=a.kac_id_full), '')
                    FROM authority AS a;
                    INSERT INTO authority_fts(authority_fts) VALUES('optimize');
                """
                )
                conn.commit()
                conn.close()
                self.append_log(f"[✓] Authority DB processed: {auth_path}")

            # --- Biblio DB (Compromise Strategy - No advanced tokenizer) ---
            if bib_path and os.path.exists(bib_path):
                self.append_log(
                    f"[*] Processing Biblio DB (Compromise FTS): {bib_path}"
                )
                conn = sqlite3.connect(bib_path)
                conn.executescript(
                    """
                    /* [1단계: 기존 FTS 및 트리거 정리 (오류 발생 시 무시)] */
                    DROP TRIGGER IF EXISTS biblio_ai;
                    DROP TRIGGER IF EXISTS biblio_au;
                    DROP TRIGGER IF EXISTS biblio_ad;
                    DROP TABLE IF EXISTS biblio_fts; /* Use DROP TABLE for virtual tables */

                    /* [2단계: 중복 B-Tree 인덱스 삭제 (선택적)] - 그대로 유지 */
                    DROP INDEX IF EXISTS idx_biblio_creator;
                    DROP INDEX IF EXISTS idx_biblio_dc_creator;
                    DROP INDEX IF EXISTS idx_biblio_dcterms_creator;
                    DROP INDEX IF EXISTS idx_biblio_title;
                    DROP INDEX IF EXISTS idx_biblio_author_names;
                    DROP INDEX IF EXISTS idx_biblio_kac_codes;
                    CREATE INDEX IF NOT EXISTS idx_biblio_year ON biblio(year);

                    /* [3단계: 새로운 FTS5 테이블 (타협안 - tokenize 옵션 없음)] */
                    CREATE VIRTUAL TABLE biblio_fts USING fts5(
                        title,
                        creator,
                        dc_creator,
                        dcterms_creator,
                        author_names,
                        kac_codes,
                        content='biblio',
                        content_rowid='rowid'
                        /* tokenize 옵션 제거됨 */
                    );

                    /* 3-2 ~ 3-4: 트리거 생성 (이전과 동일) */
                    CREATE TRIGGER IF NOT EXISTS biblio_ai AFTER INSERT ON biblio BEGIN
                      INSERT INTO biblio_fts(
                        rowid, title, creator, dc_creator, dcterms_creator, author_names, kac_codes
                      ) VALUES (
                        new.rowid, new.title, new.creator, new.dc_creator, new.dcterms_creator, new.author_names, new.kac_codes
                      );
                    END;
                    CREATE TRIGGER IF NOT EXISTS biblio_au AFTER UPDATE ON biblio BEGIN
                      UPDATE biblio_fts
                      SET title = new.title,
                          creator = new.creator,
                          dc_creator = new.dc_creator,
                          dcterms_creator = new.dcterms_creator,
                          author_names = new.author_names,
                          kac_codes = new.kac_codes
                      WHERE rowid = old.rowid;
                    END;
                    CREATE TRIGGER IF NOT EXISTS biblio_ad AFTER DELETE ON biblio BEGIN
                      DELETE FROM biblio_fts WHERE rowid = old.rowid;
                    END;

                    /* [4단계: 기존 데이터 인덱싱] (이전과 동일) */
                    DELETE FROM biblio_fts;
                    INSERT INTO biblio_fts(rowid, title, creator, dc_creator, dcterms_creator, author_names, kac_codes)
                    SELECT rowid, title, creator, dc_creator, dcterms_creator, author_names, kac_codes FROM biblio;

                    /* [5단계: 최적화] (이전과 동일) */
                    INSERT INTO biblio_fts(biblio_fts) VALUES('optimize');
                """
                )
                conn.commit()
                conn.close()
                self.append_log(f"[✓] Biblio DB processed (Compromise FTS): {bib_path}")

            # --- Completion ---
            self.progress.setRange(0, 100)  # Indicate completion
            self.progress.setValue(100)
            self.btn_add_indexes.setEnabled(True)  # Re-enable button
            QMessageBox.information(
                self, "Success", "Final indexes and FTS strategy applied successfully!"
            )
            self.append_log("[✓] Operation completed.")

        except sqlite3.Error as e:  # Catch SQLite specific errors
            error_msg = f"Failed to apply indexes/FTS: {str(e)}"
            self.append_log(f"[❌ ERROR] {error_msg}")
            # Check for the specific parse error
            if "parse error" in str(e) or "no such tokenizer" in str(e):
                self.append_log(
                    "[!] The SQLite version being used likely lacks ICU support for the advanced tokenizer."
                )
                self.append_log(
                    "    Consider running this operation using the Python environment where the main app runs,"
                )
                self.append_log(
                    "    or use a simpler FTS configuration (without 'tokenize' options) as a fallback."
                )
                error_msg += "\n\n(SQLite ICU support might be missing)"

            QMessageBox.critical(self, "Error", error_msg)
            self.progress.setRange(0, 100)  # Reset progress
            self.progress.setValue(0)
            self.btn_add_indexes.setEnabled(True)  # Re-enable button on error

        except Exception as e:  # Catch other potential errors
            error_msg = f"An unexpected error occurred: {str(e)}"
            self.append_log(f"[❌ ERROR] {error_msg}")
            QMessageBox.critical(self, "Error", error_msg)
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.btn_add_indexes.setEnabled(True)

    # ---------- helpers
    def _list_items(self, lw: QListWidget) -> List[str]:
        return [lw.item(i).text() for i in range(lw.count())]

    def add_files(self, lw: QListWidget):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select JSON files", "", "JSON files (*.json *.jsonl);;All files (*)"
        )
        for p in files:
            if not any(lw.item(i).text() == p for i in range(lw.count())):
                lw.addItem(QListWidgetItem(p))
        if lw is self.auth_list and not self.auth_db.text() and files:
            self.auth_db.setText(
                os.path.join(os.path.dirname(files[0]), "kac_authorities.sqlite")
            )
        if lw is self.bib_list and not self.bib_db.text() and files:
            self.bib_db.setText(
                os.path.join(os.path.dirname(files[0]), "nlk_biblio.sqlite")
            )

    def add_folder(
        self, lw: QListWidget, pattern_edit: QLineEdit, recursive_chk: QCheckBox
    ):
        folder = QFileDialog.getExistingDirectory(self, "Select folder")
        if not folder:
            return
        patterns = [p.strip() for p in pattern_edit.text().split(";") if p.strip()]
        recursive = recursive_chk.isChecked()
        matched: List[str] = []
        if recursive:
            for root, _, files in os.walk(folder):
                for fn in files:
                    if any(fnmatch.fnmatch(fn, pat) for pat in patterns):
                        matched.append(os.path.join(root, fn))
        else:
            for fn in os.listdir(folder):
                if any(fnmatch.fnmatch(fn, pat) for pat in patterns):
                    matched.append(os.path.join(folder, fn))
        for p in matched:
            if not any(lw.item(i).text() == p for i in range(lw.count())):
                lw.addItem(QListWidgetItem(p))
        if lw is self.auth_list and not self.auth_db.text() and matched:
            self.auth_db.setText(os.path.join(folder, "kac_authorities.sqlite"))
        if lw is self.bib_list and not self.bib_db.text() and matched:
            self.bib_db.setText(os.path.join(folder, "nlk_biblio.sqlite"))

    def pick_auth_db(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Authority DB",
            self.auth_db.text() or "kac_authorities.sqlite",
            "SQLite (*.sqlite)",
        )
        if path:
            self.auth_db.setText(path)

    def pick_bib_db(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Biblio DB",
            self.bib_db.text() or "nlk_biblio.sqlite",
            "SQLite (*.sqlite)",
        )
        if path:
            self.bib_db.setText(path)

    # ---------- run/cancel
    def on_start(self):
        auth_files = self._list_items(self.auth_list)
        bib_files = self._list_items(self.bib_list)
        if not auth_files and not bib_files:
            QMessageBox.warning(
                self,
                "Input missing",
                "Add at least one JSON file (Authority or Biblio).",
            )
            return
        if auth_files and not self.auth_db.text():
            QMessageBox.warning(self, "DB path missing", "Select Authority DB path.")
            return
        if bib_files and not self.bib_db.text():
            QMessageBox.warning(self, "DB path missing", "Select Biblio DB path.")
            return

        self.log.clear()
        self.append_log("[i] Starting batch…")
        self.progress.setRange(0, 0)
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)

        cfg = TaskConfig(
            authority_files=auth_files,
            authority_db=self.auth_db.text() or None,
            biblio_files=bib_files,
            biblio_db=self.bib_db.text() or None,
            fast_mode=self.chk_fast.isChecked(),
            light_mode=self.chk_light.isChecked(),
        )
        self.worker = BuildWorker(cfg)
        self.worker.sig_log.connect(self.append_log)
        self.worker.sig_progress.connect(self.on_progress)
        self.worker.sig_phase.connect(self.on_phase)
        self.worker.sig_done.connect(self.on_done)
        self.worker.start()

    def on_cancel(self):
        if self.worker:
            self.worker.cancel()
            self.append_log("[i] Cancel requested…")

    @Slot(str)
    def append_log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log.append(f"[{ts}] {msg}")

    @Slot(int, int)
    def on_progress(self, current: int, total: int):
        if total <= 0:
            if self.progress.minimum() != 0 or self.progress.maximum() != 0:
                self.progress.setRange(0, 0)
            self.lbl_phase.setText(f"Working… {current:,} rec")
        else:
            if self.progress.maximum() != total:
                self.progress.setRange(0, total)
            self.progress.setValue(current)
            self.lbl_phase.setText(f"{current:,} / {total:,}")

    @Slot(str)
    def on_phase(self, text: str):
        self.log.append(f">> {text}")

    @Slot(bool, str)
    def on_done(self, ok: bool, message: str):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.worker = None
        if ok:
            self.append_log(f"[✓] {message}")
            QMessageBox.information(self, "Done", message)
        else:
            self.append_log(f"[×] {message}")
            QMessageBox.critical(self, "Failed", message)


def main():
    app = QApplication(sys.argv)
    w = BuilderGUI()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
