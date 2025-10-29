// KSH MARC Inserter - Background Script (검색 기능 추가)

// 액션 아이콘 클릭 → 현재 탭에 패널 토글 메시지 전송
chrome.action.onClicked.addListener(async (tab) => {
  if (!tab?.id) return;
  
  try {
    // 기존 KSH 패널 토글 메시지 전송 (기존 기능 유지)
    await chrome.tabs.sendMessage(tab.id, { type: "KSH_TOGGLE_PANEL" });
  } catch (e) {
    // content.js가 아직 주입되지 않은 경우 스크립트 주입 후 재시도
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id, allFrames: true },
        files: ["content.js", "search-addon.js", "article-processor.js"]
      });
      await chrome.tabs.sendMessage(tab.id, { type: "KSH_TOGGLE_PANEL" });
    } catch (e2) {
      console.warn("KSH panel toggle failed:", e2);
    }
  }
});

// 컨텍스트 메뉴 추가 (우클릭 메뉴)
chrome.runtime.onInstalled.addListener(() => {
  // 기존 컨텍스트 메뉴 제거
  chrome.contextMenus.removeAll();
  
  // KSH 패널 토글 메뉴
  chrome.contextMenus.create({
    id: "toggle-ksh-panel",
    title: "KSH 패널 토글",
    contexts: ["all"]
  });
  
  // 검색 패널 토글 메뉴
  chrome.contextMenus.create({
    id: "toggle-search-panel", 
    title: "검색 패널 토글",
    contexts: ["all"]
  });
  
  // 구분선
  chrome.contextMenus.create({
    id: "separator1",
    type: "separator",
    contexts: ["all"]
  });
  
  // 선택한 텍스트로 DDC/KSH 검색
  chrome.contextMenus.create({
    id: "search-selected-text",
    title: "선택한 텍스트로 DDC/KSH 검색: '%s'",
    contexts: ["selection"]
  });
  
  console.log('KSH MARC Inserter 설치/업데이트 완료');
  console.log('단축키: Ctrl+Shift+Q (KSH 패널), Ctrl+Shift+S (검색 패널)');
});

// 컨텍스트 메뉴 클릭 처리
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (!tab?.id) return;
  
  try {
    switch (info.menuItemId) {
      case "toggle-ksh-panel":
        await chrome.tabs.sendMessage(tab.id, { type: "KSH_TOGGLE_PANEL" });
        break;
        
      case "toggle-search-panel":
        await chrome.tabs.sendMessage(tab.id, { type: "SEARCH_TOGGLE_PANEL" });
        break;
        
      case "search-selected-text":
        if (info.selectionText) {
          await chrome.tabs.sendMessage(tab.id, { 
            type: "SEARCH_WITH_TEXT", 
            text: info.selectionText.trim() 
          });
        }
        break;
    }
  } catch (e) {
    // 스크립트가 주입되지 않은 경우 주입 후 재시도
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id, allFrames: true },
        files: ["content.js", "search-addon.js", "article-processor.js"]
      });
      
      // 재시도
      switch (info.menuItemId) {
        case "toggle-ksh-panel":
          await chrome.tabs.sendMessage(tab.id, { type: "KSH_TOGGLE_PANEL" });
          break;
        case "toggle-search-panel":
          await chrome.tabs.sendMessage(tab.id, { type: "SEARCH_TOGGLE_PANEL" });
          break;
        case "search-selected-text":
          if (info.selectionText) {
            await chrome.tabs.sendMessage(tab.id, { 
              type: "SEARCH_WITH_TEXT", 
              text: info.selectionText.trim() 
            });
          }
          break;
      }
    } catch (e2) {
      console.warn("Context menu action failed:", e2);
    }
  }
});

// 키보드 단축키 지원을 위한 commands API (manifest.json에 정의 필요)
if (chrome.commands) {
  chrome.commands.onCommand.addListener(async (command, tab) => {
    if (!tab?.id) return;
    
    try {
      switch (command) {
        case "toggle_ksh_panel":
          await chrome.tabs.sendMessage(tab.id, { type: "KSH_TOGGLE_PANEL" });
          break;
        case "toggle_search_panel":
          await chrome.tabs.sendMessage(tab.id, { type: "SEARCH_TOGGLE_PANEL" });
          break;
      }
    } catch (e) {
      // 스크립트 주입 후 재시도
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id, allFrames: true },
          files: ["content.js", "search-addon.js", "article-processor.js"]
        });
        
        switch (command) {
          case "toggle_ksh_panel":
            await chrome.tabs.sendMessage(tab.id, { type: "KSH_TOGGLE_PANEL" });
            break;
          case "toggle_search_panel":
            await chrome.tabs.sendMessage(tab.id, { type: "SEARCH_TOGGLE_PANEL" });
            break;
        }
      } catch (e2) {
        console.warn("Keyboard shortcut failed:", e2);
      }
    }
  });
}

// 확장 프로그램 아이콘 배지 업데이트
function updateBadge(text, color = "#28a745") {
  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({ color });
}

// 탭 활성화 시 초기화
chrome.tabs.onActivated.addListener(() => {
  updateBadge("");
});

// 디버깅용 콘솔 로그
console.log('🎯 KSH MARC Inserter Background Script 로드 완료');
console.log('📋 기능: KSH 패널 + DDC/KSH 검색 패널');
console.log('⌨️ 단축키: Ctrl+Shift+Q (KSH), Ctrl+Shift+S (검색)');
console.log('🖱️ 우클릭 메뉴에서도 패널 토글 가능');

// content.js와 search-addon.js 간의 메시지를 중계하는 리스너
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // 메시지를 보낸 탭의 ID가 있는지 확인
  if (sender.tab && sender.tab.id) {
    // 메시지를 보낸 탭으로만 메시지를 다시 전달
    chrome.tabs.sendMessage(sender.tab.id, message);
  }
  // return true 제거 - 실제 비동기 응답이 없으므로
});
