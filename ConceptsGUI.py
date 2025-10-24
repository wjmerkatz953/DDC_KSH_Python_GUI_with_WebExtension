# ConceptsGUI.py
# -*- coding: utf-8 -*-
"""
NLK Concepts GUI
- SQLite에 적재된 NLK 주제(DB)에서 altLabel/prefLabel로 검색하고
  결과를 tksheet 표로 보여주는 간단 GUI.
- 요구 반영:
  * 자동 DB 연결(기본 경로 시도 + 필요시 파일 선택)
  * altLabel 한국어/영어 검색
  * 중복 altLabel 제거(동일 용어는 @fr 우선)
  * Subject/Related/Broader/Narrower 모두 "▼a주제명▼0KSH코드▲" 형식으로 표기 (nlk: 접두어 제거)
  * 우선어(prefLabel) 별도 컬럼
  * KSH 코드 단독 컬럼 제거(형식에 포함되므로)
  * 값 검색은 altLabel + prefLabel 동시 검색 (옵션 토글 가능)
- 실행:
    pip install tksheet
    python ConceptsGUI.py
"""
import re, os, sqlite3, webbrowser, sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tksheet import Sheet
except ImportError as e:
    raise SystemExit("tksheet가 설치되어 있지 않습니다. 먼저 'pip install tksheet'를 실행하세요.") from e

APP_TITLE = "NLK Concepts GUI"
DEFAULT_DB_CANDIDATES = [
    os.path.join(os.getcwd(), "nlk_concepts.sqlite"),
    os.path.expanduser("~/Downloads/nlk_concepts.sqlite"),
    os.path.expanduser("~/nlk_concepts.sqlite"),
]

# --- 유틸 ---
RX_LANG = re.compile(r"@([a-z]{2,3})$", re.IGNORECASE)
def strip_lang_tag(s: str) -> str:
    return RX_LANG.sub("", s).strip()

def pick_dedup(values):
    """동일 용어(언어태그 제거 기준) 중복 제거. '@fr'가 있으면 우선 선택."""
    by_key = {}
    for v in values:
        key = strip_lang_tag(v).lower()
        cur = by_key.get(key)
        if cur is None:
            by_key[key] = v
        else:
            if v.lower().endswith("@fr") and not cur.lower().endswith("@fr"):
                by_key[key] = v
    return list(by_key.values())

def extract_ksh_from_id(concept_id: str) -> str:
    if not concept_id:
        return ""
    cid = concept_id.split(":")[-1]
    m = re.search(r"(KSH\d+)", cid, re.IGNORECASE)
    return m.group(1).upper() if m else cid

def fmt_subject(pref_label: str, concept_id: str) -> str:
    return f"▼a{pref_label}▼0{extract_ksh_from_id(concept_id)}▲"

def apply_theme(root: tk.Tk):
    style = ttk.Style(root)
    for candidate in ("vista","xpnative","clam"):
        if candidate in style.theme_names():
            try:
                style.theme_use(candidate); break
            except Exception:
                pass
    style.configure(".", font=("Segoe UI", 10))
    style.configure("TButton", padding=(10,6))
    style.configure("TEntry", padding=(4,4))
    style.configure("TCombobox", padding=(4,4))

# --- 스키마 탐지 ---
class Schema:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.literal_table = None
        self.uri_table = None
        self.cols = {}
        self.detect()

    def detect(self):
        cur = self.conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
        tbls = cur.fetchall()
        for name, sql in tbls:
            low = name.lower()
            if any(k in low for k in ("literal", "literals", "literal_values")):
                self.literal_table = name
                self.cols[name] = self._cols(name)
            if any(k in low for k in ("uri", "uris", "uri_relations", "relations")):
                self.uri_table = name
                self.cols[name] = self._cols(name)
        if not self.literal_table and tbls:
            self.literal_table = tbls[0][0]
            self.cols[self.literal_table] = self._cols(self.literal_table)
        if not self.uri_table and len(tbls) >= 2:
            self.uri_table = tbls[1][0]
            self.cols[self.uri_table] = self._cols(self.uri_table)

    def _cols(self, table):
        cur = self.conn.execute(f"PRAGMA table_info({table})")
        return [r["name"] if isinstance(r, sqlite3.Row) else r[1] for r in cur.fetchall()]

# --- DB 쿼리 계층 ---
class ConceptsDB:
    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.schema = Schema(self.conn)
        self._ensure_indexes()

    def _ensure_indexes(self):
        c = self.conn.cursor()
        lt = self.schema.literal_table
        ut = self.schema.uri_table
        lcols = self.schema.cols.get(lt, [])
        ucols = self.schema.cols.get(ut, [])
        def idx(table, name, cols):
            try:
                c.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({', '.join(cols)})")
            except Exception:
                pass
        if lt:
            cand = [x for x in ("concept_id","subject_id","s","id") if x in lcols]
            pred = [x for x in ("pred","predicate","p") if x in lcols]
            text = [x for x in ("text","value","literal","label") if x in lcols]
            lang = [x for x in ("lang","langtag","language") if x in lcols]
            if cand and text: idx(lt, f"ix_{lt}_{cand[0]}_{text[0]}", [cand[0], text[0]])
            if pred and text: idx(lt, f"ix_{lt}_{pred[0]}_{text[0]}", [pred[0], text[0]])
            if text: idx(lt, f"ix_{lt}_{text[0]}", [text[0]])
            if lang: idx(lt, f"ix_{lt}_{lang[0]}", [lang[0]])
        if ut:
            s = [x for x in ("source","source_id","s","subject_id") if x in ucols]
            p = [x for x in ("pred","predicate","p") if x in ucols]
            t = [x for x in ("target","target_id","t","object_id") if x in ucols]
            if s and p: idx(ut, f"ix_{ut}_{s[0]}_{p[0]}", [s[0], p[0]])
            if s and t: idx(ut, f"ix_{ut}_{s[0]}_{t[0]}", [s[0], t[0]])
        self.conn.commit()

    def _literal_cols(self):
        lt = self.schema.literal_table
        lcols = self.schema.cols.get(lt, [])
        col = {
            "cid": next((x for x in ("concept_id","subject_id","s","id") if x in lcols), None),
            "pred": next((x for x in ("pred","predicate","p") if x in lcols), None),
            "text": next((x for x in ("text","value","literal","label") if x in lcols), None),
            "lang": next((x for x in ("lang","langtag","language") if x in lcols), None),
        }
        return lt, col

    def _uri_cols(self):
        ut = self.schema.uri_table
        ucols = self.schema.cols.get(ut, [])
        col = {
            "s": next((x for x in ("source","source_id","s","subject_id") if x in ucols), None),
            "p": next((x for x in ("pred","predicate","p") if x in ucols), None),
            "t": next((x for x in ("target","target_id","t","object_id") if x in ucols), None),
        }
        return ut, col

    def find_concepts_by_label(self, q: str, in_alt=True, in_pref=True, dedup=True):
        lt, L = self._literal_cols()
        if not lt or not L["cid"] or not L["text"] or not L["pred"]:
            raise RuntimeError("리터럴 테이블 스키마를 인식할 수 없습니다.")
        preds = []
        if in_alt: preds.append("altLabel")
        if in_pref: preds.extend(["prefLabel","label"])
        ph = ",".join("?"*len(preds))
        sql = f"SELECT {L['cid']} AS cid, {L['text']} AS text FROM {lt} WHERE {L['pred']} IN ({ph}) AND {L['text']} LIKE ?"
        rows = self.conn.execute(sql, (*preds, f"%{q}%")).fetchall()
        if not dedup:
            return list({r["cid"] for r in rows})
        by_cid = {}
        for r in rows:
            by_cid.setdefault(r["cid"], []).append(r["text"])
        out = []
        for cid, texts in by_cid.items():
            _ = pick_dedup(texts)
            out.append(cid)
        return list(dict.fromkeys(out))

    def get_pref_label(self, cid: str):
        lt, L = self._literal_cols()
        rows = self.conn.execute(
            f"SELECT {L['text']} AS text, {L.get('lang','NULL')} AS lang FROM {lt} WHERE {L['cid']}=? AND {L['pred']} IN ('prefLabel','label')",
            (cid,)
        ).fetchall()
        if not rows:
            return ""
        def lang_of(text, row_lang):
            if row_lang:
                return (row_lang or "").lower()
            m = RX_LANG.search(text)
            return (m.group(1).lower() if m else "")
        ranked = sorted(rows, key=lambda r: {"ko":0, "en":1}.get(lang_of(r["text"], r["lang"]), 2))
        return strip_lang_tag(ranked[0]["text"])

    def get_related_pref_labels(self, cid: str, pred_name: str):
        ut, U = self._uri_cols()
        if not ut or not U["s"] or not U["t"] or not U["p"]:
            return []
        rows = self.conn.execute(
            f"SELECT {U['t']} AS target FROM {ut} WHERE {U['s']}=? AND {U['p']}=?",
            (cid, pred_name)
        ).fetchall()
        out = []
        for r in rows:
            tcid = r["target"]
            pl = self.get_pref_label(tcid)
            out.append((tcid, pl))
        return out

# --- GUI ---
COLUMNS = ["Subject(형식)","우선어(prefLabel)","관련어(related)","상위어(broader)","하위어(narrower)","원시ID"]

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        apply_theme(self)
        self.title(APP_TITLE)
        self.geometry("1280x780")
        self.minsize(1100, 680)

        self.db: ConceptsDB|None = None
        self.db_path = tk.StringVar(value="(미연결)")

        bar = ttk.Frame(self, padding=8); bar.pack(fill="x")
        ttk.Label(bar, text="DB:").pack(side="left")
        ttk.Label(bar, textvariable=self.db_path, foreground="#2c7").pack(side="left", padx=(6,12))
        ttk.Button(bar, text="DB 선택…", command=self.choose_db).pack(side="left", padx=(0,12))

        ttk.Label(bar, text="검색어:").pack(side="left")
        self.q_var = tk.StringVar()
        ent = ttk.Entry(bar, textvariable=self.q_var, width=28)
        ent.pack(side="left", padx=(6,6))
        ent.bind("<Return>", lambda e: self.run_search())

        self.in_alt = tk.BooleanVar(value=True)
        self.in_pref = tk.BooleanVar(value=True)
        self.dedup = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="altLabel", variable=self.in_alt).pack(side="left")
        ttk.Checkbutton(bar, text="prefLabel", variable=self.in_pref).pack(side="left")
        ttk.Checkbutton(bar, text="중복제거(@fr 우선)", variable=self.dedup).pack(side="left", padx=(6,0))
        ttk.Button(bar, text="검색", command=self.run_search).pack(side="left", padx=(8,0))

        ttk.Button(bar, text="복사", command=self.copy_selection).pack(side="right")
        ttk.Button(bar, text="CSV 저장", command=self.export_csv).pack(side="right", padx=(0,8))

        self.sheet = Sheet(self,
                           data=[],
                           headers=COLUMNS,
                           show_row_index=True,
                           show_x_scrollbar=True,
                           show_y_scrollbar=True)
        self.sheet.enable_bindings([
            "single_select","row_select","column_select","drag_select",
            "copy","rc_select","arrowkeys","double_click",
            "right_click_popup_menu","column_width_resize","double_click_column_resize",
        ])
        self.sheet.pack(fill="both", expand=True, padx=8, pady=(0,8))

        self.sheet.popup_menu_add_command("KSH 상세(검색)", self.open_ksh_search)
        self.sheet.extra_bindings("double_click", lambda e: self.open_ksh_search())

        self.status = tk.StringVar(value="준비")
        ttk.Label(self, textvariable=self.status, anchor="w").pack(fill="x", padx=8, pady=(0,8))

        self.auto_connect_db()

    def auto_connect_db(self):
        for p in DEFAULT_DB_CANDIDATES:
            if os.path.exists(p):
                try:
                    self.db = ConceptsDB(p)
                    self.db_path.set(p)
                    self.status.set(f"연결됨: {p}")
                    return
                except Exception:
                    continue
        self.status.set("DB 미연결 — 'DB 선택…'으로 파일을 선택하세요.")

    def choose_db(self):
        path = filedialog.askopenfilename(
            title="NLK Concepts SQLite 선택",
            filetypes=[("SQLite", "*.sqlite;*.db"), ("All files", "*.*")]
        )
        if not path: return
        try:
            self.db = ConceptsDB(path)
            self.db_path.set(path)
            self.status.set(f"연결됨: {path}")
        except Exception as e:
            messagebox.showerror("DB 오류", str(e))

    def run_search(self):
        if not self.db:
            messagebox.showwarning("검색", "먼저 DB를 연결하세요."); return
        q = self.q_var.get().strip()
        if not q:
            messagebox.showinfo("검색", "검색어를 입력하세요."); return
        try:
            cids = self.db.find_concepts_by_label(q, in_alt=self.in_alt.get(), in_pref=self.in_pref.get(), dedup=self.dedup.get())
            self._populate_rows(cids)
        except Exception as e:
            messagebox.showerror("검색 오류", str(e))

    def _populate_rows(self, cids):
        rows = []
        for cid in cids:
            pref = self.db.get_pref_label(cid)
            subj = fmt_subject(pref, cid)

            rels = self.db.get_related_pref_labels(cid, "related")
            broa = self.db.get_related_pref_labels(cid, "broader")
            narr = self.db.get_related_pref_labels(cid, "narrower")

            rel_txt = ", ".join(fmt_subject(pl, tcid) for tcid, pl in rels if pl)
            bro_txt = ", ".join(fmt_subject(pl, tcid) for tcid, pl in broa if pl)
            nar_txt = ", ".join(fmt_subject(pl, tcid) for tcid, pl in narr if pl)

            rows.append([subj, pref, rel_txt, bro_txt, nar_txt, cid])

        self.sheet.headers(COLUMNS)
        self.sheet.set_sheet_data(rows, reset_col_positions=True, reset_row_positions=True)
        self.status.set(f"{len(rows)}건 표시")

    def open_ksh_search(self):
        sel = self.sheet.get_currently_selected()
        if not sel: return
        r, c = sel
        if r is None: return
        code_str = self.sheet.get_cell_data(r, 0)  # Subject 형식 안에 KSH 포함
        m = re.search(r"▼0(KSH\d+)▲", code_str)
        if not m:
            messagebox.showinfo("검색", "KSH 코드를 찾을 수 없습니다."); return
        ksh = m.group(1)
        webbrowser.open(f"https://www.google.com/search?q={ksh}", new=2)

    def copy_selection(self):
        selected = self.sheet.get_selected_cells(get_cells_as_rows=True)
        if selected:
            rows_map = {}
            for r, c in selected:
                rows_map.setdefault(r, {})[c] = self.sheet.get_cell_data(r, c)
            ordered_rows = []
            for r in sorted(rows_map.keys()):
                cols = rows_map[r]
                ordered_rows.append([cols.get(c, "") for c in sorted(cols.keys())])
            text = "\n".join("\t".join(map(str, row)) for row in ordered_rows)
        else:
            data = self.sheet.get_sheet_data(return_copy=True)
            text = "\n".join("\t".join(map(str, row)) for row in data)
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("복사", "클립보드로 복사했습니다.")

    def export_csv(self):
        import csv
        path = filedialog.asksaveasfilename(
            title="CSV로 저장",
            defaultextension=".csv",
            initialfile="concepts_results.csv",
            filetypes=[("CSV","*.csv"), ("All files","*.*")]
        )
        if not path: return
        data = self.sheet.get_sheet_data(return_copy=True)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(COLUMNS)
            w.writerows(data)
        messagebox.showinfo("저장", f"저장 완료: {path}")

def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
