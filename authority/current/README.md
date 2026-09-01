# Current Authority

這個目錄只放 live current authority pointer 與 current authority file。

禁止：

- archive 檔案在這裡冒充 current
- 用 mtime / filename 排序猜最新版本
- 用 Memory / conversation history 補缺失 authority
- revision = UNSET 時繼續 production execution

第一次正式啟用前，請把 registry.json 每個 Owner 的 exact revision 與 current file 準備好。
