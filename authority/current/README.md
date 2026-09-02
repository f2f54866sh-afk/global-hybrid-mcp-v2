# Current Authority

這個目錄只放 current authority registry。Registry 綁定的原生 Canonical 位於專案
根目錄；其中包含 live authority、reference-only 與可由多個 partition 共用的
canonical。

禁止：

- archive 檔案在這裡冒充 current
- 用 mtime / filename 排序猜最新版本
- 用 Memory / conversation history 補缺失 authority
- revision = UNSET 時繼續 production execution

第一次正式啟用前，請把 registry.json 每個 document 的 `expected_revision`
與原生 current file 準備好。

原生 Canonical 必須直接保存，不另外包上 `ROLE / STATUS / REVISION / section`
wrapper。Resolver 只從原生文件開頭的 metadata 區塊解析：

```text
# <native canonical title>

CURRENT_REVISION: `<exact revision>`
STATUS: `CURRENT`
OWNER: `<native owner>`                       # 原文件有才驗證
AUTHORITY_ROLE: `<registry role>`             # 原文件有才驗證

<unchanged native canonical content>
```

Registry schema v5 將 runtime Owner、normative document 與 authority partition 分開：

- `documents` 只保存 document role、`expected_revision` 與 exact root path。
- 正式啟用時，registry `expected_revision` 必須完全等於原生文件
  `CURRENT_REVISION`，且原生 `STATUS` 必須是 `CURRENT`。
- `entries` 只保存既有五個 Owner 的 `normative_authority`、`authority_partition`
  與 reference binding。
- `SALES_HUMAN` Owner 的 normative authority 是 `SALES`；`SALES_HUMAN_REFERENCE`
  只能以 `REFERENCE_ONLY` 綁定，不能成為 live authority。
- `VISUAL` 與 `EXECUTION` 的 normative authority 都是同一份 `REAL_CAR` canonical，
  但 partition 分別是 `VISUAL_JUDGE` 與 `EXECUTION_LAB`。共用 document 與 revision
  不會合併 Owner 或 effect 權限。
- Registry 不接受獨立的 `VISUAL` 或 `EXECUTION` authority document。

安全啟用順序：

1. 保持 registry `expected_revision` 為 `UNSET`。
2. 將經核准的原生 Canonical 原樣寫入 exact root path，不改寫、不包裝、不摘要。
3. 驗證原生 `CURRENT_REVISION / STATUS`，以及存在時的 `OWNER / AUTHORITY_ROLE`。
4. 確認 role、revision、path、binding、partition 與內容完整後，最後才更新
   registry `expected_revision`。

file `CURRENT_REVISION` 與 registry `expected_revision` 必須完全相同；任一
role、status、revision、content、path、binding 或 partition 未設定或不一致時，resolver
必須 fail-close。
