# VEHICLE_KNOWLEDGE_BASE｜台灣中古車知識 Canonical

CURRENT_REVISION: `VEHICLE_KNOWLEDGE_BASE_20260901_SCHEMA_DATA_SEPARATION`
OWNER: `LIBRARY`
STATUS: `CURRENT`
CONTENT_COMPLETENESS: `PARTIAL / FOUNDATIONAL_COVERAGE_TRACKED`
DATA_STORE_ROOT: `/LibraryData`
DATASET_RULE: `CANONICAL DEFINES SCHEMA/AUTHORITY/RETRIEVAL; FACT ROWS LIVE IN DATA STORE`

## 1. 目的｜Library 是可靠資料層，不是決策邏輯
Library 的本質固定為**可隨時調取、可持續更新、可追溯的台灣中古車資料／知識庫**。它只把資料蒐集得更完整、驗證得更準、更新得更即時、調取得更精確；不因資料很多就取得 Sales、Human、Visual、Execution 或 GLOBAL 的判斷權。

固定能力只有四類：
`COLLECT / VERIFY / UPDATE / RETRIEVE`。

固定邊界：
- Library 可以保存 hard fact、current market observation、closed-transaction evidence、market/audience observation、modification ecosystem evidence、query-language evidence。
- Library 可以回答「資料顯示什麼／目前觀察到什麼／來源之間如何衝突／什麼時間有效」。
- Library 不回答「所以這台應該賣給誰／客人一定在意什麼／文案怎麼寫／畫面怎麼做／該採哪個 execution route／是否應成交」。
- `DATA_EVIDENCE != DOMAIN_DECISION`；下游 owner 只消費資料，不把 Library evidence 當成自己的決策已被替代。

## 2. Entity
市場/車型知識至少依需要辨識：
`MAKE / MODEL / GENERATION / BODY / MODEL_YEAR / MARKET / TRIM / PACKAGE / POWERTRAIN / DRIVETRAIN`

維度不足時不得跨 scope 推廣結論。
個別實車另標 `VEHICLE_INSTANCE`；市場規格 ≠ 單車實配，單車實配 ≠ 市場標配。

## 3. Fact authority
- `A INSTANCE_LOCAL_MUTABLE`：當前在庫/使用者實車觀察、里程、整理、已實測配備等；以最新可靠 instance evidence 為準，客觀衝突時再驗。
- `B MARKET_HARD_FACT`：總代理/原廠引進、MY、標配/選配、動力、MSRP、法規等；用 scope-matching authoritative evidence。
- `C PRACTICAL_FACT`：常見故障、維修、持有成本、當前中古市場實務；採台灣多來源實務證據並標 transfer/uncertainty。
- `D SALES_HISTORY`：歷史銷售文案/對話，只能從 SALES_ARCHIVE 取用，不升格成車輛事實。

## 4. Source role
依問題選來源角色，不固定單一來源永遠最高：
- HARD_FACT → 原廠/總代理/法規/金融機構等第一方。
- PRACTICAL_FUNCTION → 台灣實測/車主/專業媒體。
- REPAIR_PRACTICE → 台灣專修、技師、拆解、長期維修實務。
- MARKET/COST → 多個台灣市場/維修/交易來源交叉；公開刊登只先形成 market-listing candidate，需經 comparable qualification 後才可進 asking-market view；成交價需 closed-transaction evidence。廣告 funnel／成交率屬 Sales outcome scope，Library 不從 listing 推導。
海外資料必須標 `MARKET_TRANSFER_RISK`，不能直接套台灣。

## 5. Evidence lineage
鏡像、轉載、同作者/店家多平台重貼、同原始材料衍生摘要、Library duplicate 不算獨立 evidence。
`SOURCE_COUNT ≠ SOURCE_INDEPENDENCE`

## 6. Current / unstable facts
價格、行情、法規、金融方案、當期配備/官方頁面、當前市場等有時間敏感性；使用時需要 `LAST_VERIFIED` 或當下重新驗證。`UNKNOWN ≠ FALSE`。

## 7. Sales ↔ Library fact interface｜最小契約
Library 不主動把整個知識庫倒給 Sales；跨域輸入只接受下列 fact request 欄位，任何未列出的 Sales/Human 內部狀態或策略都不得參與 retrieval。

Sales/Human request：
`REQUEST_PACKET_ID / CONSUMER_ID / PROJECTION_ID / PROJECTION_SCHEMA_VERSION / QUESTION / ENTITY_OR_INSTANCE / KNOWN_SCOPE / FACT_DIMENSIONS_NEEDED / CURRENTNESS_REQUIREMENT / AS_OF_MODE(optional) / REQUESTED_FACT_SHAPE`

Library 固定：
`FACT_REQUEST → ENTITY/SCOPE_RESOLUTION → CURRENT_AUTHORITY_FILTER → EXACT_RETRIEVAL_OR_GAP → FRESHNESS/CONFLICT_CHECK → FACT_RESULT → EXIT_LIBRARY`

Library result：
`LIBRARY_PACKET_ID / REQUEST_PACKET_ID / CONSUMER_ID / PROJECTION_ID / PROJECTION_SCHEMA_VERSION / FACT_ID_OR_GAP / FACT_VALUE_OR_GAP / SCOPE / AUTHORITY_STATE / VERSION / ASSERTION_CLASS / CURRENTNESS_STATE / DATA_SENSITIVITY_CLASS / SOURCE_ROLE / OBSERVED_AT(if relevant) / EFFECTIVE_FROM(if relevant) / EFFECTIVE_TO(if relevant) / LAST_VERIFIED / CONFLICTS / MISSING_DIMENSIONS / LINEAGE_ROOT_ID / PROVENANCE_POINTER`

只回目前任務需要的 facts。Sales 回到自己的 owner scope 決定順序、說明量、tradeoff、comparison、fit 或 next step；Library 不參與這些判斷。

## 8. 禁止
- 生成海報、舊文案、圖片描述、OCR、摘要未驗證不得自動成為 fact。
- 不因單一海外案例把通病/配備/維修費硬套台灣。
- 不把「查不到」說成「不存在」。


## 9. Foundational KB coverage｜高頻基礎知識不是「用到才臨時查」
`TASK_SUFFICIENT ≠ LIBRARY_COMPLETE`。

「只回目前任務需要的 facts」只限制 **輸出 packet 的大小**，不代表 Library 只需要保存當前任務剛好用到的資料。

Library 必須維護 `HIGH_FREQUENCY_FOUNDATION_MATRIX`，優先覆蓋台灣中古車業務會反覆使用、可跨車重用的基礎事實：
- `VEHICLE_CLASS / USE_TYPE / OWNER_NAME_TYPE / REGISTRATION_TYPE`
- 自用 / 營業 / 公司名義持有的差異
- 牌照稅 / 公路養管費 / 驗車 / 保險 / 金融 / 持有成本基本規則
- 排氣量與相關級距
- 常見車籍、市場、總代理/外匯、年份/世代/版本分類
- 現有庫存與近期詢問車的固定技術、版本、配備 truth

每一 coverage domain 至少記：
`COVERAGE_STATE=VERIFIED|PARTIAL|MISSING / QUERY_KEYS / SCOPE / LAST_VERIFIED / SOURCE_ROLE / VERSION`

高頻、可重用、與目前業務直接相關的 `PARTIAL/MISSING` 是正式 `FOUNDATIONAL_COVERAGE_DEBT`。
不得因「目前沒有客人問」永久不補；也不得擴張成無限百科式收集。

## 10. Live query routing｜Library-first
汽車 fact query 固定：
`QUERY_MODEL → ENTITY/CLASSIFICATION_RESOLUTION → KB_RETRIEVE → FRESHNESS/CONFLICT → ANSWER_OR_VERIFY_GAP`

只有：
`KB_MISS / PARTIAL / STALE / CONFLICT / HIGH_RISK_LATEST_REQUIRED`
才可外部驗證，而且只補缺口，不得把已 verified 欄位整批重新查一次。

稅費 / 車籍問題在任何金額前先解析：
`VEHICLE_CLASS / USE_TYPE / OWNER_NAME_TYPE / REGISTRATION_TYPE / DISPLACEMENT_RANGE`

硬限制：
- `公司名義 ≠ 營業用`
- 分類未解析不得先報單一金額
- KB 已有足夠版本/來源時不得無必要外查
- 每次 query 留 `QUERY_HIT_STATE=HIT|PARTIAL|MISS|CONFLICT|STALE`

## 11. Fact persistence closure｜查過不等於學會
可重用 verified fact 只有完成：
`STRUCTURED_WRITE → LOCATION/RESOURCE_ID → VERSION → READBACK → QUERY_KEY_BINDING → MATCHING_CONSUMER_READ_USE`
才算 `PERSISTED_VERIFIED`。

以下都不算真正入庫：
- 只出現在某次回答
- automation prompt
- memory / summary
- generated marketing artifact
- 舊文案 / 廣告圖
- runtime output 欄位寫著 `VERIFIED_STATIC_FACTS`

若因 `KB_MISS` 才去外部驗證，同一閉環必須更新 KB；若當下沒有 durable write path，標：
`PERSISTENCE_BLOCKED / OWNER_ACTION_REQUIRED`
不得宣稱「已學會」。

同類或同義 query 在前一次已補完後再次無故 `MISS`：
`LIBRARY_PERSISTENCE_REGRESSION`

## 12. Coverage closure / regression
固定檢查：
1. 已知 static fact 是否直接 KB HIT；
2. MISS 後是否只補缺口；
3. 新 verified fact 是否真正 persist；
4. 同義下一問是否可 HIT；
5. `TASK_SUFFICIENT` 是否被錯當 `KB_COMPLETE`；
6. generated artifact 是否被錯升 authority；
7. wrong market/year/trim/vehicle class 是否跨 scope 套用。

同類高頻基礎問題第二次仍因資料未沉澱而臨時外查：
`FOUNDATIONAL_COVERAGE_CLOSURE_FAILURE`


## 13. LIVE_QUERY_PRECALL_BINDING｜規則必須綁到即時工具選擇
`LIBRARY_FIRST` 不只是一條研究原則，而是 live fact query 的 action gate。

任何汽車 fact 問題在呼叫 Web／外部搜尋／外部 source fetch 前，必須先建立 `LIBRARY_QUERY_COMMIT_RECORD`：
`QUERY_ID / USER_ASK / QUERY_MODEL / ENTITY_CLASSIFICATION / KB_QUERY_KEYS / KB_RETRIEVAL_ATTEMPT / QUERY_HIT_STATE / VERSION_STATE / CONFLICT_STATE / EXTERNAL_GAP / EXTERNAL_AUTHORIZATION_REASON`

只有 `EXTERNAL_GAP` 明確屬於下列之一才可外查：
- `KB_MISS`
- `KB_PARTIAL_MATERIAL_GAP`
- `KB_STALE_FOR_REQUESTED_CURRENTNESS`
- `KB_INTERNAL_CONFLICT_UNRESOLVED`
- `USER_EXPLICITLY_REQUESTED_EXTERNAL_VERIFY`

若沒有這份 commit record，外查動作必須 BLOCK：
`EXTERNAL_TOOL_CALL_WITHOUT_LIBRARY_COMMIT = FAIL`。

### 13.1 USER_CHALLENGE_CONFLICT_GATE
使用者說「不對／你確定嗎／再確認／前後不一樣」時，預設只代表 `ANSWER_OR_KB_CONFLICT_RECHECK`，**不等於** `HIGH_RISK_LATEST_REQUIRED`，也不等於外查授權。

固定流程：
`USER_CHALLENGE → RE-READ_CURRENT_KB → RECHECK_ENTITY/CLASSIFICATION → COMPARE_PREVIOUS_ANSWER_WITH_KB → LOCATE_DIVERGENCE → ANSWER_OR_DECLARE_KB_GAP`

只有完成上述流程後仍確認是 `KB_MISS/PARTIAL/STALE/CONFLICT`，才進 external verify。

### 13.2 SAME-TURN QUESTION STABILITY
同一話題中，已解析的 `USER_ASK / OUTPUT_SHAPE / ENTITY_CLASSIFICATION` 必須保持，除非使用者明確改題。
不得因後續追問把：
- 「我要全年總額」改成「我要拆解原理」；
- 「公司名義」自行改成「營業用」；
- 「自用 vs 公司」自行重寫成另一組比較維度。

違反標：`QUESTION_REINTERPRETATION_REGRESSION`。

### 13.3 ANSWER CONTRACT FIRST
對明確數字題，先滿足使用者指定輸出：例如要求「全年牌照＋養管費總額」，主回答必先給總額表。組成、制度解釋只能作次要補充，不得取代主答案。
`REQUESTED_OUTPUT_SHAPE_MISSED = FAIL`。


## 13.4 LIBRARY PURPOSE｜Verified fact store，不是搜尋快取
Library 的存在目的：把已經證實、可追溯、可重用的事實固定下來，避免 live answer 再搜尋、重算、拼湊或靠印象改寫。

任何數值/法規/稅費 fact 要進 VERIFIED 區，必須同時具備：
`FACT_VALUE + ENTITY/SCOPE + CLASSIFICATION + PRIMARY_SOURCE_POINTER + SOURCE_TABLE/ROW_OR_FIELD + LAST_VERIFIED + VERSION + DERIVATION(if calculated) + CONFLICT_CHECK + READBACK`。

硬限制：
- `SOURCE_NAME_ONLY != EVIDENCE_CHAIN`；只寫「財政部/公路局」不夠。
- `SEARCH_RESULT != VERIFIED_FACT`；搜尋結果只能是候選。
- `USER_MEMORY != FACT_EVIDENCE`；使用者記憶只能觸發 conflict review。
- `GENERATED_AD / OLD_ANSWER / SUMMARY != FACT_EVIDENCE`。
- derived total 必須可由同 scope 的 verified component rows 重算一致。
- 任一 evidence pointer 缺失、scope 未定、分類未定、來源互相矛盾：`QUARANTINED / UNVERIFIED`，不得對外當確定答案。

對高頻基礎資料，目標不是「記很多」，而是「每一筆能追到證據、下次直接 HIT 且答案不漂移」。


## 14. FOUNDATIONAL_TAX_DATASET_REGISTRY｜目前未完成，主 KB 不保存隔離數字
DATASET_ID: `TW_USED_CAR_ANNUAL_TAX_COST`
AUTHORITY_STATE: `NOT_READY`
QUERY_READY: `NO`
REASON: `EVIDENCE_CHAIN_INCOMPLETE + CLASSIFICATION_CONTAMINATION`
QUARANTINE_POINTER: `/Archive/VEHICLE_KB_QUARANTINE_TAX.md`

硬限制：
- 主 query-ready KB 不保留待驗證數字，避免 chunk retrieval 遺失上層 QUARANTINED 標記後洩漏到答案。
- FACT_QUERY_CONSUMER 查此 dataset 時先讀 registry；`QUERY_READY=NO` 直接回 `KB_GAP/BUILD_REQUIRED`，不得 broad search main Library 找相近數字。
- 完成 background primary-source rebuild 後，另建立 query-ready VERIFIED dataset/view，registry 才能改為 READY。

## 15. 車型名稱不得直接決定稅率｜classification rule only
AUTHORITY_STATE: `VERIFIED_RULE_ONLY`
`MODEL_NAME != REGISTRATION_CLASS`。Ford Ranger、皮卡、雙廂車等車型名稱本身不得直接綁定任何稅率；必須先確認實際 `VEHICLE_CLASS / REGISTRATION_TYPE / USE_TYPE`。
沒有 instance classification 時，不得把任一稅率情境冒充該車實際稅額。
數值候選已移至 quarantine，不得由本 section 取值。

## 16. FOUNDATIONAL_PREBUILD_PIPELINE｜基礎資料要在背景研究階段先建好，不等 live 問題才拼

### 16.1 Read / Write plane 必須分離
Library 保持單一 owner，但內部固定分成兩個 plane：

**WRITE_PLANE｜研究/更新面**
`SOURCE_DISCOVERY → SCOPE_BINDING → AUTHORITY/EVIDENCE_CHECK → CONFLICT/LINEAGE → STRUCTURED_WRITE/REPLACE → READBACK → QUERY_VIEW_REBUILD → REGRESSION`
- `BACKGROUND_FOUNDATIONAL_BUILD` 與需要 persistence 的 `CONTROLLED_GAP_RECOVERY` 都屬 WRITE_PLANE。
- 可處理來源、版本、quarantine、supersession、derivation、dataset build。

**READ_PLANE｜即時查詢面**
`FACT_REQUEST → ENTITY/SCOPE → CURRENT/QUERY_READY FILTER → EXACT_ROW_OR_GAP → FRESHNESS/CONFLICT → FACT_RESULT`
- `LIVE_QUERY_RETRIEVAL` 只消費已建立的 current/query-ready truth；不得把整套 research workflow 帶進 live path。
- Read plane 只接受 fact request contract；Sales/Human 內部狀態或策略不得成為 retrieval key。

核心：`WRITE_PLANE_BUILDS_TRUTH → VERIFIED_FACT_STORE → READ_PLANE_DIRECT_HIT`。
若高頻基礎題在 live 才首次需要廣泛外查，這是 `FOUNDATIONAL_PREBUILD_FAILURE`；若必須救援，只切到受控 WRITE_PLANE 補缺口，完成 write/readback 後再回 READ_PLANE。

### 16.2 高頻基礎資料的預建責任
在不做百科式無限擴張的前提下，Library 應優先主動完成與台灣中古車業務高頻直接相關的可重用資料集，例如：
- 車種 / 用途 / 登記分類與常見口語名稱的正規映射；
- 牌照稅 / 公路養管費 / 驗車 / 保險 / 持有成本的完整級距表與適用條件；
- 常見排氣量級距、柴油/汽油/油電等影響條件；
- 現有庫存與近期詢問車款的年份、世代、台灣/外匯、版本、動力、驅動、標配/選配等固定 truth；
- 與成交/持有直接相關且會反覆被問的法規或行政基礎。

Priority 不再使用單一路徑硬排序；固定改為：
`BUSINESS_IMPACT × QUERY_FREQUENCY × CURRENT_INVENTORY_RELEVANCE × ERROR_COST × REUSABILITY × STALENESS_RISK × INFORMATION_GAIN`。

`CURRENT_INVENTORY_RELEVANCE` 只是權重，不是全域前置 gate。current inventory 尚未完成時，只阻擋**依賴 current inventory 的 live 排名／主打／廣告決策**；不得因此停止與 current inventory 無依賴關係的車型市場研究、基礎資料預建、market intelligence、retrieval learning 或其他高價值 frontier。`ONE_FRONTIER_BLOCKED != LIBRARY_RESEARCH_BLOCKED`。

### 16.3 完成一個基礎資料集的最低條件
不能只存一兩個數字。每個 foundational dataset 要能被標為 `VERIFIED_DATASET`，至少必須具備：
`DIMENSION_MATRIX + COMPLETE_RELEVANT_ROWS + ENTITY/SCOPE + CLASSIFICATION_KEYS + PRIMARY_SOURCE_POINTER_PER_FIELD_OR_ROW + SOURCE_TABLE/ROW/FIELD + LAST_VERIFIED + VERSION + DERIVATION + CONFLICT_CHECK + READBACK + SAMPLE_QUERY_HIT`。

若只知道某一例、某張廣告、某次回答或某個總額，不算 dataset coverage。
`PARTIAL_ROWS != VERIFIED_DATASET`。

### 16.4 Live query 行為
Live fact query 固定：
`USER_ASK -> QUERY_KEYS -> ENTITY/CLASSIFICATION -> EXACT_LIBRARY_ROW -> ANSWER`。

禁止：
- live 當下從多個公開網頁東湊西湊不同欄位；
- 用搜尋摘要補 Library 缺的數字；
- 用相近車種/相近排量/相近用途推算；
- 用 user memory、舊回答或廣告成品選擇哪個數值看起來合理；
- 在沒有 exact verified row 時自行組合 derived total。

若 exact row 缺失：
1. 標 `KB_GAP + FOUNDATIONAL_PREBUILD_FAILURE`；
2. 不得假裝 Library 已有；
3. 若必須即時回答，只能做 `CONTROLLED_GAP_RECOVERY`：限定 primary/authoritative source、只驗缺口、逐欄保存 evidence chain、完成 write/readback 後才對外給確定數字；
4. 禁止 broad-search recomposition。

### 16.5 防止「搜尋結果變答案」
正式拒絕：`SEARCH_RESULT_RECOMPOSITION`。
候選資料必須先過：
`SOURCE_CAPTURE -> FIELD_EXTRACTION -> SCOPE_BINDING -> CLASSIFICATION_BINDING -> CONFLICT_CHECK -> DERIVATION_CHECK -> STRUCTURED_WRITE -> READBACK -> SAMPLE_RETRIEVAL`。
在此之前只能是 `RESEARCH_CANDIDATE`，不能作 user-facing exact fact。


## 17. USED_CAR_TAX_INTENT_MODEL｜先理解中古車業務在比較什麼

### 17.1 使用者實務語義優先於抽象 owner-type 拆解
在中古車業務的持有成本/節稅問題中，常見問法如：
`自用牌 vs 公司牌 / 公司用 / 貨車牌 / 節稅牌 / 2.0或3.2一年多少`。

這類 query 的預設商業意圖是比較：
`NORMAL_SELF_USE_PASSENGER_REGISTRATION vs LEGAL_TAX_SAVING_TRUCK_REGISTRATION_SCENARIO`
而不是先把問題重寫成 `個人名義 vs 公司名義 vs 營業用`。

官方分類仍需精確綁定，但不得讓抽象 legal/owner taxonomy 取代使用者真正要的「一般牌一年多少、節稅牌一年多少、差多少」。

### 17.2 Answer-shape contract
對這類高頻問題，Library 應能直接支援：
`排氣量 × 一般自用小客車 × 節稅貨車登記`，並拆列：
`牌照稅 / 公路養管費(俗稱燃料費) / 年合計 / 年差額 / 官方登記名稱與適用條件`。

主答案先給比較表；官方術語與限制只作必要註記，不得先輸出長篇分類說明。

### 17.3 Query crosswalk
- `自用牌`：優先解析為一般自用小客車/使用者所指正常自用方案，再用實際車種確認。
- `貨車牌 / 節稅牌`：優先解析為使用者要比較的合法貨車登記節稅方案，再以行照車種/用途確認適用 row。
- `公司牌`：在「一年稅金/節稅多少」語境中，先視為 `TAX_SAVING_REGISTRATION_INTENT`，不得自動等同 `OWNER_NAME_TYPE=公司` 或 `USE_TYPE=營業用`；必要時用一句話說明官方分類名稱。

### 17.4 Benchmark from current failure
2026-08-19 current failure 證明：若使用者問 2.0/3.2 柴油年度稅金，系統卻先展開公司名義/營業用途 taxonomy、反覆外查、再自行拼值，標：
`USED_CAR_INTENT_MISMODELED_AS_OWNER_TYPE + SIMPLE_FOUNDATIONAL_QUERY_OVERCOMPLICATED`。

Google AI 截圖僅作 `USER_PROVIDED_BENCHMARK_REFERENCE`，證明使用者期望的輸出結構是「2.0/3.2 × 自用小客車/貨車牌 × 牌照/燃料/總額」的直接比較；截圖數值本身不得因畫面存在就自動升為 VERIFIED fact，仍須由 BACKGROUND_FOUNDATIONAL_BUILD 的 primary-source evidence chain 入庫。


## 18. QUERYABLE_KNOWLEDGE_MODEL｜Library 不只存資料，還要可被精準調用

### 18.1 Record contract
每一筆可供 live exact answer 使用的 hard fact 必須具備可查詢主鍵與 authority state：
`FACT_ID / DATASET_ID / VIEW_ID(optional) / DOMAIN / ENTITY_SCOPE / DIMENSION_KEYS / FACT_VALUE / UNIT / AUTHORITY_STATE / ASSERTION_CLASS / DATA_SENSITIVITY_CLASS / SOURCE_POINTER / LINEAGE_ROOT_ID / OBSERVED_AT(if relevant) / EFFECTIVE_FROM(if relevant) / EFFECTIVE_TO(if relevant) / RECORDED_AT / LAST_VERIFIED / CURRENTNESS_STATE / VERSION / QUERY_ALIASES`。
`AUTHORITY_STATE` 僅 `VERIFIED` 可直接進 user-facing exact answer；`QUARANTINED / UNVERIFIED / REJECTED / HISTORICAL` 只能作 conflict/evidence clue，不得被 retrieval ranking 直接提升。

### 18.2 Materialized comparison view
高頻中古車業務問題不應每次臨場 join/recompute。可建立 `MATERIALIZED_VIEW`，但 view 只能引用同 scope 的 VERIFIED base facts，並保存：
`VIEW_ID / QUERY_PURPOSE / DIMENSIONS / REQUIRED_COLUMNS / SOURCE_FACT_IDS / DERIVATION / VERSION / LAST_VERIFIED`。
例如持有成本比較 view 應能直接提供：
`排氣量 × 一般自用方案 × 合法節稅貨車登記方案 × 牌照稅 × 公路養管費 × 年合計 × 年差額`。
若任何 source fact 降級/過期，dependent view 自動 `STALE/QUARANTINED`，不得繼續回答。

### 18.2.1 Dataset registry routing
FACT_QUERY_CONSUMER 不得一開始 broad-search 整個 Library 找數字；先查 `DATASET_REGISTRY` 取得 `DATASET_ID / QUERY_READY / AUTHORITY_STATE / TARGET_FILE_REF_OR_VIEW_ID / VERSION`。
只有 `QUERY_READY=YES + AUTHORITY_STATE=VERIFIED` 才進 target dataset/view retrieval。`NOT_READY/QUARANTINED` 直接 `KB_GAP`。
這可避免 semantic search 把歷史/隔離數字排到前面。

### 18.3 Retrieval authority filter
Library semantic search 只負責找候選，不代表可回答。正式取值流程：
`SEMANTIC_CANDIDATES -> AUTHORITY_STATE_FILTER(VERIFIED_ONLY) -> SCOPE_MATCH -> DIMENSION_MATCH -> VERSION/FRESHNESS_CHECK -> EXACT_ROW(S) -> ANSWER_ASSEMBLY`。
若搜尋排名第一是 QUARANTINED，而後面才有 VERIFIED，必須丟棄前者；若沒有 VERIFIED exact row，回 `KB_GAP`，不得拿 quarantine row 補值。
正式 failure：`SEARCH_RANK_MISTAKEN_FOR_AUTHORITY / QUARANTINED_ROW_LEAKED_TO_ANSWER / APPROXIMATE_ROW_SUBSTITUTION`。

### 18.4 Business-language alias layer
Library 要保存業務常用語到 query plan 的 alias/crosswalk，但 alias 不等於官方 classification truth。
例如 `自用牌 / 公司牌 / 貨車牌 / 節稅牌` 先映射到 `QUERY_PURPOSE` 與候選比較 view，再由 VERIFIED classification row 決定實際官方類別。
`ALIAS -> QUERY_PLAN`，禁止 `ALIAS -> TAX_VALUE` 直接跳值。

### 18.5 Deterministic answer assembly
FACT_QUERY_CONSUMER 可做的運算只限 deterministic assembly：排序、欄位選擇、同 scope verified components 相加、verified scenarios 差額。
任何 derived value 必須帶 `SOURCE_FACT_IDS + FORMULA`；不得跨 scope join、不得從 search snippet 重算、不得用「合理看起來」補缺值。

### 18.6 Sample retrieval tests
每個 foundational dataset 完成前至少通過：
1. exact wording hit；
2. synonym/業務口語 hit；
3. reordered dimensions hit；
4. quarantined-result-first adversarial case仍只取 VERIFIED；
5. missing dimension -> KB_GAP，不近似套值；
6. stale version -> refresh flag，不默默沿用；
7. same fact repeated query -> same FACT_ID/version/value；
8. comparison query -> same verified rows + deterministic diff。
只有資料存在但無上述 retrieval tests，不得標 `QUERY_READY`。


## 19. LIVE_QUERY_RETRIEVAL_SIMULATION｜資料不只要正確，也要能被自然問法精準調用

### 19.1 Purpose
Library 的 query-ready 判定包含 live-style retrieval 測試，但只測 **query semantics / scope / authority / answer shape**；Sales/Human 內部狀態或策略不得作 retrieval condition。

測試使用 synthetic user/customer utterance，不得生成 synthetic fact value。若 dataset 未 ready，正確 expected result 是 `KB_GAP/BUILD_REQUIRED`，不是補猜。

### 19.2 Simulation packet
每次模擬固定建立：
`SIM_ID / USER_OR_CUSTOMER_UTTERANCE / NORMALIZED_FACT_QUESTION / REQUESTED_OUTPUT_SHAPE / REQUIRED_DIMENSIONS / KNOWN_SCOPE / TARGET_DATASET_OR_VIEW / EXPECTED_FACT_IDS / AUTHORITY_EXPECTATION / SCOPE_EXPECTATION / ALLOWED_DERIVATION / MUST_INCLUDE / MUST_NOT_INCLUDE / EXPECTED_GAP_BEHAVIOR / ACTUAL_RETRIEVAL / ACTUAL_FACT_IDS / ACTUAL_OUTPUT_FIELDS / PASS_FAIL / FAILURE_LOCUS`。


### 19.3 Query-ready requires usage-ready
一個 dataset/view 只有同時通過以下才可 `QUERY_READY=YES`：
1. exact fact correctness；
2. synonym / seller slang / customer natural wording routing；
3. correct scope/classification；
4. authority/version gate；
5. correct row selection；
6. deterministic derived value；
7. requested-output-shape；
8. negative selection：不相關、雖真但本題不該輸出的 facts 不得被塞入；
9. gap behavior：缺資料時 fail-closed；
10. repeated query stability。

### 19.4 High-risk fact domains
以下 domain 的錯誤輸出可直接傷害成交/信任/廣告效益，列 `HIGH_IMPACT_LIVE_FACT`：
`PRICE / MARKET_POSITION / TRANSACTION_PRICE / TAX / FINANCE / LEGAL_REGISTRATION / WARRANTY / SAFETY / ACCIDENT_FLOOD / INSTANCE_EQUIPMENT / MODEL_YEAR_MARKET_TRIM / OWNERSHIP_COST / DELIVERY_CONDITION`。
這些 domain 若 simulation 出現 wrong fact / wrong scope / unverified leakage，該 dataset/view 立即 `LIVE_USE_BLOCKED`，直到修正並重測。

### 19.5 Scheduled sampling
背景研究排程每輪至少對「本輪新增/修改的 dataset/view 或目前最高風險 open domain」跑 1 個 live-style retrieval simulation；重大 schema/query-planner/alias/view 變更則跑完整 regression set。不得為了湊測試數量每輪重跑同一低資訊案例。

正式 closure：`FACT_VERIFIED + QUERY_READY + LIVE_QUERY_SCENARIO_PASS + FACT_CONSUMER_PASS`。

## 20. OPERATIONAL_DATASET_PORTFOLIO｜學習內容要變成可直接調用的資料集／查詢 view

### 20.1 Root finding
2026-08-19 controlled retrieval audit 發現：主 `VEHICLE_KNOWLEDGE_BASE` 雖已宣告 foundational coverage，但對目前高頻車款 `A250 / Macan / CT200h / Altis / Mustang` 尚無可直接命中的正式 instance/model fact rows；相關資訊主要散落在廣告圖、舊文案或案例檔。這些來源依法不得自動升格為 fact authority。

因此新增 root：`DECLARED_LEARNING_SCOPE_WITHOUT_QUERY_READY_DATA_PRODUCTS`。

### 20.2 Dataset portfolio，不再只用 topic list
Library 必須維護 `OPERATIONAL_DATASET_PORTFOLIO`，每個高頻 domain 是一個實際 dataset/view，而不是只在 prompt 寫「要研究」。至少分兩類：

A. `CURRENT_INVENTORY_FACT_LEDGER`
- 每台目前在庫／主打／待售／近期詢問車一個 `VEHICLE_INSTANCE_ID`；
- 建議最低欄位：`MAKE / MODEL / GENERATION / MODEL_YEAR / MARKET / TRIM / POWERTRAIN / DRIVETRAIN / ASK_PRICE / MILEAGE / INSTANCE_EQUIPMENT / CONDITION / ACCIDENT_FLOOD_STATE / SERVICE_REPAIR_STATE / WARRANTY / INSPECTION_TESTDRIVE_STATE / SOURCE_EVIDENCE / LAST_UPDATED / AUTHORITY_STATE`；
- 使用者直接明確提供、現場實測、行照/車籍/維修單/原始實車證據可依 authority 類型入 instance fact；生成廣告與舊文案仍不可作 fact authority。
- 在 Library 的 **fact/input interface**，`CURRENT_TASK_CONTRACT / 防火牆` 只傳入目前任務允許使用的 `AUTHORIZED_SOURCE_REFS / TASK_SCOPE / USER_CURRENTNESS_CLAIM(if explicit)`；它決定**可進入的輸入**，不自行驗證 fact truth。GLOBAL task contract 即使另含 bounded `EFFECT_AUTHORIZATION`，也只代表 action permission，不能升格成 fact authority。`TASK_AUTHORIZED != VERIFIED_CURRENT_FACT`。
- `CURRENT_INVENTORY_SOURCE_BINDING`：Library 對 task-authorized source 或 current ledger 解析 `SOURCE_ID / SOURCE_ROLE / EFFECTIVE_AT_OR_LAST_UPDATED / VEHICLE_INSTANCE_KEYS / MUTABLE_FIELDS / AUTHORITY_STATE`，再決定 current row／conflict／gap。
- source 不要求同一則訊息重新提供；只要仍存在目前 task contract 的 current-authorized state，可在該任務內使用。任務結束後 task-local source state 不自動跨話題延續；若要跨話題作 current fact，必須進 WRITE_PLANE reconcile/replace current ledger。
- 若 `ASK_PRICE / MILEAGE / INVENTORY_STATE / CONDITION / WARRANTY` 等 mutable 欄位在候選來源間衝突，固定 `MATCH_CURRENT_PRIMARY_KEY → RESOLVE_AUTHORIZED_CURRENT_SOURCE → REPLACE_OR_DECLARE_CONFLICT`；無法唯一解析時回 `CURRENT_INVENTORY_SOURCE_UNRESOLVED`，不得提供基於該欄位的排序。
- `SEARCH_RESULT_SCREENSHOT / OLD_AD / OLD_COPY / OLD_CAROUSEL_SNAPSHOT` 即使包含完整表格，也只能作 conflict clue；`TABLE_LOOKS_COMPLETE != CURRENT_AUTHORITY`。

B. `FOUNDATIONAL_BUSINESS_DATASETS`
優先不是百科，而是會直接影響成交、報價、客人信任與廣告內容的高頻資料：
1. 車種／用途／登記／節稅方案；
2. 牌照稅／公路養管費／年度持有成本；
3. 驗車／過戶／牌照行政；
4. 強制險／常見車險基本規則與適用條件；
5. 車貸：年式限制、期數、利率/費用口徑、月付計算所需欄位；
6. 保固／第三方認證／試車／交付條件；
7. 事故／泡水／重大安全揭露；
8. 年式／世代／facelift／台灣總代理 vs 外匯／版本／動力／驅動／標選配；
9. 常見維修風險與持有成本（需依車型/世代/引擎 scope）；
10. 價格／里程／在庫狀態等 current mutable facts。

C. `MODEL_MARKET_PROFILE_DATASETS`｜不依賴目前車源表也可背景研究
- 目的：回答「某車型／世代／版本在什麼年份、里程、價格帶、車身型式、動力／驅動、供給密度與替代方案條件下，相對更有市場競爭力」；這是 model/market-level evidence，不要求使用者目前持有該車。
- 最低維度依問題需要包含：`MAKE / MODEL / GENERATION / MODEL_YEAR_BUCKET / MARKET / TRIM_OR_BUCKET / BODY / POWERTRAIN / DRIVETRAIN / MILEAGE_BAND / ASKING_PRICE_BAND / UNIQUE_SUPPLY_DENSITY / LISTING_PERSISTENCE_IF_OBSERVABLE / SUBSTITUTE_PRICE_GAP / OBSERVED_AT / LAST_VERIFIED / SOURCE_POINTERS / QUALIFICATION_STATE`。
- 可做時間序列：比較不同觀測時間的 qualified unique supply、asking band、price dispersion、版本密度與 listing persistence；若觀測設計一致，可形成 `MARKET_DIRECTION_SIGNAL`。
- 不得把 listing views、刊登數或 asking price 直接稱為成交率；「相對好賣」若沒有 Sales outcome/closed evidence，只能表述為 `MARKET_COMPETITIVENESS / CONVERSION_POTENTIAL_INPUT`，不能冒充 observed conversion。
- 若之後要把 model profile 套到「目前這一台車」，才需要 current inventory packet 來綁定該 instance；`MODEL_MARKET_RESEARCH != CURRENT_INVENTORY_DEPENDENT`。

### 20.3 Impact-weighted build priority｜高優先不等於卡住其他研究
資料建置優先級固定用：
`BUSINESS_IMPACT × QUERY_FREQUENCY × CURRENT_INVENTORY_RELEVANCE × ERROR_COST × REUSABILITY × STALENESS_RISK × INFORMATION_GAIN`。

其中 `PRICE / MARKET_POSITION / TRANSACTION_PRICE / TAX / FINANCE / LEGAL_REGISTRATION / WARRANTY / SAFETY / ACCIDENT_FLOOD / INSTANCE_EQUIPMENT / MODEL_YEAR_MARKET_TRIM / OWNERSHIP_COST / DELIVERY_CONDITION` 為 high-impact，不得被低風險泛研究擠掉。

排程採 **非阻塞 frontier**：
`OPEN_FRONTIERS → DEPENDENCY_CHECK → BLOCK_ONLY_DEPENDENT_FRONTIER → SELECT_HIGHEST_VALUE_EXECUTABLE_FRONTIER → RESEARCH/BUILD → REASSESS`。
- 一個 dataset/view 尚未完成，只能 block 依賴它的輸出，不得把整個 Library 學習 queue 卡死。
- current inventory ledger 未完成時，仍可研究 model-level market profile、comparable qualification、market direction、基礎制度資料、query/retrieval failure。
- 同一 unresolved frontier 若沒有新 evidence、可執行修法或資訊增益，保留 `OPEN_GAP` 後跳到下一個高價值可執行 frontier；不得每小時重複撞同一堵牆。
- `FAIL_CLOSED_FOR_LIVE_DECISION != FAIL_CLOSED_FOR_BACKGROUND_RESEARCH`。

### 20.4 Customer-question coverage map
Library 不只追 topic coverage，還維護 `CUSTOMER_QUESTION_COVERAGE_MAP`：把真實使用者／客戶反覆問題映射到 dataset/view，例如：
- 「這台有沒有 ACC / 360 / 自動停車？」→ instance equipment view；
- 「總代理還是外匯？哪一年哪一代？」→ market/year/trim view；
- 「一年稅金多少／貨車牌省多少？」→ ownership-cost view；
- 「可以貸幾期／月付多少？」→ finance view；
- 「有沒有事故、泡水、保固、可不可以驗車試車？」→ condition/trust view；
- 「這公里數會不會有問題／整理大概多少？」→ maintenance-risk view。

Coverage 只有在對應 dataset/view `QUERY_READY + LIVE_CUSTOMER_READY` 才算 operational coverage；只有研究筆記或廣告文字仍是 `DECLARED_OR_HISTORICAL_ONLY`。

### 20.5 No fake completeness
`TOPIC_COVERED != DATASET_MATERIALIZED != QUERY_READY != LIVE_CUSTOMER_READY`。
任何一層不得冒充下一層。

目前 controlled audit：
- `TW_USED_CAR_ANNUAL_TAX_COST`：`NOT_READY`；
- current-inventory query-ready fact ledger：`MISSING / BUILD_REQUIRED`；
- 因此 Library 整體 `CONTENT_COMPLETENESS=PARTIAL` 維持，不得宣稱已可全面 live customer use。

## 20.6 MARKET_INTELLIGENCE_QUALIFICATION｜搜尋結果不是行情；Library 只負責市場/交易 evidence
市場事實與 closed-transaction evidence 屬 Library 的 fact/evidence owner scope；廣告 funnel、詢問、到店、成交 conversion outcome 屬 Sales outcome scope。這一節只把既有 `MARKET/COST` 的 evidence qualification 補完整，不新增獨立 owner，也不讓 Library 取代 Sales 做成交決策。

### 20.6.1 Candidate first, authority later
外部搜尋、8891/平台列表、車商網站、社群刊登首先只能形成 `MARKET_LISTING_CANDIDATE`。正式流程：
`PUBLIC_SEARCH → LISTING_CANDIDATES → ENTITY/SCOPE_NORMALIZATION → PHYSICAL_VEHICLE_DEDUP → COMPARABLE_QUALIFICATION → BAIT/FINANCE/OUTLIER_SCREEN → ASKING_MARKET_VIEW → [TRANSACTION_VIEW ONLY IF CLOSED-EVIDENCE]`

`SEARCH_RESULT != MARKET_FACT`。任何未完成 qualification 的單筆/少數 listing 不得直接支撐「市場行情合理/偏高/偏低」。

### 20.6.2 Comparable qualification
每筆候選至少建立：
`LISTING_ID / SOURCE / OBSERVED_AT / SELLER / LOCATION / MAKE / MODEL / GENERATION / MODEL_YEAR / MARKET_ORIGIN(if known) / TRIM / BODY / POWERTRAIN / DRIVETRAIN / MILEAGE / ASK_PRICE / CONDITION_DISCLOSURE / ACCIDENT_FLOOD_DISCLOSURE / FINANCE_OR_TEASER_FLAGS / LISTING_STATUS / VEHICLE_FINGERPRINT / QUALIFICATION_STATE / EXCLUSION_REASON`。

進入 comparable set 前至少檢查：
1. `ENTITY_MATCH` 不只名稱相同；generation/year/market/trim/body/powertrain/drivetrain 中會改變價格的 dimension 必須 match 或明確分 bucket。
2. `INSTANCE_CONDITION`：重大事故/泡水/營業用途/極端改裝/明顯車況差異若未知，不能假裝完全可比；依影響 downgrade 或 exclude。
3. `PRICE_PRESENTATION`：0 元交車、月付導向、全額貸、需搭融資、明顯 teaser/假價/異常低價不得進一般 cash-retail asking benchmark。
4. `PHYSICAL_VEHICLE_DEDUP`：同一實車跨平台、跨業務、同照片/里程/價格/車色/地區高度一致時，合併為一個 evidence identity；`LISTING_COUNT != UNIQUE_VEHICLE_COUNT`。
5. `OUTLIER_WITH_REASON`：極端價格不能只因高/低就刪；先找版本、車況、事故、里程、交易條件差異。找不到原因才標 unexplained outlier，不得拿來定中心行情。

### 20.6.3 Asking / transaction strict separation + Sales outcome boundary
- `ASKING_MARKET_VIEW`：只反映 qualified unique listings 的公開開價分布、供給量、版本密度與位置；不得稱成交價。
- `TRANSACTION_MARKET_VIEW`：只有可驗證 closed-transaction evidence（例如可追溯成交/過戶/拍賣成交資料）才可建立；listing 消失/下架/換帳號不等於 SOLD。
- `SALES_OUTCOME / CONVERSION_RATE` 不由 Library 從 listing 推導。Library 不建立或校準曝光→詢問→到店→成交 funnel；該 outcome evidence 由 Sales 的 current campaign/歷史 outcome 資料負責。
- 若任務要求「哪台比較有機會成交」，Library 只提供 verified current inventory + qualified market/transaction inputs 與資料限制；Sales 再結合自己合法可用的 outcome evidence做 `CONVERSION_POTENTIAL_ESTIMATE` 或 observed conversion analysis。
- `ASKING_LISTINGS != SALES_CONVERSION_EVIDENCE`。

### 20.6.4 Market output packet
對 Sales 的市場比較資料至少回：
`DATASET_ID / SUBJECT_INSTANCE / COMPARABLE_SCOPE / QUALIFIED_UNIQUE_COUNT / EXCLUDED_COUNT_BY_REASON / ASKING_BAND_OR_GAP / SUBJECT_POSITION_OR_GAP / TRANSACTION_EVIDENCE_STATE / MAJOR_SCOPE_LIMITS / LAST_VERIFIED / SOURCE_POINTERS`。

只要 `CURRENT_INVENTORY_SOURCE_UNRESOLVED`、`COMPARABLE_SCOPE_UNRESOLVED`、qualified unique sample 不足以支持結論、或來源只剩 unqualified listing，正確結果是 `MARKET_EVIDENCE_GAP`，不是從常識補一個排名。

### 20.6.5 Model market-condition learning｜沒有現車也能研究
Library 可在背景／排程中針對一個車型或 scope bucket 建立市場條件 profile，不需要 current inventory source。研究問題可包括：
- 哪些年份／世代／trim/body/powertrain/drivetrain 形成不同價格 bucket；
- 哪些里程帶與 asking-price percentile 對應較低／較高市場摩擦；
- qualified unique supply density、價格分散度、替代車價差與同預算競品；
- 在一致觀測方法下，供給量、asking band、listing persistence 的時間變化；
- 哪些「看似便宜」其實是融資 teaser、事故／營業用途、版本差異或重複實車。

固定輸出角色：
`MARKET_STRUCTURE_FACTS → MARKET_COMPETITIVENESS_PROFILE → SALES_CONSUMABLE_INPUT`。
Library 不直接宣稱「一定更好賣」；若要判定成交／廣告成效，交由 Sales 結合 real outcome evidence。

### 20.6.6 Required adversarial regressions
至少保留以下回歸：
- 舊車源表截圖在 semantic search 排第一，但 verified current inventory source 不同 → 舊表必須 BLOCK；
- A250 名稱相同但 W176/W177、market/4MATIC/trim 不同 → 不得放同一 comparable bucket；
- 同一 Mustang 實車由兩個業務/平台重刊 → unique vehicle count 只能算 1；
- listing 下架但無 closed evidence → 不得標 SOLD；
- 0 元交車/月付/全貸 teaser → 不得進一般現金零售 asking benchmark；
- 只有 asking listings → Library 只能回 asking-market evidence，不得輸出成交率；Sales 也不得把它當 observed conversion evidence。

## 21. IMMEDIATE_POST_PATCH_VALIDATION｜任何資料／調用邏輯修改都必須同回合測

### 21.1 Root finding
2026-08-19 再確認根缺陷：`PATCH_WITHOUT_IMMEDIATE_VALIDATION`。僅完成 WRITE/READBACK、把測試留到下一排程，不能證明新邏輯可用；這會讓錯誤 schema/query alias/authority/filter/response-selection 在下一個真實客戶問題前保持未發現。

### 21.2 Atomic patch-test closure
任何 Library dataset/view/registry/query alias/authority rule/classification/persistence/query-ready contract 的修改，固定同一 execution cycle：
`PRE_PATCH_SNAPSHOT -> WRITE -> READBACK_DIFF -> SAME_CYCLE_STATIC_TEST -> SAME_CYCLE_RETRIEVAL_TEST -> NEGATIVE/ADVERSARIAL_TEST -> RESULT_CLASSIFICATION -> REPAIR_OR_REVERT -> RETEST -> STATUS_COMMIT`。

若未完成 behavior test：只可 `PATCH_INCOMPLETE / UNTESTED`；不得標 `PATCHED / QUERY_READY / LIVE_CUSTOMER_READY / CLOSED / LEARNED`。

### 21.3 Minimum behavioral test
至少包含：
- 1 個 exact positive 或 expected-gap case；
- 1 個 synonym/nearby wording case；
- 1 個 negative/adversarial case；
- high-impact domain 額外驗 `FACT_TRUTH + SCOPE + AUTHORITY + NO_GUESS + REQUESTED_OUTPUT_SHAPE`；若是 inventory/market 題，再驗 `CURRENT_TASK_INPUT_BOUNDARY + CURRENT_SOURCE_BINDING + COMPARABLE_QUALIFICATION + DEDUP + ASKING_TRANSACTION_SEPARATION + NO_SALES_OUTCOME_OWNERSHIP`。

Dataset 尚 NOT_READY 時，正確 local result 可以是 fail-closed；不得為讓測試通過而 synthetic 補值。
Library same-cycle test 只產生 `LOCAL_RETRIEVAL_EVIDENCE`；若要宣稱跨域修正完成、GLOBAL closure 或正式 behavior validation，仍須服從上游 validation contract，Library 不得自證整體 closure。
`PATCH_TEXT_ONLY_FALSE_COMPLETION` = FAIL。

## 22. EXTERNAL_PRACTICE_QUERY_CORPUS｜真實用詞只訓練調用，不升格成 fact

### 22.1 Two-lane evidence model
Library 背景研究除 VERIFIED fact build 外，持續蒐集公開台灣中古車/車主實務的 `AUTOMOTIVE_QUERY_LANGUAGE_CORPUS`。來源可含 Threads、Facebook 公開內容、Dcard、Mobile01、公開車商案例與公開銷售教學；其 authority 只限 `QUERY_LANGUAGE / AMBIGUITY / BUSINESS_ALIAS / REQUIRED_DIMENSION / ANSWER_SHAPE / QUESTION_CONTEXT`。

正式隔離：`PRACTICE_EVIDENCE != FACT_EVIDENCE`。論壇、社群、車商貼文中的數字、配備、法規敘述不得直接寫入 VERIFIED fact。缺 primary/authoritative evidence chain 時只能 `CANDIDATE / CONFLICT_SIGNAL / QUERY_ALIAS_EVIDENCE`。

### 22.2 Query-language case schema
每個可重用問法樣本正規化為：
`CASE_ID / SOURCE_ROLE / RAW_OR_PARAPHRASED_UTTERANCE / NORMALIZED_INTENT / AMBIGUOUS_TERMS / REQUIRED_DIMENSIONS / POSSIBLE_SCOPE_SPLITS / TARGET_DATASET_VIEW / EXPECTED_GAP_BEHAVIOR / QUERY_ALIASES / RISK_IF_MISROUTED / CONFIDENCE`。

高優先 stress corpus 包含：
- 公司牌 / 公司名義 / 貨車牌 / 客貨兩用；
- 燃料稅 / 燃料費 / 公路養管費；
- 年式 / 出廠 / 領牌；
- 定速 / ACC / 跟車；
- 360 / 環景 / 倒車顯影；
- 自動停車；
- 總代理 / 外匯；
- 保固 / 認證；
- 月付 / 利率 / 可貸期數；
- 驗車 / 過戶 / 牌照與持有成本。

FACT_QUERY_CONSUMER 必須判斷哪些詞只是 synonym、哪些會改變 classification 或 required dimensions。`SEMANTIC_SIMILARITY != SAME_FACT_SCOPE`。

### 22.3 Practical retrieval validation
新 alias/query-language cluster 不因蒐集完成就可 live。至少測：exact wording、seller slang、reordered wording、ambiguous wording、classification-changing near-match、missing dimension、quarantine-first、repeat equivalent query。

若 query-language corpus 能理解問題但 target fact dataset NOT_READY，正確結果仍是 `SAFE_GAP / BUILD_REQUIRED`；不得用 practical corpus 自己補 value。

### 22.4 Same-cycle closure
本 section/schema/alias 修改必須同 cycle 跑：`READBACK -> EXACT_OR_EXPECTED_GAP -> SYNONYM_NEARBY -> ADVERSARIAL_SCOPE -> NO_FACT_LEAK -> STATUS`。未測=`PATCH_INCOMPLETE/UNTESTED`。

## 23. INTERFACE_PACKET_INTEGRITY｜Library 對任何 fact consumer 的無失真契約

### 23.1 Library packet is a typed read packet
Library 對 `SALES/HUMAN` 或其他合法 fact consumer 的輸出不得只是段落文字或搜尋 snippet。正式 result packet 至少：
`LIBRARY_PACKET_ID / REQUEST_PACKET_ID / FACT_ID_OR_GAP / DATASET_ID / DIMENSION_KEYS / AUTHORITY_STATE / SCOPE / VERSION / FACT_VALUE_OR_GAP / CONFLICTS / SOURCE_POINTER / DERIVATION / LAST_VERIFIED / QUERY_ALIAS_USED / CREATED_AT`。

### 23.2 Hard-field preservation
`FACT_ID_OR_GAP / DIMENSION_KEYS / AUTHORITY_STATE / SCOPE / VERSION / CONFLICTS` 為 hard fields。Archive/write/readback/query/view/materialized-view 任一轉換都不得刪除、默認或改寫。
`VALUE WITHOUT SCOPE/AUTHORITY/VERSION != USABLE FACT`。

### 23.3 Archive version guard
Consumer 必須指定或收到 current packet/version。若同 FACT_ID 有舊版與新版：current version 未確認前不得由 semantic ranking 選舊版。正式 failure：`STALE_ARCHIVE_PACKET_CONSUMED / VERSION_CONTEXT_LOST / SEARCH_RANK_OVERRULED_VERSION`。

### 23.4 One-to-many / many-to-one mapping guard
一個自然問法可對應多個可能 fact rows 時，Library 不替 consumer 隨機選擇；回 `MULTIPLE_MATCHES + REQUIRED_DISAMBIGUATION_DIMENSIONS`。
多個 query aliases 可指向同 dataset/view，但 alias 只改 routing，不得折疊會改 scope 的 classification dimensions。

### 23.5 Library -> consumer roundtrip test
每次 dataset/view/schema/archive 變更，同 cycle 至少：
1. exact FACT_ID packet write/readback；
2. current version selected over stale version；
3. missing scope/authority -> BLOCK；
4. conflict/quarantine survives serialization；
5. one-to-many returns disambiguation, not guessed row；
6. alias routing preserves dimension differences；
7. consumer echo equals source hard fields。

只有 `PACKET_WRITE_PASS + PACKET_READBACK_PASS + VERSION_PASS + AUTHORITY_SCOPE_PASS + SELECTION_PASS + CONSUMER_ECHO_PASS` 才可供 live fact retrieval。

## 24. UNIQUE_FACT_AUTHORITY_IDENTITY｜現行 fact 規則唯一解

### 24.1 Authority identity
本 KB 唯一 live authority identity：
`CANONICAL_PATH = /VEHICLE_KNOWLEDGE_BASE.md`
`AUTHORITY_RESOLUTION = ROOT_PATH_CURRENT_OBJECT_ONLY`

### 24.2 Supersession
Dataset/fact/rule 修訂採 `CURRENT_SUPERSEDES_PRIOR`。同 FACT_ID/DATASET_ID/規則一旦 current version promotion，舊版即 `SUPERSEDED_NON_EXECUTABLE`；不得與 current 共同 ranking、merge、投票或碰撞。歷史值只能用於 audit/provenance，不能 live answer。

### 24.3 Current resolver
Current fact/KB bootstrap 固定：`AUTHORITY_ID -> CURRENT_METADATA/VERSION -> EXACT DATASET/FACT -> AUTHORITY_STATE -> SCOPE -> VERSION -> ANSWER`。semantic search 只能找 query-language/candidate location；不得決定現行 fact version。若拿到舊 file_id、舊 version、Trash/Archive 或 search stale hit：`STALE_FACT_AUTHORITY_BLOCK`。

### 24.4 Atomic persistence
本 KB 每次正式 mutation 固定採 `FULL_OBJECT_REPLACEMENT_TRANSACTION`：snapshot current root -> build replacement -> delete current root object -> create fresh same-path version1 -> list/readback/test。任何 Trash/Archive/舊 file_id 都不能成為 live fact authority。

## 25. FACT_UPDATE_REPLACEMENT_CONTRACT｜同一事實主鍵永遠只有一個現行值

### 25.1 Fact primary key
每筆可 live 的 fact 必須有可決定唯一性的 `FACT_PRIMARY_KEY = DATASET_ID + DIMENSION_KEYS + ENTITY_SCOPE`（必要時含 MARKET/MODEL_YEAR/TRIM/VEHICLE_INSTANCE/EFFECTIVE_JURISDICTION）。同一 primary key 在 current query-ready dataset 中最多只能有一筆 `AUTHORITY_STATE=VERIFIED/CURRENT`。

### 25.2 Update = replace row
同一 `FACT_PRIMARY_KEY` 的值、scope、classification、source 或 effective rule 被修正時：
`MATCH_CURRENT_ROW -> VALIDATE_NEW_EVIDENCE -> REPLACE_ROW -> REMOVE_OLD_ROW_FROM_CURRENT_DATASET -> INVALIDATE_DEPENDENT_VIEWS -> REBUILD_VIEWS -> READBACK -> QUERY_TEST`。
禁止把舊值與新值都留在 current dataset 再靠版本、ranking 或 consumer 猜哪個比較新。舊值若需要歷史追溯，移至 Archive/history 並標 `SUPERSEDED_NON_EXECUTABLE`。

### 25.3 Mutable/current facts
PRICE / MILEAGE / INVENTORY_STATE / WARRANTY_REMAINING / CURRENT_REGULATION / CURRENT_FEE / CURRENT_FINANCE_PROGRAM 等 mutable facts 更新後，current view 只保留最新 effective 值。過去值不得參與一般 live answer。

### 25.4 Historical as-of exception
只有使用者明確問「某年某日當時規定/價格/狀態」才啟用 `HISTORICAL_AS_OF_MODE`，以 `AS_OF_DATE` 查 Archive/history；此模式與 current live retrieval 隔離，不能混合輸出。

### 25.5 Duplicate-key hard gate
每次 dataset/view persistence 前掃描：
- 同 `FACT_PRIMARY_KEY` current verified row count = 1；
- 同 DATASET_ID 不得並存兩套 active schema version；
- 同 alias 不得直接綁定多個會改變 scope 的 fact values；
- dependent view 不得同時引用 superseded + current source fact。
違反 -> `FACT_CURRENT_STACKING_DETECTED / DUPLICATE_CURRENT_FACT_KEY`，不得 QUERY_READY。

### 25.6 Three-case regression
F1 同 FACT_ID/primary key 新值 -> 舊 row 必須退出 current；
F2 同制度法規新 effective rule -> current 只回新規則，舊規則僅 historical-as-of；
F3 新增不同車款/不同 year-market-trim row -> 可 coexist，因 primary key 不同；不得誤當「疊加」。


## 26. DATASET_STORE_SEPARATION｜規則與資料分離
Library Canonical 只保存 schema、authority、verification、retrieval、currentness、consumer contract 與 dataset lifecycle 規則；具體車型/實車 fact rows 不再長期堆在 Canonical。

固定：
`/VEHICLE_KNOWLEDGE_BASE.md = RULE/SCHEMA AUTHORITY`
`/LibraryData/* = LIBRARY-OWNED DATASET/FACT STORE`

目前已遷移的 query-ready model datasets：
- `MUSTANG_MODEL_YEAR_GENERATION_BASELINE`
- `A250_CA_MY2019_DRIVER_ASSIST_BASELINE`

Current data store：`/LibraryData/VEHICLE_FACT_DATASETS_CURRENT.md`。

- Dataset file 不取得新的 owner/Canonical authority；其 rows 必須符合本 Canonical 的 primary-key、evidence、currentness、query-ready 與 consumer projection 規則。
- 新車型/新 fact 以 dataset/row 方式新增或 replace，不得為每個車款擴寫 Canonical professional rules。
- Canonical update 與 dataset update 分開 version；schema incompatible 時 dataset/view 先標 stale/hold，再 migrate/test。
- live retrieval 先查 dataset registry/store，再依本 Canonical authority filter 取值；不得因資料檔存在就跳過 VERIFIED/currentness/scope gate。

## 28. CONSUMER_ORIENTED_QUERY_VIEWS｜同一 truth core，依 consumer 建可重建讀取 view

### 28.1 Root design
Library 不建立「一個巨大 packet 給所有邏輯」，也不把 projection 升格成新的 data-product authority。projection 只是方便不同邏輯快速調取的 read-only query view / DTO。固定：
`WRITE_PLANE → VERIFIED_FACT_CORE → CONSUMER_PROJECTION_REGISTRY → {SALES_HUMAN_FACT_PROJECTION | SALES_MARKET_DECISION_PROJECTION | VISUAL_LITERAL_FACT_PROJECTION | EXECUTION_INSTANCE_TRUTH_PROJECTION | GLOBAL_FACT_STATUS_PROJECTION}`。

核心原則：
- `VERIFIED_FACT_CORE` 是唯一 truth authority；projection 只是 read model / materialized view / query DTO，不取得新 authority，也不承載 consumer 的業務判斷。
- `PROJECTION != FACT_AUTHORITY`、`PROJECTION_CAN_BE_REBUILT`、`PROJECTION_DIRECT_WRITE = FORBIDDEN`。
- 每個 consumer 只拿它真正需要的欄位；extra field 不因存在就自動跨域。
- projection 缺欄只 block 依賴該欄位的 consumer action，不把整個 Library 或其他 consumer 一起 fail-close。

### 28.2 Projection registry
每個 projection 必須登錄：
`PROJECTION_ID / CONSUMER_ID / SOURCE_DATASET_IDS / SCHEMA_MAJOR / SCHEMA_MINOR / REQUIRED_FIELDS / OPTIONAL_FIELDS / BLOCKING_FIELDS / DENYLIST / CURRENTNESS_REQUIREMENT / DATA_SENSITIVITY_POLICY / COMPATIBILITY_MODE / CONTRACT_TEST_SET / OWNER=LIBRARY`。

### 28.3 Consumer projections
**A. `SALES_HUMAN_FACT_PROJECTION`**
- 供 direct answer、比較、揭露、tradeoff 前的最小 truth 使用。
- 至少保留 `FACT_ID / VALUE_OR_GAP / SCOPE / AUTHORITY_STATE / ASSERTION_CLASS / CURRENTNESS_STATE / CONFLICTS / MISSING_DIMENSIONS / DATA_SENSITIVITY_CLASS / LINEAGE_ROOT_ID`。
- Library 不替 Sales 判斷 relevance、價值、客戶心理或 next step。

**B. `SALES_MARKET_DECISION_PROJECTION`**
- 供市場定位、comparable、asking/transaction evidence、current inventory decision input。
- 既有 market packet 之外固定帶 `OBSERVATION_WINDOW / CURRENTNESS_STATE / QUALIFICATION_STATE / LINEAGE_ROOT_ID / MAJOR_SCOPE_LIMITS`。
- 不輸出 Sales conversion 結論。

**C. `VISUAL_LITERAL_FACT_PROJECTION`**
- 只在 current task 已要求／授權使用 truth-sensitive literal 時使用，例如年份、里程、價格、版本、已驗證配備。
- 只提供 `FACT_ID / CANONICAL_VALUE / UNIT / SCOPE / ASSERTION_CLASS / CURRENTNESS_STATE / EXACT_LITERAL_CANDIDATE / LINEAGE_ROOT_ID`。
- `EXACT_LITERAL_CANDIDATE != RENDER_AUTHORITY`；是否把文字放進圖片仍由 current task + Sales/Visual 既有 `VISUAL_TEXT_AUTHORITY / AUTHORIZED_EMBEDDED_LITERALS` 決定。
- Visual 不得以此 projection 自行探索行情、客群或新增賣點。

**D. `EXECUTION_INSTANCE_TRUTH_PROJECTION`**
- 只供 execution 做 source/instance binding 與 truth-sensitive protected state：`VEHICLE_INSTANCE_ID / IDENTITY_FACT_IDS / INSTANCE_EQUIPMENT_FACT_IDS / CONDITION_FACT_IDS / MUTABLE_INSTANCE_FACTS / SOURCE_BINDING / CURRENTNESS_STATE / CONFLICTS / LINEAGE_ROOT_ID`。
- 不含 Visual perceptual verdict、Sales positioning、route capability 或工具策略。

**E. `GLOBAL_FACT_STATUS_PROJECTION`**
- GLOBAL 預設只消費 metadata：`LIBRARY_PACKET_ID / PROJECTION_ID / PROJECTION_SCHEMA_VERSION / AUTHORITY_STATE / CURRENTNESS_STATE / GAP_STATE / CONFLICT_STATE / LINEAGE_STATE / BLOCKING_DIMENSIONS / CONSUMER_CONTRACT_STATE`。
- GLOBAL 不需要為治理而取得整包 fact values；只有 closure/audit 真正需要時才讀最小 supporting facts。

## 29. TEMPORAL_CURRENTNESS_CONTRACT｜LAST_VERIFIED 不等於現在仍有效

對 time-sensitive / mutable / observation-series fact 固定區分：
`OBSERVED_AT / EFFECTIVE_FROM / EFFECTIVE_TO_OR_OPEN / RECORDED_AT / LAST_VERIFIED / FRESHNESS_CLASS / CURRENTNESS_STATE / AS_OF_MODE`。

定義：
- `OBSERVED_AT`：來源實際被觀察／擷取的時間。
- `EFFECTIVE_FROM/TO`：該值在真實世界適用的有效期間；若來源無法支持 effective time，不得臆測。
- `RECORDED_AT`：Library 寫入此版本的時間。
- `LAST_VERIFIED`：最後完成 authority/conflict verification 的時間，不可單獨當 valid-time。
- `CURRENTNESS_STATE = CURRENT | STALE | EXPIRED | FUTURE_EFFECTIVE | HISTORICAL | UNKNOWN_CURRENTNESS`。

每個 dataset 標 `FRESHNESS_CLASS = STATIC | SEMI_STATIC | MUTABLE | OBSERVATION_SERIES`，並自訂 `CURRENTNESS_SLO / REVERIFY_TRIGGER`；不建立所有資料共用的固定天數。

規則：
- 價格、里程、在庫、保固剩餘、金融方案、法規/費率、asking-market observation 等不得只靠 `LAST_VERIFIED` 判 current。
- `CURRENT_REQUIRED` query 只消費 `CURRENTNESS_STATE=CURRENT` 或符合 dataset currentness policy 的 row。
- historical query 才進 `AS_OF_MODE`；current projection 不混入 superseded historical value。
- market observation series 必須保留 `OBSERVED_AT/OBSERVATION_WINDOW`，不得把不同時間截面的 listing 混成同一 current market snapshot。

## 30. CONSUMER_DATA_CONTRACT_AND_SCHEMA_EVOLUTION｜consumer 可獨立演進，不用一起重寫

Library 對 projection 採 consumer-defined contract：只把 consumer 真正依賴的欄位列為 required。

Schema 規則：
- `SCHEMA_MINOR`：只允許不改既有語意的 additive optional field、metadata 補充或等價 alias；舊 consumer 應可忽略新欄位。
- `SCHEMA_MAJOR`：欄位語意改變、required field 改名/刪除、scope/currentness/authority semantics 改變時必須升 major，並提供 explicit adapter/migration 或先 HOLD consumer。
- `EXTRA_FIELD != NEW_CONSUMER_DEPENDENCY`；consumer 未宣告使用的欄位不進 contract hard gate。
- provider patch 前跑 consumer contract set；若任何 current consumer required field 失真，標 `LIBRARY_SCHEMA_COMPATIBILITY_BREAK / HOLD`。
- 不用「整份 schema 完全相等」製造 brittle contract；只保護真正會造成 consumer 行為錯誤的欄位與情境。

## 31. PROVENANCE_LINEAGE_AND_DATASET_SHAPE｜證據鏈可追、資料形狀可驗

### 31.1 Minimal lineage
沿用現有 evidence chain，補成最小 lineage：
`LINEAGE_ROOT_ID / SOURCE_EVIDENCE_IDS / SOURCE_ENTITY_OR_DOCUMENT / EXTRACTION_OR_NORMALIZATION_ACTIVITY_ID / DERIVED_FROM_FACT_IDS(if any) / DERIVATION / RESPONSIBLE_OWNER=LIBRARY / RECORDED_AT`。

- 每個 derived fact/materialized view 必須能回到 exact upstream fact IDs/source evidence。
- consumer packet 只帶 `LINEAGE_ROOT_ID` + 必要 pointer，不把完整 evidence dump 傾倒給 consumer。
- `SOURCE_POINTER_ONLY_WITHOUT_LINEAGE_FOR_DERIVED_VALUE = INCOMPLETE_PROVENANCE`。

### 31.2 Dataset shape contract
每個 query-ready dataset/view 必須有：
`DATASET_SHAPE_ID / REQUIRED_DIMENSIONS / FACT_PRIMARY_KEY / FIELD_TYPES_UNITS / ALLOWED_ENUMS / CROSS_FIELD_CONSTRAINTS / DERIVATION_RULES / CURRENTNESS_RULE / DATA_SENSITIVITY_POLICY / NULL_OR_GAP_RULE / VERSION`。

Shape validation 先於 QUERY_READY promotion；例如 year/market/trim 不可被 alias 折疊、price 必須有 currency/market、derived total 必須引用同 scope components、instance equipment 必須有 instance evidence class。

## 32. CONSUMER_DEMAND_AND_FEEDBACK_BRIDGE｜其他邏輯告訴 Library「要查什麼／缺什麼」，不能告訴 Library「真相或決策是什麼」

Library 接受最小 demand/feedback signal，用來排 build priority，不改 fact authority：
- Sales/Human：`QUESTION_PATTERN / REQUIRED_FACT_DIMENSIONS / REQUESTED_ANSWER_SHAPE / FREQUENCY_SIGNAL / DECISION_IMPACT / CURRENTNESS_REQUIREMENT`。
- Visual：`LITERAL_FACT_NEED / INSTANCE_TRUTH_NEED / MISSING_DIMENSIONS / TASK_SCOPE`；不得送 market strategy、心理狀態或構圖決策。
- Execution：`SOURCE_BINDING_OR_INSTANCE_TRUTH_GAP / REQUIRED_FACT_DIMENSIONS / BLOCKED_CONTROL_SCOPE`；不得送 route conclusion 當 truth。
- GLOBAL：`PROJECTION_MISMATCH / SCHEMA_DRIFT / CURRENTNESS_LOSS / LINEAGE_GAP / OVERFETCH_OR_FOREIGN_FIELD / CONSUMER_CONTRACT_FAIL`。

固定：
`CONSUMER_NEED_SIGNAL → NORMALIZE → MATCH_EXISTING_DATA_PRODUCT → BUILD/REVISE_PROJECTION_OR_DATASET → CONTRACT_TEST → READBACK → CONSUMER_RETEST`。
`CONSUMER_FEEDBACK != FACT_EVIDENCE`；consumer 可以指出缺口／使用失敗，不能直接改值。

## 33. CROSS_DOMAIN_LIBRARY_REGRESSION｜資料正確還不夠，必須對不同 consumer 都不失真

高影響 Library interface patch 至少覆蓋：
1. Sales/Human direct fact：只取所需欄位，scope/currentness/uncertainty 保留。
2. Sales market decision：qualified asking/transaction/current inventory 邊界不變。
3. Visual literal：verified exact literal 可被驗證，但 `VISUAL_TEXT_AUTHORITY=NONE` 時不得因 Library fact 存在就自動渲染。
4. Execution instance truth：能取得 source-bound identity/condition fact，但不得取得 Visual verdict 或 Sales strategy。
5. GLOBAL status：可判 packet/gap/conflict/currentness/schema/lineage 狀態，而不需要吸收完整 fact domain。
6. Temporal stale case：舊價格/里程/規則即使 verified 過，currentness 不符時必須 BLOCK dependent claim。
7. Schema evolution：加 optional field 不破壞舊 consumer；required semantic breaking change 必須 major/adapt/HOLD。
8. Extra-field injection：consumer 未宣告欄位必須忽略，不得擴權。
9. Lineage：derived fact/view 能回到 exact upstream evidence。
10. Consumer feedback：能觸發 Library repair priority，但不能直接改寫 fact value。

正式狀態：`FACT_CORE_VALID + PROJECTION_CONTRACT_PASS + CURRENTNESS_PASS + LINEAGE_SHAPE_PASS + CONSUMER_ROUNDTRIP_PASS` 才可把該 projection 標為 `CONSUMER_READY`。



## 34. SOURCE_SYNC_AND_CHANGE_CAPTURE｜最新資料先同步，再談查得準
Library 對會變動的來源不只做「最後驗證」，而要有明確 source-sync 狀態。成熟 change-data-capture 思路在此只抽象成最小必要機制，不要求特定 Kafka/CDC 工具。

固定：
`SOURCE_DISCOVERY/AUTHORIZATION → SOURCE_IDENTITY → CHANGE_SIGNAL_OR_SNAPSHOT → NORMALIZE → VERIFY → CURRENT_STORE_RECONCILE → DEPENDENT_VIEW_REFRESH → RETRIEVAL_READY`。

每個可變來源至少標：
`SOURCE_ID / SOURCE_TYPE / SOURCE_SCOPE / SOURCE_VERSION_OR_FINGERPRINT / OBSERVED_AT / INGESTED_AT / CHANGE_DETECTION_MODE / LAST_CHANGE_SEEN_AT / SYNC_STATE / AUTHORITY_ROLE`。

`CHANGE_DETECTION_MODE` 依來源能力使用：
- `EVENT_OR_CDC`：來源本身能提供可靠 change event/version 時，優先事件驅動。
- `VERSION_DIFF`：檔案、車源表、結構化清單有版本／hash／modified time 時做差異偵測。
- `SCHEDULED_SNAPSHOT`：外部市場/listing 沒有 change feed 時，以一致方法定期快照。
- `ON_DEMAND_REVERIFY`：使用者明確要求「最新／現在」且現有 snapshot 不滿足 currentness requirement 時，受控重驗。

規則：
- **最新車源表**：只要 current authorized/persisted source 有新版，先做 row/field diff，再 replace mutable current facts；不得把舊表與新表同時當 current。
- **即時市場行情**：沒有真正 change feed 時只能稱 `NEAR_CURRENT_MARKET_SNAPSHOT` 或帶明確 `OBSERVATION_WINDOW`；不得把排程快照冒充 streaming realtime。
- source sync 成功只代表「來源已更新」，仍需 evidence/authority qualification 才能進 VERIFIED/CURRENT。`SOURCE_FRESH != FACT_VERIFIED`。

## 35. VEHICLE_ENTITY_RELATION_AND_LINEAGE_GRAPH｜先對準是哪一台／哪一代，再查資料
Library 維持結構化 entity graph／關係索引，用來提升跨來源 entity resolution 與改款前後資料連接準確度；它不是 Sales customer graph。

核心節點：
`MAKE / MODEL / GENERATION / FACELIFT_PHASE / MODEL_YEAR / MARKET / BODY / TRIM / PACKAGE / POWERTRAIN / DRIVETRAIN / VEHICLE_INSTANCE`。

核心關係：
`PREDECESSOR_OF / SUCCESSOR_OF / FACELIFT_OF / MODEL_YEAR_OF / MARKET_VARIANT_OF / TRIM_OF / PACKAGE_APPLIES_TO / POWERTRAIN_AVAILABLE_IN / INSTANCE_OF / SUBSTITUTE_SCOPE_LINK`。

規則：
- 同名車款不代表同 entity；generation/facelift/model-year/market/trim 等會改變事實時必須分開。
- alias、俗稱、平台錯標只作 entity-resolution candidate；不得覆蓋 verified classification。
- 改款前後比較固定先輸出 `DELTA_FACTS + MARKET_OBSERVATION_DELTA + EVIDENCE_LIMITS`，不直接輸出「所以新款客群一定是 X」。
- 多來源疑似同一實車可做 rule/fingerprint matching；無法唯一對上時保留 `ENTITY_MATCH_UNRESOLVED`，不得為了市場統計強行合併。

## 36. EVIDENCE_CLASSES_FOR_BUSINESS_USE｜可以收客群與改裝資料，但只作 evidence
Library 除 hard fact 外允許維護下列 evidence class，目的是讓其他邏輯不必每次從網路重新拼湊：

1. `VERIFIED_HARD_FACT`：規格、版本、配備、法規、價格/里程/在庫等 scope-matched fact。
2. `CURRENT_MARKET_OBSERVATION`：qualified asking listings、供給密度、價格帶、版本密度、listing persistence、替代車價差；必帶 observation window。
3. `CLOSED_TRANSACTION_EVIDENCE`：可追溯成交/拍賣/過戶等 closed evidence；與 asking 嚴格分開。
4. `MARKET_AUDIENCE_EVIDENCE`：有來源的受眾／需求／詢問結構 evidence，例如不同世代或改款前後常見關注點、用途、預算／替代方案、平台/社群聚集差異。
5. `MODIFICATION_ECOSYSTEM_EVIDENCE`：常見改裝方向、零件相容性、常見品牌/規格、費用區間、合法性/安全限制、社群趨勢與二手市場接受度 evidence。
6. `PRACTICE_AND_QUERY_LANGUAGE_EVIDENCE`：車主／業務常用語、常見問題、別名與 ambiguity，只服務 query routing。

`MARKET_AUDIENCE_EVIDENCE` 最小欄位：
`EVIDENCE_ID / VEHICLE_SCOPE / OBSERVATION_PERIOD / SOURCE_ROLE / OBSERVED_AUDIENCE_OR_QUESTION_PATTERN / USE_CASE_OR_CONCERN / COMPARISON_SET(if observed) / SAMPLE_OR_SIGNAL_STRENGTH / TRANSFER_LIMITS / PROVENANCE`。

`MODIFICATION_ECOSYSTEM_EVIDENCE` 最小欄位：
`EVIDENCE_ID / VEHICLE_SCOPE / MOD_CATEGORY / OBSERVED_DIRECTION / COMPATIBILITY_FACTS / COST_RANGE_IF_SUPPORTED / LEGAL_SAFETY_CONSTRAINTS / MARKET_ACCEPTANCE_SIGNAL_IF_OBSERVED / OBSERVATION_PERIOD / SOURCE_ROLE / TRANSFER_LIMITS / PROVENANCE`。

硬邊界：
- `AUDIENCE_EVIDENCE != TARGET_BUYER_DECISION`；target buyer／怎麼賣仍由 Sales。
- `MOD_TREND != RECOMMENDED_MODIFICATION`；要不要改、怎麼改、是否適合某客戶由對應專業/使用者決定。
- 社群聲量、詢問多、按讚多不等於成交率；沒有 Sales outcome link 不得升成 conversion claim。
- 法律、安全、相容性等 truth-sensitive mod 欄位必須走相應 authority；論壇熱門不能覆蓋硬事實。

## 37. QUERY_MODES_AND_RETRIEVAL_PIPELINE｜按問題調資料，不按 Library 自己想講什麼
Library 對現行各邏輯提供少量穩定 query mode；query mode 只決定資料怎麼取，不決定 downstream action：
- `EXACT_FACT_QUERY`：單一／少量硬事實。
- `CURRENT_INVENTORY_QUERY`：最新在庫、價格、里程、車況、保固等 current mutable facts。
- `CURRENT_MARKET_SNAPSHOT_QUERY`：qualified asking/transaction evidence + observation window。
- `MODEL_LINEAGE_DELTA_QUERY`：世代／改款／MY／市場版本前後差異。
- `MARKET_AUDIENCE_EVIDENCE_QUERY`：車款／世代／改款前後受眾與關注點 evidence。
- `MODIFICATION_ECOSYSTEM_QUERY`：改裝方向／相容性／法規安全／市場接受度 evidence。
- `INSTANCE_SOURCE_TRUTH_QUERY`：Visual/Execution 需要的實車/source-bound truth。

調取策略分兩條：
**A. Structured exact lane**
`QUERY → ENTITY/SCOPE FILTER → DATASET/PRIMARY_KEY → CURRENTNESS/AUTHORITY → EXACT ROW/VIEW → PACKET`。
適用 hard facts、current inventory、可結構化市場統計。

**B. Evidence retrieval lane**
`QUERY NORMALIZATION → STRUCTURED METADATA FILTER → KEYWORD + SEMANTIC CANDIDATE RETRIEVAL → RERANK → AUTHORITY/SCOPE/CURRENTNESS/EVIDENCE-CLASS FILTER → MINIMAL EVIDENCE PACKET`。
適用 audience/modification/practice evidence 等較非結構化資料。

規則：
- hybrid/semantic search 只提升 recall/relevance；`SEARCH_SCORE != AUTHORITY`。
- entity/scope/currentness/authority/evidence class 必須在 final selection 前保留。
- rerank 只能決定「哪個 evidence 更相關」，不能把低 authority 資料升格成 hard fact。
- consumer request 應帶 `QUERY_MODE / REQUIRED_DIMENSIONS / CURRENTNESS_REQUIREMENT / REQUESTED_SHAPE`；Library 只回必要資料，避免 overfetch。

## 38. CONNECTION_TO_CURRENT_LOGICS｜Library 配合所有邏輯，但不壓過任何邏輯
現行連結固定：
- `Library → Sales/Human`：提供 hard facts、current inventory、market snapshot、model-lineage delta、audience/modification evidence；Sales/Human 決定 relevance、target buyer、tradeoff、回覆與 next step。
- `Library → Visual`：只有透過現行 Sales acquisition bridge 的 market/product semantics，或 current task 明確 truth-sensitive literal/instance need；Library 不直接對 Visual 下「這群客人喜歡什麼畫面」指令。
- `Library → Execution`：只提供 source/instance truth、literal/compatibility factual constraints；不決定 route/control。
- `Library → GLOBAL`：只回 authority/currentness/gap/conflict/lineage/consumer-contract status；GLOBAL 不吸收車輛專業內容。
- `Human/Sales/Visual/Execution → Library`：只回 query need、missing dimension、stale/conflict signal、consumer-use failure；不能直接寫 Library fact value。

對使用者舉例的正式 owner 分配：
- 「即時市場行情變動」→ Library 蒐集/快照/qualification/時間序列；Sales 解讀市場策略。
- 「最新車源表」→ Library 做 source sync/current row；Sales 做排名/主打，Visual/Execution 按需取 instance truth。
- 「改款前後客群差異／車款客群特性」→ Library 收集 `MARKET_AUDIENCE_EVIDENCE + MODEL_LINEAGE_DELTA`；Sales/Human 決定是否、如何轉成 target buyer/話術/內容。
- 「改裝方向」→ Library 收集 `MODIFICATION_ECOSYSTEM_EVIDENCE`；不得自行變成銷售、視覺或實作 recommendation。

總原則：`LIBRARY_BETTER_DATA → BETTER_DOMAIN_INPUT`，不是 `LIBRARY_MORE_DATA → LIBRARY_MORE_AUTHORITY`。
