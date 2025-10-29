(() => {
  // === 설정 ===
  const AUTO_SHOW = false;
  const ONLY_650_DEFAULT = true;
  const PANEL_ID = "ksh-panel";

  // ================= 공통 유틸 =================
  const $ = (sel, root = document) => root.querySelector(sel);
  const $all = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // ================= 서식/타겟 판별 유틸 =================
  function isSubfieldSpan(el) {
    return el?.nodeType === 1 &&
      el.matches('span.ikc-marc-subfields[contenteditable="true"][data-marc="subfields"]');
  }

  function is650Span(el) {
    if (!isSubfieldSpan(el)) return false;
    const li = el.closest('li.ikc-marc-field');
    const tag = li?.querySelector('input[data-marc="tag"]')?.value?.trim();
    return tag === "650";
  }

  function findAllSubfieldSpans() {
    return $all('span.ikc-marc-subfields[contenteditable="true"][data-marc="subfields"]');
  }

  function findAll650SubfieldSpans() {
    const lis = $all('li.ikc-marc-field');
    const out = [];
    for (const li of lis) {
      const tag = li.querySelector('input[data-marc="tag"]')?.value?.trim();
      if (tag === "650") {
        const sp = li.querySelector('span.ikc-marc-subfields[contenteditable="true"][data-marc="subfields"]');
        if (sp) out.push(sp);
      }
    }
    return out;
  }

  // ======== 다른 모듈에서 사용할 삽입 로직 (전역 IIFE 스코프로 이동) ========
  function insertTextToSpan(el, text) {
    el.focus();
    el.textContent = text;
    el.dispatchEvent(new InputEvent("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // -------------------
  // [추가된 기능] 082 필드에서 DDC 번호를 읽는 헬퍼 함수
  function read082Field() {
    const fields082 = $all('li.ikc-marc-field');
    let ddcCode = '';

    for (const field of fields082) {
      const tagInput = field.querySelector('input[data-marc="tag"]');
      if (tagInput && tagInput.value.trim() === '082') {
        const subfieldSpan = field.querySelector('span.ikc-marc-subfields[data-marc="subfields"]');
        if (subfieldSpan) {
          const text = subfieldSpan.textContent || '';
          // ▼a 뒤의 숫자 (점 포함)를 찾습니다.
          const match = text.match(/▼a\s*(\d+(\.\d+)?)/i);
          if (match) {
            ddcCode = match[1].trim();
            break;
          }
        }
      }
    }
    return ddcCode;
  }
  // -------------------

  // ============== 패널 생성 ==============
  function buildKshPanel(root) {
    // 컨테이너
    Object.assign(root.style, {
      position: "fixed",
      right: "0",
      bottom: "40px",
      width: "400px",
      maxHeight: "900px",
      overflowY: "auto",
      background: "white",
      borderTop: "1px solid #d0d0d0",
      boxShadow: "0 -8px 24px rgba(0,0,0,0.08)",
      zIndex: "2147483647",
      fontSize: "13px",
      lineHeight: "1.4",
      display: "flex",
      flexDirection: "column",
      padding: "8px 12px",
      gap: "8px",
      borderRadius: "10px 0 0 0"
    });

    // 특정 모달 감지 및 z-index 조절
    function checkModalVisibility() {
      const modalSelectors = [
        'span.k-window-title',
        'h1.ikc-toolbar-header[flex=""]'
      ];

      let hasVisibleModal = false;

      for (const selector of modalSelectors) {
        const elements = document.querySelectorAll(selector);
        for (const element of elements) {
          const style = window.getComputedStyle(element);
          const parentStyle = element.parentElement ? window.getComputedStyle(element.parentElement) : null;

          if (style.display !== 'none' && style.visibility !== 'hidden' &&
            (!parentStyle || (parentStyle.display !== 'none' && parentStyle.visibility !== 'hidden'))) {
            hasVisibleModal = true;
            break;
          }
        }
        if (hasVisibleModal) break;
      }

      root.style.zIndex = hasVisibleModal ? "999" : "1000";
    }

    const observer = new MutationObserver(checkModalVisibility);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['style', 'class']
    });

    // 초기 체크
    checkModalVisibility();

    // === 1. 프리셋 섹션 (맨 위) ===
    const presetSection = document.createElement("div");
    presetSection.style.borderBottom = "2px solid #007acc";
    presetSection.style.paddingBottom = "8px";
    presetSection.style.marginBottom = "8px";

    const presetTitle = document.createElement("div");
    presetTitle.textContent = "🎯 KSH 프리셋 for PNU Library 자료조직팀 by InnovaNex";
    presetTitle.style.fontWeight = "bold";
    presetTitle.style.color = "#007acc";
    presetTitle.style.marginBottom = "8px";
    presetSection.appendChild(presetTitle);

    // 프리셋 버튼들
    const presetButtonsContainer = document.createElement("div");
    presetButtonsContainer.id = "ksh-presets";
    Object.assign(presetButtonsContainer.style, {
      height: "100px",
      overflowY: "auto",
      border: "1px solid #ccc",
      padding: "8px",
      display: "flex",
      flexWrap: "wrap",
      gap: "4px",
      alignContent: "flex-start",
      background: "#f9f9f9"
    });
    presetSection.appendChild(presetButtonsContainer);

    // 프리셋 컨트롤
    const presetControls = document.createElement("div");
    presetControls.style.display = "flex";
    presetControls.style.gap = "6px";
    presetControls.style.marginTop = "8px";
    presetControls.style.flexWrap = "wrap";

    const inName = document.createElement("input");
    inName.placeholder = "프리셋 이름";
    inName.style.width = "110px";  // 원하는 픽셀 값으로 조정

    const btnSave = document.createElement("button");
    btnSave.textContent = "저장";
    const btnUpdate = document.createElement("button");
    btnUpdate.textContent = "수정";
    const btnDelete = document.createElement("button");
    btnDelete.textContent = "삭제";
    const btnImport = document.createElement("button");
    btnImport.textContent = "Import";
    const btnExport = document.createElement("button");
    btnExport.textContent = "Export";

    const fileIn = document.createElement("input");
    fileIn.type = "file";
    fileIn.accept = "application/json";
    fileIn.style.display = "none";

    presetControls.append(inName, btnSave, btnUpdate, btnDelete, btnImport, btnExport, fileIn);
    presetSection.appendChild(presetControls);
    root.appendChild(presetSection);

    // -------------------
    // === 1-2. 통합 검색 섹션 ===
    const searchSection = document.createElement("div");
    Object.assign(searchSection.style, {
      padding: "8px 0",
      display: "flex",
      alignItems: "center",
      gap: "8px",
      borderBottom: "1px solid #eee",
      marginBottom: "8px"
    });

    const searchInput = document.createElement("input");
    searchInput.placeholder = "DDC/KSH 검색...";
    searchInput.id = "panel-search-input"; // 고유 ID 부여
    Object.assign(searchInput.style, {
      flexGrow: "1",
      padding: "6px",
      border: "1px solid #ddd",
      borderRadius: "3px"
    });

    const searchBtn = document.createElement("button");
    searchBtn.textContent = "검색";
    Object.assign(searchBtn.style, {
      padding: "5px 10px",
      background: "#007bff",
      color: "white",
      border: "none",
      borderRadius: "3px",
      cursor: "pointer"
    });

    const openSearchBtn = document.createElement("button");
    openSearchBtn.textContent = "열기";
    Object.assign(openSearchBtn.style, {
      padding: "5px 10px",
      background: "#28a745",
      color: "white",
      border: "none",
      borderRadius: "3px",
      cursor: "pointer"
    });

    const closeSearchBtn = document.createElement("button");
    closeSearchBtn.textContent = "닫기";
    Object.assign(closeSearchBtn.style, {
      padding: "5px 10px",
      background: "#6c757d",
      color: "white",
      border: "none",
      borderRadius: "3px",
      cursor: "pointer"
    });

    // -------------------
    // [추가된 기능] 082 버튼 추가
    const btn082 = document.createElement("button");
    btn082.textContent = "082";
    Object.assign(btn082.style, {
      padding: "5px 10px",
      background: "#ffc107", // 노란색 계열
      color: "black",
      border: "none",
      borderRadius: "3px",
      cursor: "pointer"
    });

    // 082 버튼 클릭 핸들러
    btn082.onclick = () => {
      const ddcCode = read082Field();
      if (ddcCode) {
        searchInput.value = ddcCode;
        triggerSearch(); // 082 코드를 읽어온 후 바로 검색 실행
      } else {
        searchInput.value = '';
        alert('082 필드에서 DDC 번호를 찾을 수 없습니다.');
      }
    };
    // -------------------    

    // 검색 실행 함수
    const triggerSearch = () => {
      const query = searchInput.value.trim();
      if (query) {
        // search-addon.js에 검색 요청 메시지 전송
        chrome.runtime.sendMessage({ type: "SEARCH_FROM_PANEL", text: query });
      }
    };

    // 이벤트 리스너 연결
    searchBtn.onclick = triggerSearch;
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        triggerSearch();
      }
    });
    openSearchBtn.onclick = () => {
      // search-addon.js에 패널 열기 요청 메시지 전송
      chrome.runtime.sendMessage({ type: "SEARCH_TOGGLE_PANEL" });
    };
    closeSearchBtn.onclick = () => {
      // search-addon.js에 닫기 요청 메시지 전송
      chrome.runtime.sendMessage({ type: "CLOSE_SEARCH_PANEL" });
    };

    // -------------------
    // 082 버튼을 검색 섹션에 추가
    searchSection.append(searchInput, searchBtn, btn082, openSearchBtn, closeSearchBtn);
    root.appendChild(searchSection);
    // -------------------

    // 닫기 버튼
    const closeBtn = document.createElement("button");
    closeBtn.textContent = "✕";
    closeBtn.onclick = () => {
      root.style.display = "none";
      // 토글 상태에 따라 체크박스 해제 여부 결정
      const shouldClear = $("#ksh-clear-on-close").checked;
      if (shouldClear) {
        const checkboxes = $all('.ksh-item-checkbox', listBox);
        checkboxes.forEach(cb => {
          cb.dataset.checked = "false";
          cb.textContent = "☐";
        });
      }
    };

    Object.assign(closeBtn.style, {
      position: "absolute",
      top: "8px",
      right: "13px",
      background: "#ff4757",
      color: "white",
      border: "none",
      borderRadius: "4px",
      padding: "4px 8px",
      cursor: "pointer",
      fontSize: "10px",
      zIndex: "10000"
    });
    root.appendChild(closeBtn);

    // === 2. 헤더 ===
    const header = document.createElement("div");
    header.style.display = "flex";
    header.style.alignItems = "center";
    header.style.gap = "12px";

    const title = document.createElement("div");
    title.textContent = "📋 KSH 후보 붙여넣기";
    title.style.fontWeight = "bold";
    title.style.color = "#007acc";

    const headerRight = document.createElement("div");
    headerRight.style.display = "flex";
    headerRight.style.alignItems = "center";
    headerRight.style.gap = "8px";

    const only650Wrap = document.createElement("label");
    const only650Chk = document.createElement("input");
    only650Chk.type = "checkbox";
    only650Chk.checked = ONLY_650_DEFAULT;
    only650Chk.id = "ksh-only650";
    only650Wrap.appendChild(only650Chk);
    only650Wrap.append(" 650 필드만");

    const clearOnCloseWrap = document.createElement("label");
    const clearOnCloseChk = document.createElement("input");
    clearOnCloseChk.type = "checkbox";
    clearOnCloseChk.checked = true; // 기본값: 닫을 때 해제
    clearOnCloseChk.id = "ksh-clear-on-close";
    clearOnCloseWrap.appendChild(clearOnCloseChk);
    clearOnCloseWrap.append(" 닫을 때 해제");
    clearOnCloseWrap.style.fontSize = "12px";

    headerRight.append(only650Wrap, clearOnCloseWrap);
    header.append(title, headerRight);
    root.appendChild(header);

    // === 3. 입력창 ===
    const ta = document.createElement("textarea");
    ta.id = "ksh-input";
    ta.rows = 6;
    ta.placeholder = "여기에 후보 문자열을 줄바꿈으로 붙여넣으세요. (컴마/세미콜론으로 구분된 것도 자동 정제)";
    ta.style.width = "100%";
    ta.style.boxSizing = "border-box";
    root.appendChild(ta);

    // === 4. 설명 ===
    const tips = document.createElement("div");
    tips.style.color = "#666";
    tips.style.fontSize = "12px";
    tips.innerHTML =
      "· '현재 칸에 1개 삽입'은 <b>지금 커서가 깜빡이는 칸</b>에 들어갑니다.<br/>" +
      "· '체크된 항목 일괄삽입'은 <b>☑ 체크된 항목만</b> 삽입합니다.";
    root.appendChild(tips);

    // === 5. 버튼줄 ===
    const buttonBar = document.createElement("div");
    buttonBar.id = "ksh-action-buttons"; // [수정] 고유 ID 부여
    buttonBar.style.display = "flex";
    buttonBar.style.gap = "8px";
    buttonBar.style.flexWrap = "wrap";

    const btnInsertCurrent = document.createElement("button");
    btnInsertCurrent.textContent = "전체 삽입";
    const btnFillBatch = document.createElement("button");
    btnFillBatch.textContent = "체크 삽입";
    const btnSelectAll = document.createElement("button");
    btnSelectAll.textContent = "전체 선택";
    const btnDeselectAll = document.createElement("button");
    btnDeselectAll.textContent = "전체 해제";
    const btnClearAll = document.createElement("button");
    btnClearAll.textContent = "목록 삭제";

    buttonBar.append(btnInsertCurrent, btnFillBatch, btnSelectAll, btnDeselectAll, btnClearAll);
    root.appendChild(buttonBar);

    // === 6. 리스트 ===
    const listBox = document.createElement("div");
    listBox.id = "ksh-list";
    Object.assign(listBox.style, {
      display: "flex",
      flexDirection: "column",
      gap: "1px",
      borderTop: "1px solid #eee",
      paddingTop: "8px",
      maxHeight: "300px",
      overflowY: "auto"
    });
    root.appendChild(listBox);

    // -------------------
    // article-processor.js와 같은 다른 모듈을 초기화합니다.
    if (window.initArticleProcessor) {
      window.initArticleProcessor(root);
    }
    // -------------------

    function normalizeInputToLines(raw) {
      if (!raw) return [];
      let s = raw
        .replace(/▲\s*[;,]\s*/g, "▲\n")
        .replace(/[;,]\s*(?=▼a)/g, "\n")
        .replace(/▲\s*\n\s*/g, "▲\n");

      const lines = s.split(/\r?\n/).map(v => v.trim());

      // 중복 제거 로직 (빈 줄은 예외 처리)
      const uniqueLines = [];
      const seenLines = new Set();

      for (const line of lines) {
        // 빈 줄은 중복 체크 없이 그대로 추가
        if (line === "") {
          uniqueLines.push(line);
        } else {
          // 빈 줄이 아닌 경우에만 중복 체크
          if (!seenLines.has(line)) {
            seenLines.add(line);
            uniqueLines.push(line);
          }
        }
      }

      // 중복이 제거되었다면 알림 (빈 줄 제외하고 계산)
      const nonEmptyOriginal = lines.filter(line => line !== "").length;
      const nonEmptyUnique = uniqueLines.filter(line => line !== "").length;
      if (nonEmptyOriginal !== nonEmptyUnique) {
        const removedCount = nonEmptyOriginal - nonEmptyUnique;
        console.log(`중복 항목 ${removedCount}개가 제거되었습니다.`);
      }

      return uniqueLines;
    }

    function renderList(lines, preserveCheckedState = []) {
      listBox.innerHTML = "";
      lines.forEach((line, idx) => {
        const row = document.createElement("div");
        Object.assign(row.style, {
          display: "flex",
          alignItems: "center",
          gap: "6px",
          padding: "0px 0"
        });

        // 체크박스 (문자 아이콘)
        const checkbox = document.createElement("span");
        const isChecked = preserveCheckedState[idx] || false;
        checkbox.textContent = isChecked ? "☑" : "☐";
        checkbox.className = "ksh-item-checkbox";
        checkbox.dataset.index = idx;
        checkbox.dataset.checked = isChecked.toString();
        Object.assign(checkbox.style, {
          cursor: "pointer",
          fontSize: "20px",
          width: "20px",
          color: "#007acc",
          userSelect: "none"
        });
        checkbox.onclick = () => {
          const isChecked = checkbox.dataset.checked === "true";
          checkbox.dataset.checked = isChecked ? "false" : "true";
          checkbox.textContent = isChecked ? "☐" : "☑";
        };

        const b1 = document.createElement("button");
        b1.textContent = "삽입";
        b1.onclick = () => insertOne(line);

        const b2 = document.createElement("button");
        b2.textContent = "삭제";
        b2.onclick = () => {
          const checkboxes = $all('.ksh-item-checkbox', listBox);
          const checkedStates = checkboxes.map(cb => cb.dataset.checked === "true");
          const arr = ta.value.split('\n');
          arr.splice(idx, 1);
          checkedStates.splice(idx, 1);
          ta.value = arr.join("\n");
          renderList(arr, checkedStates);
        };

        const span = document.createElement("span");
        Object.assign(span.style, {
          flex: "1",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap"
        });
        span.textContent = line || "(빈 줄)";
        span.title = line || "(빈 줄)";

        row.append(checkbox, b1, b2, span);
        listBox.appendChild(row);
      });
    }

    function syncFromTextarea() {
      console.log("[DEBUG] syncFromTextarea 호출됨! 스택 트레이스:");
      console.trace();

      console.log("[DEBUG] 호출 전 ta.value:", ta.value);

      // 전체 텍스트에 대해 정규화 및 중복 제거 적용
      const processedLines = normalizeInputToLines(ta.value);

      // 처리된 결과로 텍스트에어리어 업데이트
      ta.value = processedLines.join('\n');

      console.log("[DEBUG] 호출 후 ta.value:", ta.value);

      // 리스트 렌더링
      renderList(processedLines);
    }

    // 엔터키나 붙여넣기 등 명시적 사용자 액션에만 반응
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault(); // 기본 엔터 동작 방지

        const cursorPos = ta.selectionStart;
        const textBefore = ta.value.substring(0, cursorPos);
        const textAfter = ta.value.substring(cursorPos);

        ta.value = textBefore + '\n' + textAfter;
        ta.selectionStart = ta.selectionEnd = cursorPos + 1;

        // 엔터키 입력 시에는 중복 제거 없이 단순 렌더링만
        setTimeout(() => {
          renderList(ta.value.split('\n'));
        }, 10);
      }
    });

    // 붙여넣기 시에만 자동 정규화 및 중복 제거 실행
    ta.addEventListener("paste", (e) => {
      setTimeout(() => { syncFromTextarea(); }, 50);
    });

    // 검색 패널로부터 동기화 요청을 받을 리스너 추가
    ta.addEventListener("ksh:sync", syncFromTextarea);


    // ======== 삽입 로직 ========
    function insertTextToSpan(el, text) {
      el.focus();
      el.textContent = text;
      el.dispatchEvent(new InputEvent("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }

    // ALT+8 매크로 실행 함수
    function create650Field() {
      // keydown + keyup 조합 (document에만 발송)
      const keydownEvent = new KeyboardEvent('keydown', {
        key: '8',
        code: 'Digit8',
        keyCode: 56,
        which: 56,
        altKey: true,
        bubbles: true,
        cancelable: true
      });

      const keyupEvent = new KeyboardEvent('keyup', {
        key: '8',
        code: 'Digit8',
        keyCode: 56,
        which: 56,
        altKey: true,
        bubbles: true,
        cancelable: true
      });

      // document에만 이벤트 발송 (중복 방지)
      document.dispatchEvent(keydownEvent);
      setTimeout(() => document.dispatchEvent(keyupEvent), 10);

      console.log('ALT+8 키 이벤트 발송됨');
    }

    function insertOne(text) {
      const only650 = $("#ksh-only650").checked;
      let el = document.activeElement;

      if (!isSubfieldSpan(el) && el?.parentElement && isSubfieldSpan(el.parentElement)) {
        el = el.parentElement;
      }

      if (!isSubfieldSpan(el)) {
        const pool = only650 ? findAll650SubfieldSpans() : findAllSubfieldSpans();
        const target = pool.find(n => (n.textContent || "").trim() === "▼a▲");
        if (!target) {
          // 빈 650 필드가 없으면 1개 생성
          console.log("빈 650 필드가 없어서 새로 생성합니다.");
          create650Field();

          // 필드 생성 후 잠시 대기하고 다시 시도
          setTimeout(() => {
            const newPool = only650 ? findAll650SubfieldSpans() : findAllSubfieldSpans();
            const newTarget = newPool.find(n => (n.textContent || "").trim() === "▼a▲");
            if (newTarget) {
              insertTextToSpan(newTarget, text);
            } else {
              console.log("650 필드 생성 후에도 삽입할 수 없습니다.");
            }
          }, 500);
          return;
        }
        insertTextToSpan(target, text);
        return;
      }

      if (only650 && !is650Span(el)) {
        console.log("현재 칸은 650이 아님");
        return;
      }

      insertTextToSpan(el, text);
    }

    function fillBatch() {
      const only650 = $("#ksh-only650").checked;
      const lines = normalizeInputToLines(ta.value);
      const checkboxes = $all('.ksh-item-checkbox', listBox);

      if (checkboxes.length === 0) {
        console.log('리스트가 비어있음');
        return;
      }

      const checkedItems = [];
      checkboxes.forEach((cb, idx) => {
        const isChecked = cb.dataset.checked === "true" && cb.textContent === "☑";
        if (isChecked && lines[idx]) checkedItems.push(lines[idx]);
      });

      if (checkedItems.length === 0) {
        console.log('체크된 항목 없음');
        return;
      }

      const pool = only650 ? findAll650SubfieldSpans() : findAllSubfieldSpans();
      const empties = pool.filter(n => (n.textContent || "").trim() === "▼a▲");
      const needed = checkedItems.length;
      const available = empties.length;

      if (available < needed) {
        const shortage = needed - available;
        console.log(`체크된 항목을 위해 ${shortage}개의 650 필드를 추가 생성합니다.`);

        // 부족한 만큼 650 필드 생성
        for (let i = 0; i < shortage; i++) {
          create650Field();
        }

        // 필드 생성 후 대기하고 삽입 실행
        setTimeout(() => {
          const newPool = only650 ? findAll650SubfieldSpans() : findAllSubfieldSpans();
          const newEmpties = newPool.filter(n => (n.textContent || "").trim() === "▼a▲");
          const count = Math.min(newEmpties.length, checkedItems.length);
          for (let i = 0; i < count; i++) insertTextToSpan(newEmpties[i], checkedItems[i]);
          console.log(`${count}개 체크된 항목 삽입 완료`);
        }, 1000);
      } else {
        // 충분한 필드가 있으면 바로 삽입
        const count = Math.min(empties.length, checkedItems.length);
        for (let i = 0; i < count; i++) insertTextToSpan(empties[i], checkedItems[i]);
        console.log(`${count}개 체크된 항목 삽입 완료`);
      }
    }

    btnInsertCurrent.onclick = () => {
      const only650 = $("#ksh-only650").checked;
      const lines = normalizeInputToLines(ta.value);
      if (lines.length === 0) {
        console.log('리스트가 비어있음');
        return;
      }
      const validLines = lines.filter(line => line.trim() !== "");
      if (validLines.length === 0) {
        console.log('삽입할 데이터가 없음');
        return;
      }

      const pool = only650 ? findAll650SubfieldSpans() : findAllSubfieldSpans();
      const empties = pool.filter(n => (n.textContent || "").trim() === "▼a▲");
      const needed = validLines.length;
      const available = empties.length;

      if (available < needed) {
        const shortage = needed - available;
        console.log(`${shortage}개의 650 필드를 추가 생성합니다.`);

        // 부족한 만큼 650 필드 생성
        for (let i = 0; i < shortage; i++) {
          create650Field();
        }

        // 필드 생성 후 대기하고 삽입 실행
        setTimeout(() => {
          const newPool = only650 ? findAll650SubfieldSpans() : findAllSubfieldSpans();
          const newEmpties = newPool.filter(n => (n.textContent || "").trim() === "▼a▲");
          const count = Math.min(newEmpties.length, validLines.length);
          for (let i = 0; i < count; i++) insertTextToSpan(newEmpties[i], validLines[i]);
          console.log(`${count}개 항목 전체 삽입 완료`);
        }, 1000);
      } else {
        // 충분한 필드가 있으면 바로 삽입
        const count = Math.min(empties.length, validLines.length);
        for (let i = 0; i < count; i++) insertTextToSpan(empties[i], validLines[i]);
        console.log(`${count}개 항목 전체 삽입 완료`);
      }
    };
    btnFillBatch.onclick = fillBatch;
    btnClearAll.onclick = () => { ta.value = ""; renderList([]); };
    btnSelectAll.onclick = () => {
      const checkboxes = $all('.ksh-item-checkbox', listBox);
      checkboxes.forEach(cb => { cb.dataset.checked = "true"; cb.textContent = "☑"; });
    };
    btnDeselectAll.onclick = () => {
      const checkboxes = $all('.ksh-item-checkbox', listBox);
      checkboxes.forEach(cb => { cb.dataset.checked = "false"; cb.textContent = "☐"; });
    };

    btnClearAll.onclick = () => { ta.value = ""; renderList([]); };

    // ======== 프리셋 ========
    const LS_KEY = "ksh_presets_v1";
    let currentLoadedPresetName = null; // 현재 로드된 프리셋 이름을 추적하기 위한 변수

    const loadPresets = () => { try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { return {}; } };
    const savePresets = (obj) => { localStorage.setItem(LS_KEY, JSON.stringify(obj)); renderPresetButtons(); };

    function renderPresetButtons() {
      const presets = loadPresets();
      presetButtonsContainer.innerHTML = "";
      Object.keys(presets).forEach(name => {
        const b = document.createElement("button");
        b.textContent = name;
        b.style.margin = "2px";
        b.style.padding = "4px 8px";
        b.style.fontSize = "12px";
        b.style.whiteSpace = "nowrap";
        b.onclick = () => {
          ta.value = presets[name];
          renderList(ta.value.split('\n'));
          inName.value = name;
          currentLoadedPresetName = name; // 프리셋 로드 시, 현재 이름 저장
        };
        presetButtonsContainer.appendChild(b);
      });
    }

    btnSave.onclick = () => {
      const name = inName.value.trim();
      if (!name) return;
      const p = loadPresets();
      p[name] = ta.value;
      savePresets(p);
      inName.value = "";
      currentLoadedPresetName = null; // 새 저장 후에는 선택 상태 초기화
    };

    btnUpdate.onclick = () => {
      const newName = inName.value.trim();
      if (!newName) {
        alert("프리셋 이름을 입력하세요.");
        return;
      }

      const originalName = currentLoadedPresetName;
      if (!originalName) {
        alert("수정할 프리셋을 먼저 불러오세요.");
        return;
      }

      const p = loadPresets();

      // 이름이 변경되었고, 기존 이름이 존재할 경우에만 삭제 (이름 변경 처리)
      if (originalName !== newName && p.hasOwnProperty(originalName)) {
        delete p[originalName];
      }

      // 새 이름(또는 기존 이름)으로 현재 내용을 저장
      p[newName] = ta.value;
      savePresets(p);

      // 현재 로드된 프리셋 이름을 새 이름으로 업데이트
      currentLoadedPresetName = newName;
    };

    btnDelete.onclick = () => {
      const name = inName.value.trim();
      if (!name) return;
      const p = loadPresets();
      if (!(name in p)) return;
      delete p[name];
      savePresets(p);
      
      // 삭제된 프리셋이 현재 로드된 것이었다면 상태 초기화
      if (currentLoadedPresetName === name) {
        currentLoadedPresetName = null;
        ta.value = "";
        inName.value = "";
        renderList([]);
      }
    };

    btnExport.onclick = () => {
      const data = localStorage.getItem(LS_KEY) || "{}";
      const blob = new Blob([data], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "ksh-presets.json";
      a.click();
      URL.revokeObjectURL(url);
    };

    btnImport.onclick = () => fileIn.click();
    fileIn.onchange = async () => {
      const f = fileIn.files?.[0];
      if (!f) return;
      try {
        const txt = await f.text();
        const obj = JSON.parse(txt);
        if (typeof obj !== "object" || Array.isArray(obj)) throw new Error("형식 오류");
        localStorage.setItem(LS_KEY, JSON.stringify(obj));
        renderPresetButtons();
      } catch (e) {
        console.log("가져오기 실패:", e.message);
      }
    };

    // 초기 렌더
    renderPresetButtons();
    
    // [보강] MARC 필드 변경 감지 옵저버
    // 1. MARC 리스트 컨테이너를 찾거나, 2. MARC 편집기 전체를 감싸는 컨테이너를 찾거나, 3. body에 fallback
    const marcListContainer = $('ul.ikc-marc-list, div[data-marc="list-container"]'); 
    const marcEditorRoot = $('.ikc-marc-editor'); // MARC 에디터 전체 루트 요소
    
    const targetNode = marcListContainer || marcEditorRoot || document.body; // 최후의 수단: body
    
    const marcObserver = new MutationObserver((mutationsList, observer) => {
        // DOM이 변경되면 콘솔에 로그만 남김 (필드 탐색 함수가 알아서 재탐색하도록 유지)
        console.log('🔄 MARC 필드 컨테이너 변경 감지됨 (덮어쓰기 등). 필드 참조가 갱신될 예정입니다.');
        // 상태 갱신은 필요 없음. 필드 찾기 함수가 실행 시점에서 최신 DOM을 참조하도록 보장
    });
    
    // 컨테이너가 있다면 해당 노드에 관찰자를 부착
    if (targetNode) {
        marcObserver.observe(targetNode, { 
            childList: true, 
            subtree: true, 
            // 덮어쓰기 시 컨테이너 자체가 교체될 경우 대비: attributes 감지 추가
            attributes: true, 
            attributeFilter: ['class', 'style', 'data-marc']
        });
        console.log(`✅ MARC 변경 감지 옵저버 부착: ${targetNode === document.body ? 'document.body' : targetNode.nodeName}에.`);
    }
  }

  // ============== 패널 토글 ==============
  function ensurePanel() {
    let panel = document.getElementById(PANEL_ID);
    if (!panel) {
      panel = document.createElement("div");
      panel.id = PANEL_ID;
      document.body.appendChild(panel);
      buildKshPanel(panel);
    }
    panel.style.display = "";
    return panel;
  }

  function togglePanel() {
    const panel = document.getElementById(PANEL_ID);
    if (!panel) {
      ensurePanel();
      return;
    }
    panel.style.display = panel.style.display === "none" ? "" : "none";
  }

  // ============== 메시지/초기화 ==============
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg?.type === "KSH_TOGGLE_PANEL") togglePanel();
  });

  // 자동 표시
  document.addEventListener('DOMContentLoaded', () => {
    if (AUTO_SHOW) ensurePanel();
  });

  // 자동 표시
  document.addEventListener('DOMContentLoaded', () => {
    if (AUTO_SHOW) ensurePanel();
    
    // [보강] MARC 덮어쓰기(가져오기) 버튼 클릭 감지
    // '전체 덮어쓰기' 버튼을 찾습니다. (스크린샷 기반)
    const overwriteButton = $('button[data-bind*="replaceCurrentMarcFields"], button:contains("전체 덮어쓰기")');

    if (overwriteButton) {
      overwriteButton.addEventListener('click', () => {
        console.log('🔗 "전체 덮어쓰기" 버튼 클릭 감지. DOM 갱신 후 기능 재활성화 대기.');
        
        // 덮어쓰기 작업 완료 후 (약간의 지연 필요) DOM 참조가 안정적으로 갱신되도록 합니다.
        setTimeout(() => {
             console.log('🔗 DOM 갱신 안정화 예상 완료. 다음 기능 호출 가능.');
        }, 500); 
      });
      console.log('✅ "전체 덮어쓰기" 버튼 이벤트 리스너 부착 완료.');
    } else {
      console.log('⚠️ "전체 덮어쓰기" 버튼을 찾을 수 없어 이벤트 리스너 부착 실패.');
    }
  });


  // ===== AFTER (수정 후) =====
  // 디버깅/수동 제어용 공개 API
  window.KSH = { ensurePanel, togglePanel };

  // -------------------
  // article-processor.js와 같은 다른 모듈이 사용할 헬퍼 함수들을 노출시킵니다.
  window.KSH_HELPERS = {
    $,
    $all,
    insertTextToSpan, // buildKshPanel 밖으로 이동시킨 함수
  };
  // -------------------
})();

