# Integrated Search Desktop Project Summary

## Directory Layout
- `./` – PySide6 desktop application source; all main `.py` modules live here alongside tooling scripts.
- `assets/` – UI resources (`favicon.ico`, `loading.jpg`) used by splash screens and tab icons.
- `build/` – PyInstaller outputs (`MetaTextus/`, `Qt_TabView_Example/`) for distribution experiments.
- `Gradio/` – Legacy Gradio prototypes and JSON conversion helpers; not referenced by the current Qt app.
- `PEU/`, `QRPrint/`, `Regular/`, `backpup/` – Archived or alternate projects kept for reference; contain independent scripts and virtual environments.
- `venv/` – Local virtual environment with third-party packages (e.g., `transformers`, `PySide6`).
- Numerous date-stamped folders and `.zip` files – Historical snapshots and experiment bundles; no runtime impact unless explicitly invoked.

## Core Application & UI Shell
- `qt_main_app.py` – Entry point defining `IntegratedSearchApp` and `MainApplicationWindow`; wires the database layer, initializes tabs (`qt_TabView_*.py`), configures layout persistence (`layout_settings_manager.py`, `qt_layout_settings_manager.py`), keyboard shortcuts (`qt_shortcuts.py`), custom context menus (`qt_context_menus.py`), splash assets, and the optional `extension_api_server.py`.
- `qt_tab_template_standalone.py`, `layout_integration_example.py`, `run_template.py` – Minimal harnesses illustrating how to embed `BaseSearchTab` derivatives or integrate the layout manager without the full application shell.
- `qt_tree_menu_navigation.py`, `tree_menu_navigation.py` – Navigation utilities for tree-based tab structures; reused by tab views that expose hierarchical results.

## UI Infrastructure & Utilities
- `qt_base_tab.py` – 3.0.1 base class for all search tabs; handles threading (`SearchThread` in `qt_utils.py`), table models, filtering (`qt_proxy_models.py`), column persistence (`qt_widget_events.py`), export helpers, and detail pane rendering (`view_displays.py`). Direct relations: `ui_constants.py`, `qt_shortcuts.py`, `qt_context_menus.py`, `qt_utils.py`, `qt_Tab_configs.py`.
- `qt_Tab_configs.py` – Declarative tab metadata (column maps, search functions, editable fields) consumed by `qt_main_app.py` and individual tab classes; ties UI headers to backend search functions (`search_orchestrator.py`, `Search_KSH_Lite.py`, etc.).
- `qt_utils.py` – Shared Qt helpers (thread wrapper, exporting, URL handling, text linkification) referenced by most tab modules and the main window.
- `qt_custom_widgets.py` – Custom controls such as `TripleClickLimitedTextBrowser`, hyperlink delegates, and specialized line edits used across tabs (`qt_TabView_KSH_Lite.py`, `qt_main_app.py`).
- `qt_proxy_models.py` – Sorting/filtering proxy for table views; injected by `qt_base_tab.py`.
- `qt_widget_events.py`, `qt_widget_events - ���纻.py` – Column layout persistence, Excel-style headers, and menu helpers; the suffixed file is a backup of the same logic.
- `qt_context_menus.py` – Context menu registration for widgets; imported by `qt_main_app.py` and tab classes to provide consistent right-click actions.
- `qt_shortcuts.py` – Global shortcut registration and the F1 shortcut help dialog (`show_shortcuts_help`) invoked from the main window.
- `qt_styles.py` – Centralized stylesheet tokens and dark theme adjustments referenced by tab constructors and the settings tab.
- `ui_constants.py` – Shared typography, color, and spacing constants (alias `U`/`UI_CONSTANTS`) consumed throughout the Qt code (e.g., `qt_base_tab.py`, `qt_copy_feedback.py`).
- `view_displays.py` – Rich-text viewers and column auto-sizing helpers for detail panes; used inside `qt_base_tab.py` and `MainApplicationWindow`.
- `qt_layout_settings_manager.py`, `layout_settings_manager.py` – Persist and restore splitter geometries and window states; invoked by `qt_main_app.py` during shutdown/startup.
- `qt_copy_feedback.py` – Floating toast window confirming copy actions; triggered via `qt_widget_events.py` table handlers.
- `qt_data_transfer_manager.py` – Bridges MARC extraction output into other tabs (e.g., sends author/title data from `qt_TabView_MARC_Extractor.py` to KSH tabs and orchestrators).
- `qt_dewey_logic.py` – UI-side logic for Dewey navigation (menu commands, lazy expansion, result formatting) orchestrating worker threads and API settings.
- `qt_dewey_workers.py` – Threaded workers (search, range expansion, KSH linkage) launched by the Dewey tab through `qt_base_tab.py`.
- `qt_isni_detailed_tab.py` – Additional UI components shared with the ISNI detailed view (`qt_TabView_ISNI_Detailed.py`).
- `qt_api_settings.py`, `qt_api_settings_ui.py`, `qt_api_clients.py`, `api_settings_ui.py`, `api_clients.py` – API credential dialogs and client helpers reused between Qt tabs and external scripts (Gemini, NLK/LOD fetchers).
- `qt_api_settings_ui.py` (duplicate naming) – PySide6 UI variant kept for compatibility with other packaging targets.

## Tab Implementations
- `qt_TabView_NDL.py`, `qt_TabView_Global.py`, `qt_TabView_Western.py`, `qt_TabView_LegalDeposit.py`, `qt_TabView_AIFeed.py`, `qt_TabView_KACAuthorities.py`, `qt_TabView_BriefWorks.py`, `qt_TabView_Gemini.py`, `qt_TabView_ISNI_Detailed.py`, `qt_TabView_NLK.py`, `qt_TabView_KSH_Lite.py`, `qt_TabView_KSH_Local.py`, `qt_TabView_MARC_Extractor.py`, `qt_TabView_MARC_Editor.py`, `qt_TabView_Dewey.py`, `qt_TabView_Settings.py`, `qt_TabView_Python.py`, `qt_TabView_Example.py`, `qt_TabView_Western.py` – Concrete subclasses of `BaseSearchTab` that:
  - Build tab-specific input forms, table layouts, and delegates.
  - Invoke backend search callables from `qt_Tab_configs.py` or dedicated managers (e.g., `Search_KSH_Lite.py`, `search_orchestrator.py`, `Search_Gemini.py`).
  - Coordinate with cross-tab utilities (`qt_data_transfer_manager.py`, `qt_utils.py`, `qt_context_menus.py`).
- Each tab module directly depends on `qt_base_tab.py`, `ui_constants.py`, and the search layer relevant to its domain (e.g., `qt_TabView_KSH_Lite.py` uses `SearchQueryManager`, `qt_TabView_Dewey.py` uses `Search_Dewey.py` and `qt_dewey_workers.py`).

## Search Managers & Data Access
- `search_query_manager.py` – v3.0.0 facade combining `SearchDeweyManager` and `SearchKshManager`; other modules import this class as `SearchManager`.
- `search_common_manager.py` – Shared routines for normalizing queries, formatting KSH markup, linking Dewey labels, and orchestrating thread pools; subclassed by specialized managers.
- `search_dewey_manager.py` – DDC-specific caching, ranking heuristics, and result shaping; used by `SearchQueryManager`, `Search_Dewey.py`, and the Dewey tab.
- `search_ksh_manager.py` – KSH-focused search workflows (concept lookup, relation expansion, ranking); used by `SearchQueryManager` and `Search_KSH_Local.py`.
- `search_orchestrator.py` – Fan-out controller combining ISBN/ISNI/KAC, Western catalog, and global catalog searches; invoked by corresponding tab configs and orchestrates `Search_*` modules via `ThreadPoolExecutor`.
- `split_search_manager.py`, `search_single_word.py`, `search_query_manager.py` (alias `SearchManager`) – Supplementary helpers for parsing complex input and running multi-source queries.
- `Search_Dewey.py` – Handles the WorldCat Dewey API (OAuth token management, negative caching) and relies on `SearchQueryManager` for database lookups and ranking.
- `Search_Gemini.py` – Integrates Gemini API responses with local databases to enrich conceptual metadata before populating the Gemini tab.
- `Search_KSH_Lite.py` – Web scraper and parser for the NLK KSH portal; outputs pandas DataFrames consumed by `QtKshHyridSearchTab`. Depends on `search_query_manager.py`, `search_single_word.py`.
- `Search_KSH_Local.py` – Interfaces with the local KSH mapping database through `SearchQueryManager`.
- `Search_ISNI_Detailed.py` – Collects detailed ISNI records for the ISNI tab.
- `Search_Legal_deposit.py` – National legal deposit search routines used by the Legal Deposit tab.
- `Search_KAC_Authorities.py`, `refactor_get_ksh_entries.py` – Functions for KAC authority extraction; called by orchestrator workflows and KSH tabs.

## External Catalog Connectors
- Global/Western catalog scripts: `Search_BNE.py`, `Search_BNF.py`, `Search_CiNii.py`, `Search_Cornell.py`, `Search_DNB.py`, `Search_Google.py`, `Search_Harvard.py`, `Search_Jisc.py`, `Search_MIT.py`, `Search_Princeton.py`, `Search_UPenn.py`, `Search_Naver.py`, `Search_NDL.py`, `Search_NLK.py`. Each module encapsulates HTTP scraping or API calls for its catalog and returns result lists consumed by `search_orchestrator.py`.
- `Search_BriefWorks` functionality is handled through the orchestrator and `qt_TabView_BriefWorks.py`, tying into KAC/ISNI lookups.
- `Search_AIFeed` logic combines Gemini and catalog data via `Search_Gemini.py` and shared managers.

## Database, Data Pipelines & Tooling
- `database_manager.py` – v2.2.0 manager for `nlk_concepts.sqlite`, `kdc_ddc_mapping.db`, `glossary.db`, and `dewey_cache.db`; provides PRAGMA tuning, FTS5 maintenance, cache writers, and vector search hooks. Used everywhere a `SearchQueryManager` instance is required.
- `db_perf_tweaks.py` – SQLite PRAGMA helpers and warm-up routines invoked by `qt_main_app.py` and `database_manager.py`.
- `build_kac_authority_and_biblio_db.py`, `Final_build_kac_authority_and_biblio_db.py` – Scripts for constructing combined KAC/bibliographic databases; leverage `database_manager.py`.
- `build_vector_db.py` – Generates FAISS indices for DDC embeddings, extending `DatabaseManager`.
- `manage_ddc_index.py`, `Final manage_ddc_index.py`, `migrate_ddc_schema.py`, `Final migrate_ddc_schema.py`, `Final import_alt_terms.py` – Maintenance scripts for DDC schema evolution and index management.
- `gemini.py` – Batch script to merge KSH labels into mapping databases using both mapping and concept stores.
- `mark_generator.py` – Produces MARC markers or placeholders for data export; used by MARC extractor/editor tooling.
- `marc_parser.py` – MARC parsing utilities backing the MARC extractor and data transfer manager.
- `dewey_cache_bot.py`, `dewey_context_menu.py`, `dewey_copy_manager.py`, `dewey_logic.py`, `dewey_workers.py` – Additional Dewey automation helpers, many superseded by the newer `qt_dewey_*` modules but retained for scripting contexts.
- `path_utils.py`, `preset_manager.py` – Helper modules for locating project assets and persisting user presets; referenced by settings tooling.
- `ConceptsGUI.py` – Standalone GUI for concept database inspection; useful when debugging `database_manager.py`.
- `hook-hanja.py` – Utility script (likely PyInstaller hook) ensuring Hanja resources are bundled.
- `layout_settings_manager.py` – Shared persistence helper also callable outside Qt contexts.

## API & Integration Layers
- `extension_api_server.py` – Flask-based local server exposing KSH search endpoints for browser extensions; started from `qt_main_app.py`.
- `qt_api_clients.py`, `api_clients.py` – REST client wrappers (NLK, Gemini, LC, etc.) reused by `search_orchestrator.py` and external tooling.
- `Search_Gemini.py`, `gemini.py`, `Search_AIFeed` interactions – Coordinate AI-assisted metadata enrichment.
- `test_api_server.py` – Integration test harness targeting `extension_api_server.py`.

## Diagnostics, Tests & Performance Utilities
- `check_concept_fts5.py`, `check_fts5.py`, `check_sqlite_version.py` – One-off diagnostics verifying SQLite FTS features and environment compatibility.
- `test_concept_speed.py`, `test_final_performance.py`, `test_fts5_speed.py`, `test_api_server.py` – Performance measurement scripts for database and API operations.
- `test_final_performance.py`, `test_api_server.py` – Scenario tests for end-to-end runs (database warm-up, API endpoints).
- `search_dewey_manager.py` and `Search_Dewey.py` include extensive logging toggles for profiling.

## Legacy & Reference Scripts
- `Final 0913 concept_json_to_SQLite_GUI_Final V2.0 - Update ��� �߰�.py`, `Final 0914 PNU_KDC_DDC_Mapper_SQLite_with_KSH.py`, `Final 0914 Send KSH Labels from Concept DB to Mapping DB by GPT ���� ���� ����.py`, `Final import_alt_terms.py`, `Final manage_ddc_index.py`, `Final migrate_ddc_schema.py` – Preserved “final” snapshots of earlier pipelines for traceability.
- `qt_widget_events - ���纻.py`, `qt_TabView_Example.py`, `mock_backend.py`, `run_template.py` – Sandbox or mock implementations retained for regression comparison.
- Date-stamped scripts under `PEU/`, `Regular/`, etc., mirror older iterations of the KDC/DDC mapper and support tools.

## Key Relationships & Data Flow
- UI flow: `qt_main_app.py` → tab classes (`qt_TabView_*.py`) → `SearchQueryManager` → `DatabaseManager` / `Search_*` connectors → results rendered via `qt_base_tab.py`.
- Layout persistence: `qt_main_app.py` & tabs → `qt_layout_settings_manager.py` / `layout_settings_manager.py` → `glossary.db`.
- Dewey workflows: `qt_TabView_Dewey.py` → `qt_dewey_logic.py` / `qt_dewey_workers.py` → `Search_Dewey.py` → `SearchQueryManager` → `database_manager.py`.
- KSH workflows: `qt_TabView_KSH_Lite.py` → `Search_KSH_Lite.py` → `SearchQueryManager` → `database_manager.py`; KSH Local tab bypasses web scraping and queries mapping data via `search_ksh_manager.py`.
- Western/Global workflows: `qt_TabView_Global.py` / `qt_TabView_Western.py` → `search_orchestrator.py` → individual `Search_*` modules → aggregated results normalized by `search_common_manager.py`.
- MARC workflows: `qt_TabView_MARC_Extractor.py` → `marc_parser.py` / `qt_data_transfer_manager.py` → downstream tabs (`QtKshHyridSearchTab`, etc.).
- External integration: optional `extension_api_server.py` shares `SearchQueryManager` with browser extensions; AI feed uses `Search_Gemini.py` and `gemini.py`.

## Recent Changes (Oct 2025)
- 2025-10-24 – `Search_KSH_Lite.py` and `search_ksh_manager.py` updated with enhanced ranking (DDC frequency, relation expansion) and tighter integration with `SearchQueryManager`.
- 2025-10-20 – Major refactor splitting `SearchQueryManager` into `search_common_manager.py`, `search_dewey_manager.py`, `search_ksh_manager.py`; concurrent updates to `qt_TabView_Dewey.py`, `qt_TabView_Settings.py`, `qt_styles.py`, and KSH UI aligning with new managers.
- 2025-10-19 – `database_manager.py` v2.2.0 introduces FTS5-backed views and background writer threads; Dewey search logic optimized with covering indexes.
- 2025-10-18 – `qt_main_app.py` gains splitter persistence across all tabs and ensures glossary-backed storage; close-event cleanup hardened to stop background threads and servers.
- 2025-10-17 – Dewey and MARC extractor detail panes restored, DDC search threads parallelized, tree auto-expansion and related-concept rendering tuned, DDC label/count wiring verified across tabs, and KSH Hybrid UI cleaned up; ongoing work continues on triple-click selection behavior noted in historic discussion (`이전 대화.md`).
- Ongoing – Performance test scripts (`test_final_performance.py`, `check_concept_fts5.py`) refreshed mid-October to validate new indexing strategies.
