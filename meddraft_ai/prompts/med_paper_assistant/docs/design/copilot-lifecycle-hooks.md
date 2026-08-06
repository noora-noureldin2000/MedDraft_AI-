# VS Code Copilot Lifecycle Hooks — 設計文件

> 版本：v1.0 | 2025-03  
> 對應 VS Code Copilot Hooks (Preview, v1.109.3+)

## 概述

MedPaper Assistant 透過 VS Code Copilot 的 8 個生命週期斷點 (Lifecycle Hook Events)，在 Agent 對話過程中注入品質檢查、模式保護、記憶同步。這些 hooks 與我們既有的 76-check 架構（A/B/C/D/E/F/G/P/R 系列）協同運作。

### 核心設計原則

1. **Shell-Based**：所有 hook 用 bash 實作，透過 stdin/stdout JSON 通訊
2. **Non-Blocking Default**：大多數 hook 僅注入 `additionalContext`，不阻斷 Agent
3. **State Sharing**：hooks 間透過 `.github/hooks/_state/` 目錄下的 JSON 檔案通訊
4. **Audit Trail**：所有工具呼叫記錄至 `_state/session_audit.jsonl`

---

## 8 Event Lifecycle 對應表

| #   | VS Code Event        | 我們的 Hook      | 腳本                  | 功能                                        |
| --- | -------------------- | ---------------- | --------------------- | ------------------------------------------- |
| 1   | **SessionStart**     | session-init     | `session-init.sh`     | 讀取模式、恢復狀態、檢查 pending evolutions |
| 2   | **UserPromptSubmit** | prompt-analyzer  | `prompt-analyzer.sh`  | 偵測用戶意圖、注入工作流引導                |
| 3   | **PreToolUse**       | pre-tool-guard   | `pre-tool-guard.sh`   | 模式保護、危險指令攔截、save_reference 規則 |
| 4   | **PostToolUse**      | post-tool-check  | `post-tool-check.sh`  | Writing hooks 觸發、引用提醒、審計記錄      |
| 5   | **PreCompact**       | pre-compact-save | `pre-compact-save.sh` | Context 壓縮前的記憶保存                    |
| 6   | **SubagentStart**    | subagent-init    | `subagent-init.sh`    | 注入專案/模式上下文至 subagent              |
| 7   | **SubagentStop**     | _(不實作)_       | —                     | 不需要攔截 subagent 結束                    |
| 8   | **Stop**             | session-stop     | `session-stop.sh`     | 記憶同步提醒、審計結算、清理暫存            |

---

## Hook 鏈路圖

```
┌──────────────────────────────────────────────────────────────────────┐
│                     VS Code Copilot Session                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ① SessionStart                                                      │
│  └─ session-init.sh                                                  │
│     ├─ Read .copilot-mode.json → mode                                │
│     ├─ Read .mdpaper-state.json → recovery context                   │
│     ├─ Check pending-evolutions.yaml → improvement hints             │
│     └─ Write _state/session_context.json → shared state              │
│                                                                      │
│  ↓ (user types a prompt)                                             │
│                                                                      │
│  ② UserPromptSubmit                                                  │
│  └─ prompt-analyzer.sh                                               │
│     ├─ Detect intent: mode-switch / commit / writing / autopilot     │
│     └─ Inject workflow guidance (SKILL.md reminder)                  │
│                                                                      │
│  ↓ (agent decides to use a tool)                                     │
│                                                                      │
│  ③ PreToolUse ←──── GATE (can DENY or ASK) ────┐                    │
│  └─ pre-tool-guard.sh                           │                    │
│     ├─ Mode protection (normal/research → deny  │                    │
│     │   writes to .claude/ src/ tests/ etc.)    │                    │
│     ├─ Destructive cmd blocking (rm -rf, etc.)  │                    │
│     ├─ save_reference → warn use _mcp           │                    │
│     └─ Audit: log tool invocation               │                    │
│                                                  │                    │
│  ↓ (tool executes)                               │                    │
│                                                  │ Feedback           │
│  ④ PostToolUse ──────────────────────────────────┘ Loop               │
│  └─ post-tool-check.sh                                               │
│     ├─ Draft edit → "run run_writing_hooks()"                        │
│     ├─ concept.md edit → "validate_concept() required"               │
│     ├─ git commit → memory sync reminder                             │
│     ├─ save_reference → "get_available_citations()"                  │
│     └─ Audit: log tool completion                                    │
│                                                                      │
│  ↓ (repeat ③→④ for each tool call)                                   │
│                                                                      │
│  ⑤ PreCompact (when context gets too long)                           │
│  └─ pre-compact-save.sh                                              │
│     ├─ Summarize: mode, doing, project, writing section              │
│     └─ Inject: "call sync_workspace_state() before continuing"       │
│                                                                      │
│  ⑥ SubagentStart (when subagent is spawned)                          │
│  └─ subagent-init.sh                                                 │
│     ├─ Inject active project + mode                                  │
│     └─ Agent-specific guidance (reviewer=read-only, etc.)            │
│                                                                      │
│  ⑧ Stop (session ends)                                               │
│  └─ session-stop.sh                                                  │
│     ├─ Reminder: sync memory-bank, workspace state                   │
│     ├─ Write session_end to audit log                                │
│     └─ Clean up transient _state/session_context.json                │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 與 76-Check 架構的整合

### PreToolUse × PostToolUse 循環（核心）

這兩個 hook 構成一個 **回饋迴路**，是我們 Code-Enforced 品質系統的入口：

```
PostToolUse (draft edited)
  → injects "run run_writing_hooks(hooks='post-write')"
    → Agent calls run_writing_hooks
      → PreToolUse allows (it's an MCP tool)
        → WritingHooksEngine executes A1-A6, A3b (34 checks)
          → PostToolUse captures result
            → Agent fixes issues if any
```

### Hook 對應 Check 系列

| Lifecycle Hook                 | 觸發的 Check 系列             | 觸發方式                                                         |
| ------------------------------ | ----------------------------- | ---------------------------------------------------------------- |
| PostToolUse (draft edit)       | **A1-A6, A3b** (post-write)   | 注入 additionalContext 提醒 agent 呼叫 `run_writing_hooks`       |
| PostToolUse (section complete) | **B1-B16** (post-section)     | Agent 依 SKILL.md 呼叫 `run_writing_hooks(hooks='post-section')` |
| PostToolUse (manuscript done)  | **C1-C13** (post-manuscript)  | Agent 依 SKILL.md 呼叫                                           |
| PreToolUse (git commit)        | **P1-P8, G1-G9** (pre-commit) | Agent 載入 git-precommit SKILL.md 執行                           |
| Stop                           | **Memory sync**               | 注入提醒更新 memory-bank/                                        |
| SubagentStart (reviewer)       | **E1-E5** (EQUATOR)           | 注入上下文至 reviewer subagent                                   |

### 非 Lifecycle 的 Checks（由 SKILL.md 指導）

| Check 系列                 | 觸發時機        | 機制                                                               |
| -------------------------- | --------------- | ------------------------------------------------------------------ |
| **D1-D9** (Meta-Learning)  | Phase 10        | Agent 依 auto-paper SKILL.md 呼叫 `run_meta_learning`              |
| **F1-F4** (Data Artifacts) | post-manuscript | Agent 依 SKILL.md 呼叫 `validate_data_artifacts`                   |
| **R1-R6** (Review Hooks)   | Phase 7 submit  | Agent 依 SKILL.md 呼叫 `submit_review_round` → `ReviewHooksEngine` |

---

## State File 通訊

```
.github/hooks/_state/
├── session_context.json    # SessionStart 寫入，其他 hook 讀取
│   └─ { mode, doing, next_action, active_project, writing_session, ... }
└── session_audit.jsonl     # 所有 hook 追加寫入
    └─ { timestamp, event, tool, ... }  (一行一筆 JSON)
```

**生命週期**：

- `session_context.json`：SessionStart 建立 → PreToolUse/SubagentStart 讀取 → Stop 刪除
- `session_audit.jsonl`：全程追加 → Stop 寫入結算 → 保留供審計

---

## Hook I/O 規格

### 共通輸入（stdin JSON）

所有 hooks 都會收到：

```json
{
  "tool_name": "...",       // PreToolUse, PostToolUse
  "tool_input": {...},      // PreToolUse
  "tool_result": "...",     // PostToolUse
  "userMessage": "...",     // UserPromptSubmit
  "agentName": "..."        // SubagentStart
}
```

### 輸出格式

| Hook        | 可用輸出欄位                          | 說明               |
| ----------- | ------------------------------------- | ------------------ |
| PreToolUse  | `permissionDecision` (allow/deny/ask) | 控制工具是否執行   |
| PreToolUse  | `permissionDecisionReason`            | 向 Agent 解釋原因  |
| PreToolUse  | `updatedInput`                        | 修改工具輸入參數   |
| PreToolUse  | `additionalContext`                   | 注入上下文         |
| PostToolUse | `decision` (block)                    | 阻斷結果傳回 Agent |
| PostToolUse | `additionalContext`                   | 注入上下文         |
| 其他        | `additionalContext`                   | 注入上下文         |

---

## 配置檔案

**位置**：`.github/hooks/mdpaper-lifecycle.json`

```json
{
  "version": 1,
  "hooks": {
    "SessionStart": [{ "type": "command", "command": "...", "timeout": 10 }],
    "UserPromptSubmit": [{ "type": "command", "command": "...", "timeout": 5 }],
    "PreToolUse": [{ "type": "command", "command": "...", "timeout": 5 }],
    "PostToolUse": [{ "type": "command", "command": "...", "timeout": 15 }],
    "PreCompact": [{ "type": "command", "command": "...", "timeout": 10 }],
    "SubagentStart": [{ "type": "command", "command": "...", "timeout": 5 }],
    "Stop": [{ "type": "command", "command": "...", "timeout": 10 }]
  }
}
```

**Timeout 設計**：

- 5s：輕量 hook（prompt-analyzer, pre-tool-guard, subagent-init）
- 10s：中量 hook（session-init, pre-compact-save, session-stop）
- 15s：重量 hook（post-tool-check，可能需要讀取多個狀態檔案）

---

## 與 pubmed-search-mcp 的 Hooks 比較

| 特性   | pubmed-search-mcp                                  | mdpaper (本專案)                   |
| ------ | -------------------------------------------------- | ---------------------------------- |
| 範圍   | 單一 MCP 服務的 pipeline 控管                      | 整個 workspace 生命週期            |
| Events | 5 (session, prompt, preTool, postTool, sessionEnd) | 7 (+ PreCompact, SubagentStart)    |
| 策略   | Pipeline 強制、結果評估                            | 模式保護、品質 Hook 觸發、記憶管理 |
| State  | workflow tracker + session context                 | session context + audit trail      |
| 跨平台 | sh + ps1                                           | 僅 sh（Linux/macOS）               |

---

## 安全考量

1. **PreToolUse deny** 是硬閘——Agent 無法繞過被 deny 的工具呼叫
2. **Exit code 2** = blocking error，防止 hook 腳本錯誤影響 Agent 運行
3. **Mode protection** 確保研究人員不會意外修改框架核心代碼
4. **Destructive command pattern** 使用白名單式檢查（只攔截已知危險模式）
5. **State 目錄** 不含敏感資料，僅有模式和工具名稱
6. **.gitignore** 應排除 `_state/` 目錄（暫存資料）

---

## 依賴

- **jq** — 必要的 JSON 處理工具。若未安裝，所有 hook 會自動降級（exit 0 = 全部放行）
  - 安裝：`sudo apt install jq` (Ubuntu) / `brew install jq` (macOS)
- **bash** — 4.0+ (Linux/macOS 內建)

---

## 未來擴展

- [ ] **Windows 支援**：為每個 .sh 建立對應 .ps1（參考 pubmed-search-mcp）
- [ ] **SubagentStop**：如需監控 subagent 輸出品質
- [ ] **PreToolUse updatedInput**：自動修正工具參數（如自動補全 project slug）
- [ ] **PostToolUse decision: block**：攔截低品質工具輸出（目前未使用）
- [ ] **Multi-hook 串聯**：同一事件可配置多個 hook 依序執行
