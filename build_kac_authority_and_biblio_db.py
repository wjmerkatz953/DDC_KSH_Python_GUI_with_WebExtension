# -*- coding: utf-8 -*-
"""
KAC/KAB Authority & NLK Biblio — Batch JSON → SQLite Builder (PySide6)

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

실행:
    python kac_biblio_builder_gui.py

의존:
    pip install PySide6
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

BIBLIO_SCHEMA = """
CREATE TABLE IF NOT EXISTS biblio (
  identifier TEXT PRIMARY KEY,
  type TEXT,
  title TEXT,
  remainder_of_title TEXT,
  label TEXT,
  dc_creator TEXT,
  creator_kac TEXT,
  issued_year INTEGER,
  ddc TEXT,
  edition_of_ddc TEXT,
  kdc TEXT,
  classification_nlk TEXT,
  publisher TEXT,
  publication_place TEXT,
  place_uri TEXT,
  language_uri TEXT,
  type_of_data TEXT,
  item_number_nlk TEXT,
  local_holding TEXT,
  title_of_series TEXT,
  uniform_title_of_series TEXT,
  volume_of_series TEXT,
  bibliography TEXT,
  date_published TEXT,
  same_as TEXT,
  raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_biblio_title        ON biblio(title);
CREATE INDEX IF NOT EXISTS idx_biblio_year         ON biblio(issued_year);
CREATE INDEX IF NOT EXISTS idx_biblio_creator_kac  ON biblio(creator_kac);

CREATE TABLE IF NOT EXISTS biblio_isbn (
  identifier TEXT NOT NULL,
  isbn       TEXT NOT NULL,
  PRIMARY KEY (identifier, isbn)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_biblio_isbn_id ON biblio_isbn(identifier);
CREATE INDEX IF NOT EXISTS idx_biblio_isbn_isbn ON biblio_isbn(isbn);

CREATE TABLE IF NOT EXISTS biblio_subject (
  identifier TEXT NOT NULL,
  uri        TEXT NOT NULL,
  PRIMARY KEY (identifier, uri)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_biblio_subject_id ON biblio_subject(identifier);

CREATE TABLE IF NOT EXISTS biblio_sameas (
  identifier TEXT NOT NULL,
  uri        TEXT NOT NULL,
  PRIMARY KEY (identifier, uri)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_biblio_sameas_id ON biblio_sameas(identifier);

CREATE VIRTUAL TABLE IF NOT EXISTS biblio_fts USING fts5(
  identifier UNINDEXED,
  title, remainder_of_title, series, publisher, place, dc_creator,
  content=''
);
"""

# =====================
# Open/init DB
# =====================


def init_authority_db(path: str) -> sqlite3.Connection:
    is_new = (not os.path.exists(path)) or (os.path.getsize(path) == 0)
    conn = sqlite3.connect(path)
    if is_new:
        try:
            conn.execute("PRAGMA page_size=65536;")
        except Exception:
            pass
    _apply_sqlite_tuning(conn)
    conn.executescript(AUTHORITY_SCHEMA)
    return conn


def init_biblio_db(path: str) -> sqlite3.Connection:
    is_new = (not os.path.exists(path)) or (os.path.getsize(path) == 0)
    conn = sqlite3.connect(path)
    if is_new:
        try:
            conn.execute("PRAGMA page_size=65536;")
        except Exception:
            pass
    _apply_sqlite_tuning(conn)
    conn.executescript(BIBLIO_SCHEMA)
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
    conn: sqlite3.Connection, rec: Dict[str, Any], build_fts: bool = True
):
    cur = conn.cursor()
    identifier = rec.get("@id") or rec.get("identifier") or ""
    if not identifier:
        return

    atype = rec.get("@type") or rec.get("rdf:type")
    title = _pick_best_text(rec.get("title"))
    remainder = _pick_best_text(rec.get("remainderOfTitle"))
    label = _pick_best_text(rec.get("label"))
    dc_creator = _pick_best_text(rec.get("dc:creator") or rec.get("dc_creator"))

    creator_kac = rec.get("creator")
    if isinstance(creator_kac, list):
        creator_kac_repr = next((str(v) for v in creator_kac if v), None)
    else:
        creator_kac_repr = str(creator_kac) if creator_kac else None

    issued_year = _norm_year(rec.get("issued") or rec.get("issuedYear"))
    ddc = _norm_text(rec.get("ddc"))
    edition_of_ddc = _norm_text(rec.get("editionOfDDC"))
    kdc = _norm_text(rec.get("kdc"))
    classification_nlk = _norm_text(rec.get("classificationNumberOfNLK"))
    publisher = _pick_best_text(rec.get("publisher"))
    publication_place = _pick_best_text(rec.get("publicationPlace"))
    place_uri = _norm_text(rec.get("place"))
    language_uri = _norm_text(rec.get("language"))
    type_of_data = _norm_text(rec.get("typeOfData"))
    item_number_nlk = _norm_text(rec.get("itemNumberOfNLK"))
    local_holding = _norm_text(rec.get("localHolding"))
    title_of_series = _pick_best_text(rec.get("titleOfSeries"))
    uniform_title_of_series = _pick_best_text(rec.get("uniformTitleOfSeries"))
    volume_of_series = _norm_text(rec.get("volumeOfSeries"))
    bibliography = _norm_text(rec.get("bibliography"))
    date_published = _norm_text(rec.get("datePublished"))

    isbns = _as_list(rec.get("isbn"))
    subjects = _as_list(rec.get("subject"))
    sameas_list = _as_list(rec.get("sameAs"))

    raw_json = json.dumps(rec, ensure_ascii=False)

    cur.execute(
        """
        INSERT INTO biblio (
          identifier, type, title, remainder_of_title, label, dc_creator, creator_kac,
          issued_year, ddc, edition_of_ddc, kdc, classification_nlk, publisher,
          publication_place, place_uri, language_uri, type_of_data, item_number_nlk,
          local_holding, title_of_series, uniform_title_of_series, volume_of_series,
          bibliography, date_published, same_as, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(identifier) DO UPDATE SET
          type=excluded.type,
          title=excluded.title,
          remainder_of_title=excluded.remainder_of_title,
          label=excluded.label,
          dc_creator=excluded.dc_creator,
          creator_kac=excluded.creator_kac,
          issued_year=excluded.issued_year,
          ddc=excluded.ddc,
          edition_of_ddc=excluded.edition_of_ddc,
          kdc=excluded.kdc,
          classification_nlk=excluded.classification_nlk,
          publisher=excluded.publisher,
          publication_place=excluded.publication_place,
          place_uri=excluded.place_uri,
          language_uri=excluded.language_uri,
          type_of_data=excluded.type_of_data,
          item_number_nlk=excluded.item_number_nlk,
          local_holding=excluded.local_holding,
          title_of_series=excluded.title_of_series,
          uniform_title_of_series=excluded.uniform_title_of_series,
          volume_of_series=excluded.volume_of_series,
          bibliography=excluded.bibliography,
          date_published=excluded.date_published,
          same_as=excluded.same_as,
          raw_json=excluded.raw_json
        """,
        (
            identifier,
            (
                json.dumps(atype, ensure_ascii=False)
                if isinstance(atype, list)
                else str(atype) if atype else None
            ),
            title,
            remainder,
            label,
            dc_creator,
            creator_kac_repr,
            issued_year,
            ddc,
            edition_of_ddc,
            kdc,
            classification_nlk,
            publisher,
            publication_place,
            place_uri,
            language_uri,
            type_of_data,
            item_number_nlk,
            local_holding,
            title_of_series,
            uniform_title_of_series,
            volume_of_series,
            bibliography,
            date_published,
            json.dumps(sameas_list, ensure_ascii=False) if sameas_list else None,
            raw_json,
        ),
    )

    if isbns:
        cur.executemany(
            "INSERT OR IGNORE INTO biblio_isbn (identifier, isbn) VALUES (?, ?)",
            [(identifier, v) for v in isbns],
        )
    if subjects:
        cur.executemany(
            "INSERT OR IGNORE INTO biblio_subject (identifier, uri) VALUES (?, ?)",
            [(identifier, v) for v in subjects],
        )
    if sameas_list:
        cur.executemany(
            "INSERT OR IGNORE INTO biblio_sameas (identifier, uri) VALUES (?, ?)",
            [(identifier, v) for v in sameas_list],
        )

    # FTS 요약 (옵션)
    if build_fts:
        series_ = _join_non_empty(
            [title_of_series or "", uniform_title_of_series or ""]
        )
        cur.execute("DELETE FROM biblio_fts WHERE identifier=?", (identifier,))
        cur.execute(
            "INSERT INTO biblio_fts (identifier, title, remainder_of_title, series, publisher, place, dc_creator) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                identifier,
                title or "",
                remainder or "",
                series_,
                publisher or "",
                publication_place or "",
                dc_creator or "",
            ),
        )


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
class TaskConfig:
    authority_files: List[str]
    authority_db: Optional[str]
    biblio_files: List[str]
    biblio_db: Optional[str]
    batch_size: int = 2000
    fast_mode: bool = False  # safer default for big files


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

    def cancel(self):
        self._cancel.set()

    def _log(self, m: str):
        self.sig_log.emit(m)

    def _process_many(self, files: List[str], db_path: str, kind: str) -> int:
        if not files:
            return 0
        if kind == "authority":
            conn = init_authority_db(db_path)
            if self.cfg.fast_mode:
                conn.executescript(
                    """
PRAGMA synchronous=OFF;
-- drop indexes to speed up bulk insert
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
            conn = init_biblio_db(db_path)
            if self.cfg.fast_mode:
                conn.executescript(
                    """
PRAGMA synchronous=OFF;
DROP INDEX IF EXISTS idx_biblio_title;
DROP INDEX IF EXISTS idx_biblio_year;
DROP INDEX IF EXISTS idx_biblio_creator_kac;
DROP INDEX IF EXISTS idx_biblio_isbn_id;
DROP INDEX IF EXISTS idx_biblio_isbn_isbn;
DROP INDEX IF EXISTS idx_biblio_subject_id;
DROP INDEX IF EXISTS idx_biblio_sameas_id;
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
                            upsert_biblio(conn, rec, build_fts=self._build_fts_inline)
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
                    else:
                        conn.executescript(
                            """
-- recreate indexes
CREATE INDEX IF NOT EXISTS idx_biblio_title        ON biblio(title);
CREATE INDEX IF NOT EXISTS idx_biblio_year         ON biblio(issued_year);
CREATE INDEX IF NOT EXISTS idx_biblio_creator_kac  ON biblio(creator_kac);
CREATE INDEX IF NOT EXISTS idx_biblio_isbn_id      ON biblio_isbn(identifier);
CREATE INDEX IF NOT EXISTS idx_biblio_isbn_isbn    ON biblio_isbn(isbn);
CREATE INDEX IF NOT EXISTS idx_biblio_subject_id   ON biblio_subject(identifier);
CREATE INDEX IF NOT EXISTS idx_biblio_sameas_id    ON biblio_sameas(identifier);
-- bulk build FTS
DELETE FROM biblio_fts;
INSERT INTO biblio_fts (identifier, title, remainder_of_title, series, publisher, place, dc_creator)
SELECT b.identifier,
       COALESCE(b.title, ''),
       COALESCE(b.remainder_of_title, ''),
       TRIM(
            COALESCE(b.title_of_series, '') ||
            CASE WHEN b.uniform_title_of_series IS NOT NULL AND b.uniform_title_of_series<>'' THEN ', '||b.uniform_title_of_series ELSE '' END
       ),
       COALESCE(b.publisher, ''),
       COALESCE(b.publication_place, ''),
       COALESCE(b.dc_creator, '')
FROM biblio b;
INSERT INTO biblio_fts(biblio_fts) VALUES('optimize');
PRAGMA synchronous=NORMAL;
"""
                        )
                except Exception as e:
                    self._log(f"[WARN] post-build optimize failed: {e}")
                finally:
                    conn.commit()
            conn.close()
        self._log(f"[✓] {kind} processed: {processed}")
        return processed

    def run(self):
        try:
            grand_total = 0
            if self.cfg.authority_files and self.cfg.authority_db:
                grand_total += self._process_many(
                    self.cfg.authority_files, self.cfg.authority_db, "authority"
                )
                if self._cancel.is_set():
                    self.sig_done.emit(False, "Canceled during authority phase")
                    return
            if self.cfg.biblio_files and self.cfg.biblio_db:
                grand_total += self._process_many(
                    self.cfg.biblio_files, self.cfg.biblio_db, "biblio"
                )
                if self._cancel.is_set():
                    self.sig_done.emit(False, "Canceled during biblio phase")
                    return
            self.sig_done.emit(True, f"Completed. Total processed: {grand_total}")
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
        self.chk_fast = QCheckBox("Turbo build (drop/rebuild indexes & FTS, sync=OFF)")
        self.btn_cancel.setEnabled(False)

        ctl = QHBoxLayout()
        ctl.addWidget(self.lbl_phase)
        ctl.addStretch(1)
        ctl.addWidget(self.chk_fast)
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

        self.worker: Optional[BuildWorker] = None

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
