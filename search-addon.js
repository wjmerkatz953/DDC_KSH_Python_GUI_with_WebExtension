// search-addon.js - 기존 KSH 패널 바로 왼쪽에 정확히 배치
console.log('🔍 검색 애드온 로딩 중...');

let searchPanelVisible = false;
const SEARCH_PANEL_ID = "ksh-search-panel";
const API_BASE_URL = 'http://localhost:5000/api';

// =================================================================
// 헬퍼 및 핵심 기능 함수 (전역 스코프로 이동)
// =================================================================

// DDC 번호 정규화 함수
function normalizeDDCQuery(query) {
  // a650.401 -> 650.401 같은 패턴 처리
  return query.replace(/^[a-zA-Z]+(\d+(?:\.\d+)?)$/, '$1');
}

// 검색 실행
async function executeSearch() {
  const query = document.getElementById('search-input')?.value.trim();
  if (!query) return;

  // DDC 번호 정규화
  const normalizedQuery = normalizeDDCQuery(query);
  const ddcPattern = /^\d{1,3}(\.\d+)?$/;

  if (ddcPattern.test(normalizedQuery)) {
    await Promise.all([searchDDC(normalizedQuery), searchKSH(normalizedQuery)]);
  } else {
    await searchKSH(query); // 키워드 검색은 원본 쿼리 사용
    const ddcInfo = document.getElementById('ddc-info');
    if (ddcInfo) ddcInfo.innerHTML = '키워드 검색';
  }
}

// DDC 검색
async function searchDDC(ddcCode) {
  const ddcInfo = document.getElementById('ddc-info');
  if (!ddcInfo) return;

  ddcInfo.innerHTML = 'DDC 검색중...';

  try {
    const response = await fetch(`${API_BASE_URL}/dewey/search?ddc=${ddcCode}`);
    const data = await response.json();

    if (data.error) {
      ddcInfo.innerHTML = `오류: ${data.error}`;
      return;
    }

    const main = data.main || {};
    ddcInfo.innerHTML = `${main.notation || ''} ${main.label || ''}`;
  } catch (error) {
    ddcInfo.innerHTML = 'DDC 검색 실패';
  }
}

// KSH 검색
async function searchKSH(query) {
  const kshResults = document.getElementById('ksh-text-results');
  if (!kshResults) return;

  kshResults.textContent = 'KSH 검색중...';

  try {
    const response = await fetch(`${API_BASE_URL}/ksh/search?q=${encodeURIComponent(query)}`);
    const data = await response.json();

    if (data.error) {
      kshResults.textContent = `오류: ${data.error}`;
      return;
    }

    if (!data || data.length === 0) {
      kshResults.textContent = '검색 결과 없음';
      return;
    }

    // 1. API 결과를 하나의 텍스트로 합침 (200개로 제한)
    const rawResultsText = data.slice(0, 200).map(item => item.subject).join('\n');

    // 2. 정규화 및 중복 제거 함수를 호출
    const processedLines = normalizeInputToLines(rawResultsText);

    // 3. 처리된 결과를 다시 텍스트로 합쳐서 표시
    kshResults.textContent = processedLines.join('\n');
  } catch (error) {
    kshResults.textContent = 'KSH 검색 실패';
  }
}

// KSH 결과를 기본 패널로 전송
function sendToPanel(event) {
  const resultsEl = document.getElementById('ksh-text-results');
  const textToSend = resultsEl?.textContent?.trim();

  const placeholderTexts = ['KSH 검색중...', '검색 결과 없음'];
  if (!textToSend || placeholderTexts.includes(textToSend)) {
    console.log('전송할 KSH 결과가 없습니다.');
    return;
  }

  const targetTextarea = document.getElementById('ksh-input');
  if (!targetTextarea) {
    console.error('기본 패널의 입력창(#ksh-input)을 찾을 수 없습니다.');
    return;
  }

  targetTextarea.value = textToSend;
  targetTextarea.dispatchEvent(new Event('ksh:sync', { bubbles: true }));

  const btn = event.target;
  const originalText = btn.textContent;
  btn.textContent = '전송완료!';
  btn.disabled = true;
  setTimeout(() => {
    btn.textContent = originalText;
    btn.disabled = false;
  }, 1500);
}

function normalizeInputToLines(raw) {
  if (!raw) return [];
  let s = raw
    .replace(/▲\s*[;,]\s*/g, "▲\n")
    .replace(/[;,]\s*(?=▼a)/g, "\n")
    .replace(/▲\s*\n\s*/g, "▲\n");

  const lines = s.split(/\r?\n/).map(v => v.trim());
  const uniqueLines = [];
  const seenLines = new Set();

  for (const line of lines) {
    if (line === "") {
      uniqueLines.push(line);
    } else {
      if (!seenLines.has(line)) {
        seenLines.add(line);
        uniqueLines.push(line);
      }
    }
  }

  const nonEmptyOriginal = lines.filter(line => line !== "").length;
  const nonEmptyUnique = uniqueLines.filter(line => line !== "").length;
  if (nonEmptyOriginal !== nonEmptyUnique) {
    const removedCount = nonEmptyOriginal - nonEmptyUnique;
    console.log(`🔍 검색 결과에서 중복 항목 ${removedCount}개가 제거되었습니다.`);
  }
  return uniqueLines;
}

// -------------------
// [추가된 기능] 082 필드에서 DDC 번호를 읽는 헬퍼 함수 (content.js에서 복사)
function read082Field() {
  // content.js의 $all 함수에 해당하는 DOM 쿼리를 사용해야 함
  const fields082 = document.querySelectorAll('li.ikc-marc-field');
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


// 020 필드에서 ISBN 자동 읽기
function autoReadISBN() {
  const fields020 = document.querySelectorAll('li.ikc-marc-field');
  let isbnValue = '';

  for (const field of fields020) {
    const tagInput = field.querySelector('input[data-marc="tag"]');
    if (tagInput && tagInput.value.trim() === '020') {
      const subfieldSpan = field.querySelector('span.ikc-marc-subfields[data-marc="subfields"]');
      if (subfieldSpan) {
        const text = subfieldSpan.textContent || '';
        const match = text.match(/▼a\s*([0-9\-X]+)/i);
        if (match) {
          isbnValue = match[1].replace(/\-/g, '');
          break;
        }
      }
    }
  }

  const isbnInput = document.getElementById('isbn-input');
  const resultDiv = document.getElementById('isbn-result');


  if (isbnValue) {
    if (isbnInput) isbnInput.value = isbnValue;
    // -------------------
    // [복구] 읽기 완료 후, 화면에 임시 메시지를 설정하는 대신 즉시 검색 실행
    if (resultDiv) resultDiv.textContent = '020 필드 읽기 완료. 자동 검색 시작...';
    console.log(`020 필드에서 ISBN 읽기 완료: ${isbnValue}. 자동 검색 시작.`);
    
    // 즉시 검색 실행 (원래 기능 복구)
    executeISBNSearch();
    // -------------------
  } else {
    if (resultDiv) resultDiv.textContent = '020 필드에서 ISBN을 찾을 수 없습니다.';
    console.log('020 필드에서 ISBN을 찾을 수 없음');
  }
}

// ISBN 서지정보 검색 실행
async function executeISBNSearch() {
  const isbnInput = document.getElementById('isbn-input');
  const resultDiv = document.getElementById('isbn-result');
  if (!isbnInput || !resultDiv) return;

  const isbn = isbnInput.value.trim().replace(/\-/g, '');
  if (!isbn) {
    resultDiv.textContent = 'ISBN을 입력해주세요.';
    return;
  }

  resultDiv.textContent = 'ISBN 검색중...';

  try {
    const certKey = "8f2ab95929df06a19f2f7d1b4cf4996118cce50914577c007ae6c78704ab2383";
    const url = `https://www.nl.go.kr/seoji/SearchApi.do?cert_key=${certKey}&result_style=json&page_no=1&page_size=1&isbn=${encodeURIComponent(isbn)}`;
    const response = await fetch(url);
    const data = await response.json();

    if (data.docs && data.docs.length > 0) {
      const book = data.docs[0];
      const eaIsbn = book.EA_ISBN || '';
      const eaAddCode = book.EA_ADD_CODE || '';
      const prePrice = book.PRE_PRICE || '';
      
      // -------------------
      // MARC 020 필드 서브필드 형식으로 변환 (필드 누락 시 문자열이 깨지지 않도록 조건부 연결 복구)
      let marcFormat = `▼a${eaIsbn}`;
      
      // 부가기호 (▼g)가 있을 경우에만 추가
      if (eaAddCode) {
        marcFormat += `▼g${eaAddCode}`;
      }
      
      // 가격 (▼c)이 있을 경우에만 ':\'를 붙여서 필드를 완성
      if (prePrice) {
        marcFormat += ` :▼c\\${prePrice}`;
      }
      
      marcFormat += `▲`;
      // -------------------
      
      resultDiv.textContent = marcFormat;
      resultDiv.title = `MARC 020 필드 형식 - ISBN: ${eaIsbn}, 부가기호: ${eaAddCode}, 가격: ${prePrice}`;
      console.log('ISBN 검색 결과 (MARC 형식):', marcFormat);
    } else {
      resultDiv.textContent = `ISBN ${isbn}에 대한 검색 결과가 없습니다.`;
    }
  } catch (error) {
    resultDiv.textContent = 'ISBN 검색 실패';
    console.error('ISBN 검색 오류:', error);
  }
}


// =================================================================
// 메시지 리스너 및 패널 관리
// =================================================================

chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.type === "SEARCH_TOGGLE_PANEL") {
    toggleSearchPanel();
  } else if (msg?.type === "SEARCH_WITH_TEXT" || msg?.type === "SEARCH_FROM_PANEL") {
    if (msg.text) {
      ensureSearchPanelVisible();
      setTimeout(() => {
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
          searchInput.value = msg.text;
          executeSearch(); // 이제 전역 스코프에서 호출 가능
        }
      }, 100);
    }
  } else if (msg?.type === "CLOSE_SEARCH_PANEL") {
    hideSearchPanel();
  }
});

function hideSearchPanel() {
  const existingPanel = document.getElementById(SEARCH_PANEL_ID);
  if (existingPanel) {
    existingPanel.remove();
    searchPanelVisible = false;
    console.log('🔍 검색 패널 숨김');
  }
}

function toggleSearchPanel() {
  if (searchPanelVisible) {
    hideSearchPanel();
  } else {
    createSearchPanel();
  }
}

function ensureSearchPanelVisible() {
  if (!searchPanelVisible) {
    createSearchPanel();
  }
}

function createSearchPanel() {
  if (document.getElementById(SEARCH_PANEL_ID)) return; // 이미 있으면 생성 안함

  const panel = document.createElement('div');
  panel.id = SEARCH_PANEL_ID;
  panel.innerHTML = `
    <div style="padding: 8px 12px; border-bottom: 1px solid #ddd; position: relative;">
      <h3 style="margin: 0; font-size: 14px;">🔍 검색</h3>
      <button id="close-search-panel" style="position: absolute; top: 4px; right: 8px; background: #ff4757; color: white; border: none; border-radius: 4px; padding: 4px 8px; cursor: pointer; font-size: 10px;">✕</button>
    </div>
    <div style="padding: 8px 12px; display: flex; align-items: center; gap: 8px;">
      <input type="text" id="search-input" placeholder="330.9519" style="flex-grow: 1; padding: 6px; border: 1px solid #ddd; border-radius: 3px; box-sizing: border-box;" />
      <button id="execute-search-btn" style="padding: 5px 10px; background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer;">검색</button>
      <button id="082-auto-btn" style="padding: 5px 10px; background: #ffc107; color: black; border: none; border-radius: 3px; cursor: pointer;">082</button>
      </div>
    <div style="padding: 8px 12px; border-top: 1px solid #ddd;">
      <h4 style="margin: 0 0 5px 0; font-size: 12px;">ISBN 서지정보</h4>
      <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 8px;">
        <input type="text" id="isbn-input" placeholder="ISBN 또는 020 필드 자동읽기" style="flex-grow: 1; padding: 4px; border: 1px solid #ddd; border-radius: 3px; font-size: 11px;" />
        <button id="isbn-search-btn" style="padding: 4px 8px; background: #17a2b8; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 10px;">검색</button>
        <button id="isbn-auto-btn" style="padding: 4px 8px; background: #6c757d; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 10px;">020읽기</button>
      </div>
      <div id="isbn-result" style="font-size: 11px; min-height: 1.2em; background: #f8f8f8; padding: 4px 6px; border: 1px solid #ddd; border-radius: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">ISBN 검색 대기중</div>
    </div>
    <div style="padding: 8px 12px; border-top: 1px solid #ddd;">
      <h4 style="margin: 0 0 5px 0; font-size: 12px;">DDC</h4>
      <div id="ddc-info" style="font-size: 11px; min-height: 1.2em; background: #f8f8f8; padding: 4px 6px; border: 1px solid #ddd; border-radius: 3px;">검색 대기중</div>
    </div>
    <div style="padding: 8px 12px; border-top: 1px solid #ddd;">
      <h4 style="margin: 0 0 5px 0; font-size: 12px;">KSH</h4>
      <pre id="ksh-text-results" style="width: 100%; min-height: 50px; font-size: 11px; font-family: monospace; box-sizing: border-box; resize: none; margin: 0; padding: 5px; border: 1px solid #ddd; background: #f8f8f8; white-space: pre-wrap; word-break: break-all; border-radius: 3px;"></pre>
      <button id="send-to-panel-btn" style="margin-top: 3px; padding: 8px 12px; background: #28a745; color: white; border: none; border-radius: 2px; cursor: pointer; font-size: 10px;">패널로 전송</button>
    </div>
  `;

  Object.assign(panel.style, {
    position: "fixed",
    right: "425px",
    bottom: "40px",
    width: "400px",
    maxHeight: "800px",
    overflowY: "auto",
    background: "white",
    borderTop: "1px solid #d0d0d0",
    boxShadow: "0 -8px 24px rgba(0,0,0,0.08)",
    zIndex: "2147483646",
    fontSize: "12px",
    lineHeight: "1.4",
    borderRadius: "10px 0 0 0"
  });

  document.body.appendChild(panel);
  searchPanelVisible = true;
  console.log('🔍 검색 패널 표시');

  // 모달 감지 로직
  const observer = new MutationObserver(() => {
    const modalSelectors = ['span.k-window-title', 'h1.ikc-toolbar-header[flex=""]'];
    let hasVisibleModal = modalSelectors.some(selector => {
      const element = document.querySelector(selector);
      return element && window.getComputedStyle(element).display !== 'none';
    });
    panel.style.zIndex = hasVisibleModal ? "999" : "2147483646";
  });
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class'] });

  // 이벤트 리스너 연결
  const searchInput = document.getElementById('search-input');
  searchInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') executeSearch(); });
  searchInput.focus();

  document.getElementById('execute-search-btn').addEventListener('click', executeSearch);
  document.getElementById('send-to-panel-btn').addEventListener('click', sendToPanel);
  document.getElementById('close-search-panel').addEventListener('click', hideSearchPanel);
  document.getElementById('isbn-search-btn').addEventListener('click', executeISBNSearch);
  document.getElementById('isbn-auto-btn').addEventListener('click', autoReadISBN);

  // 082 버튼 이벤트 리스너 연결
  document.getElementById('082-auto-btn').addEventListener('click', () => {
    const ddcCode = read082Field();
    if (ddcCode) {
      searchInput.value = ddcCode;
      executeSearch(); // 082 코드를 읽어온 후 바로 검색 실행
    } else {
      searchInput.value = '';
      alert('082 필드에서 DDC 번호를 찾을 수 없습니다.');
    }
  });

  const isbnInput = document.getElementById('isbn-input');
  isbnInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') executeISBNSearch(); });
}

// 키보드 단축키
document.addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.shiftKey && e.key === 'E') {
    e.preventDefault();
    toggleSearchPanel();
  }
});

console.log('🔍 검색 애드온 로드 완료 - Ctrl+Shift+E로 토글');