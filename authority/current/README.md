# Current Authority

這個目錄只放 current authority registry。Registry 綁定的 current documents 位於專案根目錄；
其中包含 live authority、reference-only 與可由多個 partition 共用的 canonical。

禁止：

- archive 檔案在這裡冒充 current
- 用 mtime / filename 排序猜最新版本
- 用 Memory / conversation history 補缺失 authority
- revision = UNSET 時繼續 production execution

第一次正式啟用前，請把 registry.json 每個 document 的 exact revision 與 current file 準備好。

每個 authority document 使用固定結構：

```text
# <DOCUMENT NAME>

ROLE: LIVE_AUTHORITY | REFERENCE_ONLY | CANONICAL
STATUS: UNSET | CURRENT
REVISION: <exact revision>

## Current Authority | Reference Content | Canonical Content

<current authoritative content>
```

Registry schema v4 將 runtime Owner、normative document 與 authority partition 分開，並鎖定
可匯入的 authority identity：

- `documents` 保存 document role、authority identity、啟用 revision 與 current path。
- `identity` 是允許接入的精確 authority identity；它本身不會啟用 document。
- 正式啟用時，registry `revision` 與 file `REVISION` 都必須完全等於 `identity`。
- `entries` 只保存既有五個 Owner 的 `normative_authority`、`authority_partition`
  與 reference binding。
- `SALES_HUMAN` Owner 的 normative authority 是 `SALES`；`SALES_HUMAN_REFERENCE`
  只能以 `REFERENCE_ONLY` 綁定，不能成為 live authority。
- `VISUAL` 與 `EXECUTION` 的 normative authority 都是同一份 `REAL_CAR` canonical，
  但 partition 分別是 `VISUAL_JUDGE` 與 `EXECUTION_LAB`。共用 document 與 revision
  不會合併 Owner 或 effect 權限。
- Registry 不接受獨立的 `VISUAL` 或 `EXECUTION` authority document。

安全啟用順序：

1. 保持 registry revision 為 `UNSET`。
2. 確認 registry 已登記核准的 exact `identity`。
3. 寫入所有已綁定 document，將 status 設為 `CURRENT`，並以該 identity 填入 file revision。
4. 確認 document role、identity、revision、path、binding 與內容完整後，最後才更新 registry revision。

file revision、registry revision 與 identity 必須完全相同；任一 role、status、identity、revision、
content、path 或 binding 未設定或不一致時，resolver 必須 fail-close。
