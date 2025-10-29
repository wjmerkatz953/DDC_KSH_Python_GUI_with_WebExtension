// article-processor.js - v7 (keyCode 문제 해결)

(() => {
  console.log('📚 정관사 처리 모듈 로딩 중... (v7)');

  const { $, $all, insertTextToSpan } = window.KSH_HELPERS || {};
  if (!$) {
    console.error('KSH 헬퍼 함수를 찾을 수 없습니다.');
    return;
  }
  
  const articleList = [
    'The', 'A', 'An', 'Le', 'La', 'L\'', 'Les', 'Un', 'Une', 'Des', 'Der', 
    'Die', 'Das', 'Dem', 'Den', 'Des', 'Ein', 'Eine', 'Einen', 'Einem', 'Eines', 
    'El', 'La', 'Lo', 'Los', 'Las', 'Un', 'Una', 'Unos', 'Unas', 'Il', 'Lo', 
    'I', 'Gli', 'Le', 'Uno', 'Un\''
  ];
  const articles = [...new Set(articleList)].join('|');
  const articleRegex = new RegExp(`^(▼a)\\s*\\(?(${articles})\\)?\\s+(.*)`, 'i');

  // [최종 수정] 650 처리 방식과 완벽하게 동일한 이벤트 생성
  function createNewMarcField() {
    console.log('Alt+9 (246 3 9 생성) 매크로 실행');
    const keydownEvent = new KeyboardEvent('keydown', {
        key: '9',
        code: 'Digit9',
        keyCode: 57, // '9' 키의 구형 식별 번호
        which: 57,   // 구형 브라우저 호환용
        altKey: true,
        bubbles: true,
        cancelable: true
    });
    const keyupEvent = new KeyboardEvent('keyup', {
        key: '9',
        code: 'Digit9',
        keyCode: 57,
        which: 57,
        altKey: true,
        bubbles: true,
        cancelable: true
    });
    document.dispatchEvent(keydownEvent);
    setTimeout(() => document.dispatchEvent(keyupEvent), 10);
  }

  // 새로 생성된 '246 ▼a▲' 필드가 렌더링될 때까지 지능적으로 기다리는 함수
  function waitForNewEmpty246Field(fieldsBefore, timeout = 5000) {
    const startTime = Date.now();
    return new Promise((resolve, reject) => {
        const check = () => {
            const fieldsAfter = $all('li.ikc-marc-field');
            const newField = fieldsAfter.find(field => !fieldsBefore.has(field));

            if (newField) {
                const tag = $('input[data-marc="tag"]', newField)?.value.trim();
                const content = $('span.ikc-marc-subfields', newField)?.textContent.trim();
                if (tag === '246' && content === '▼a▲') {
                    resolve(newField);
                    return;
                }
            }

            if (Date.now() - startTime > timeout) {
                reject(new Error("시간 내에 새로 생성된 '246 ▼a▲' 필드를 찾지 못했습니다."));
                return;
            }
            setTimeout(check, 100);
        };
        check();
    });
  }

  // 정관사 처리 메인 함수
  async function processArticleFields() {
    console.log('정관사 정리 시작 (지능형 대기 방식)');
    
    const fieldsToProcess = $all('li.ikc-marc-field').filter(field => {
      const tag = $('input[data-marc="tag"]', field)?.value.trim();
      const ind1 = $('input[data-marc="ind1"]', field)?.value.trim();
      const ind2 = $('input[data-marc="ind2"]', field)?.value.trim();
      return tag === '246' && ind1 === '1' && ind2 === '9';
    });

    if (fieldsToProcess.length === 0) {
      alert('처리할 246 19 필드를 찾을 수 없습니다.');
      return;
    }

    let processedCount = 0;
    for (const sourceField of fieldsToProcess) {
      const subfieldSpan = $('span.ikc-marc-subfields', sourceField);
      if (!subfieldSpan) continue;

      const originalText = subfieldSpan.textContent;
      const match = originalText.match(articleRegex);

      if (match) {
        const fieldsBefore = new Set($all('li.ikc-marc-field'));
        createNewMarcField();

        try {
          const newEmptyField = await waitForNewEmpty246Field(fieldsBefore, 5000);
          console.log('새로 생성된 246 3 9 필드를 성공적으로 감지했습니다.');
          
          const newSubfieldSpan = $('span.ikc-marc-subfields', newEmptyField);
          const [, , , restOfText] = match;
          const newText = '▼a' + restOfText.charAt(0).toUpperCase() + restOfText.slice(1);
          insertTextToSpan(newSubfieldSpan, newText);
          processedCount++;
        } catch (error) {
          alert('오류: ' + error.message);
          console.error(error);
        }
      }
    }
    
    if (processedCount > 0) {
      console.log(`✅ 정관사 정리 완료: 총 ${processedCount}개 필드를 처리했습니다.`); // alert 제거
    } else if (fieldsToProcess.length > 0) {
      console.log(`'246 19' 필드는 ${fieldsToProcess.length}개 찾았지만, 정관사로 시작하는 내용이 없어 처리하지 않았습니다.`); // alert 제거
    }
  }

  // -------------------
  // [추가된 기능] 090 청구기호 검색 기능
  function processCallNumberSearch(trimCount = 0) {
    const field090 = $all('li.ikc-marc-field').find(field => {
      const tag = $('input[data-marc="tag"]', field)?.value.trim();
      return tag === '090';
    });

    if (!field090) {
      alert('090 필드를 찾을 수 없습니다.');
      return;
    }

    const subfieldSpan = $('span.ikc-marc-subfields', field090);
    if (!subfieldSpan || !subfieldSpan.textContent) {
      alert('090 필드에 내용이 없습니다.');
      return;
    }

    const rawText = subfieldSpan.textContent;
    // ▼a, ▼b 등을 공백으로 바꾸고, ▲를 제거한 뒤, 연속 공백을 하나로 합침
    const cleanedText = rawText.replace(/▼[a-zA-Z0-9]/g, ' ').replace(/▲/g, '').replace(/\s+/g, ' ').trim();

    let finalText = cleanedText;
    if (trimCount > 0) {
      finalText = cleanedText.slice(0, -trimCount);
    }
    
    if (!finalText) {
        console.log('처리 후 검색할 내용이 없습니다.');
        return;
    }

    const baseUrl = 'https://las.pusan.ac.kr:18000/#/cat/biblio/management?q=ALL%3DK%7CA%7C';
    const finalUrl = `${baseUrl}${encodeURIComponent(finalText)}&s=N`;

    console.log(`[CN-${trimCount}] 검색 실행: ${finalText}`);
    window.open(finalUrl, '_blank');
  }
  // -------------------

  // 패널에 버튼 추가
  function initArticleProcessor(panelRoot) {
    // [수정] nth-child 대신 새로 부여한 ID로 정확히 찾습니다.
    const buttonBar = $('#ksh-action-buttons'); 
    
    // ID로 찾았으므로 더 이상 복잡한 예외처리(fallback)가 필요 없습니다.
    if (!buttonBar) {
        console.error('버튼을 추가할 공간(#ksh-action-buttons)을 찾지 못했습니다.');
        return;
    }

    const btnProcessArticles = document.createElement("button");
    btnProcessArticles.textContent = "정관사 정리";
    btnProcessArticles.onclick = processArticleFields;
    
    // [추가된 기능] CN-0, CN-1, CN-2 버튼 추가
    const btnCN0 = document.createElement("button");
    btnCN0.textContent = "CN-0";
    btnCN0.onclick = () => processCallNumberSearch(0);
    btnCN0.title = "090 청구기호 전체로 검색";

    const btnCN1 = document.createElement("button");
    btnCN1.textContent = "CN-1";
    btnCN1.onclick = () => processCallNumberSearch(1);
    btnCN1.title = "090 청구기호 마지막 한 글자 제외하고 검색";

    const btnCN2 = document.createElement("button");
    btnCN2.textContent = "CN-2";
    btnCN2.onclick = () => processCallNumberSearch(2);
    btnCN2.title = "090 청구기호 마지막 두 글자 제외하고 검색";

    // 모든 버튼을 한 번에 추가합니다.
    buttonBar.append(btnProcessArticles, btnCN0, btnCN1, btnCN2);
  }

  window.initArticleProcessor = initArticleProcessor;
})();