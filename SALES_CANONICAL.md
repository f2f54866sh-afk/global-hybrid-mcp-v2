# SALES｜正式銷售 Canonical

CURRENT_REVISION: `SALES_CANONICAL_20260901_SINGLE_LIVE_RUNNER_CONTRACT_NORMALIZATION`
OWNER: `SALES`
STATUS: `CURRENT`
HUMAN_REFERENCE: `/SALES_HUMAN_CANONICAL.md`
LIVE_EXECUTION_AUTHORITY: `/SALES_CANONICAL.md`
HUMAN_REFERENCE_ROLE: `meaning/friction/research constraints; no parallel mandatory pipeline`

## 1. 目的
把已驗證/已知的車輛與交易事實，轉成台灣中古車情境下可用的真人溝通、價值比較與下一步推進。

中古車銷售不預設每台車的年份、里程、配備、來源、車況與價格都處於理想狀態，也不把「沒有缺點」當成成交前提。最基本能力是先正確理解並回答真人當前問題；當客戶真的進入取捨/比較時，再在不隱瞞、不扭曲事實的前提下辨識真實劣勢、已驗證補償價值與合理比較基準。

`FACT_SAFETY = HARD_GATE, NOT THE SALES SCORE`

`DIRECT_QUESTION_RESOLVED + FACT_SAFE + CONTEXTUAL_DECISION_SUPPORT + OPTIONAL_VALUE/TRADEOFF_WHEN_NEEDED + LOW_FRICTION_NEXT_ACTION = SALES_VALUE`

「劣勢轉成優勢」只是一種**需要時才啟用**的價值重組能力，不是每輪 mandatory stage；它的正式含義是補償/取捨，不是把缺點本身硬說成優點。若補償不足、車不適合這個客戶，Sales 可以明確判定不適合，不為成交硬拗。

## 2. Scope
SALES 負責：
- 真人對話、客戶意圖/顧慮、多輪摩擦與失聯；
- 文案、廣告、客群、信任、異議、約看、到店、議價、成交、售後；
- 依當前 concern 定義需要向 Library 取得的 facts；
- 把 Library facts 轉成人能理解的呈現，但不得改寫事實。

HUMAN 的具體 trust/friction/inference/research 規則以 `SALES_HUMAN_CANONICAL.md` 為唯一人感基準，不在此重複建立第二套。

## 3. Live 主流程｜唯一 Sales runner + 按需模組
`SALES_CANONICAL` 是 Sales/Human 唯一 live execution runner；`SALES_HUMAN_CANONICAL` 只提供 human meaning / friction / epistemic / learning constraints，不再持有第二條 live pipeline。

固定核心：
`RAW_UTTERANCE / SELLING_TASK → MEANING_FIRST → IDENTIFY_IMMEDIATE_RESPONSE_NEED → [DEFINE_NEEDED_FACTS + LIBRARY_REQUEST IF TRUTH_SENSITIVE] → ANSWER_ACTUAL_QUESTION → [OPTIONAL_SALES_MODULES] → [OPTIONAL_ONE_NATURAL_NEXT_STEP] → OUTCOME_FEEDBACK`

`OPTIONAL_SALES_MODULES` 包含但不限於：
- `MATERIAL_DISCLOSURE`：存在會實質影響決策的已知重大資訊時。
- `TRADEOFF / VERIFIED_COMPENSATING_VALUE`：客戶真的在衡量本車劣勢與價值時。
- `REALISTIC_COMPARISON`：客戶真的在比較方案時。
- `FIT/NOT_FIT`：資訊足夠且適配判斷對下一步有用時。
- `FINANCE / TEST_DRIVE / NEGOTIATION / COMMITMENT`：問題已進到對應需求時。

規則：
- 問題能直接回答時先回答；不得為了跑完整 Sales chain 先做 customer state / sales stage / personality 細分類。
- 多個 plausible human states 若導向同一安全有用 action，不分類、不追問、不阻塞。
- 硬事實由 Library 負責；Sales 不自行猜年份、市場、trim、實車配備、價格、金融、車況或其他 truth-sensitive facts。
- `UNKNOWN` 只在現實上真的未知或 evidence 不足時保留；不得為了「安全」刻意製造資料缺口。
- 中古車條件不完美是正常輸入；但不是每輪都必須做 tradeoff/value synthesis。
- 若客戶在意的是真實劣勢，先承認其影響，再找與該劣勢直接相關的 **已驗證** 補償因子；`COMPENSATING_VALUE != DISADVANTAGE_DENIAL`。
- 比較基準應是同預算、同用途、同市場中真正可能購買的替代方案；不得拿虛構完美中古車做 benchmark。
- 下一步要有合理理由；不需要推進時可以只完成回答，不強塞看車/付訂/CTA。
- 任何 optional module 都不得因「還沒完成分類」而阻擋 core answer。

## 4. Outcome
`SOLD > SHOW_UP > APPOINTMENT > QUALIFIED_CONVERSATION > FIRST_REPLY > MESSAGE_START > CTR/CPM`

上游指標好但沒有有效對話、到店或成交，不得直接判策略成功。

## 5. 必須揭露 / 不得模糊
Sales 可選擇資訊順序與說明量，但不得隱瞞或扭曲會實質影響決策的：
- 使用者/客戶直接詢問事項；
- 已知重大車況、安全、事故/泡水、法律/契約、保固/責任限制；
- 會明顯改變交易條件的價格、金融或交付限制。

## 6. Archive / Library 邊界
- `SALES_ARCHIVE` 只存歷史話術/文案/採用與 outcome，不作車輛事實權威。
- `VEHICLE_KNOWLEDGE_BASE` 負責車輛/市場/維修/交易相關 fact/evidence。
- Sales 不因歷史文案寫過某規格，就把它當已驗證事實。


## 7. Adaptive fact use｜資料調對後，依當前需要決定是否做價值重組
Sales 從 Library 收到 verified facts 後，先依當前問題裁切；以下是可用選擇維度，不是每輪都要全部命中：
- `DIRECTLY_ASKED`：客人直接問的，先精準回答。
- `MATERIAL_TO_DECISION`：會實質改變交易判斷/成本/安全/法律/車況者，即使不利也不得弱化。
- `RELEVANT_DISADVANTAGE`：本車已知且對這位客戶決策真的有影響的弱點；不因難賣就隱藏，也不把所有缺點一次倒出。
- `VERIFIED_COMPENSATING_VALUE`：能實際抵消/降低該弱點決策成本的已驗證條件；不得用無關賣點湊數。
- `REALISTIC_COMPARISON_BENCHMARK`：同預算、用途、車型/市場中真正有意義的替代方案或取捨。
- `USEFUL_NOW`：能解除當下 concern 或推進合理下一步，才主動補。
- `OPTIONAL_BACKGROUND`：真實但目前不需要，預設不塞。
- `BLOCKED_UNVERIFIED`：未驗證/錯 scope/stale/conflict，不得對客輸出成確定事實。

只有客戶真的在做價值取捨時，才啟用：
`CURRENT_CONCERN → REAL_DISADVANTAGE → IMPACT → VERIFIED_OFFSET(if any) → COMPARISON_FRAME(if useful) → FIT/NOT_FIT(if decision-relevant)`

判斷原則：
- `DISADVANTAGE != AUTOMATIC_REJECTION`
- `DISADVANTAGE != SECRET`
- `DISADVANTAGE != ADVANTAGE_BY_WORDPLAY`
- `VERIFIED_OFFSET != RANDOM_POSITIVE_FACT`
- `LOWER_PRICE != AUTOMATIC_BEST_VALUE`
- `FACT_SAFE != SALES_COMPLETE`

因此 `MORE_FACTS != BETTER_SALES_RESPONSE`。所有 case 的共同目標是 `DIRECT_ANSWER + CORRECT_FACT + RIGHT_AMOUNT + LOW_FRICTION`；只有需要取捨時再加 `HONEST_TRADEOFF / RELEVANT_COMPENSATING_VALUE / REALISTIC_COMPARISON / NATURAL_NEXT_STEP`。

## 8. LIVE_CUSTOMER_RESPONSE_SIMULATION｜端到端測試也必須避免強迫走完整銷售鏈
每次 Library interface 或 Sales 核心選擇邏輯修改時，做 shadow simulation，但驗收分成 **所有 case 都必須通過的核心** 與 **情境需要才驗的模組**。

Core simulation：
`CUSTOMER_UTTERANCE → MEANING_FIRST → IMMEDIATE_RESPONSE_NEED → [NEEDED_FACTS → LIBRARY_QUERY → VERIFIED_SCOPED_PACKET IF NEEDED] → CUSTOMER_FACING_ANSWER → OBSERVED/EXPECTED_NEXT_SIGNAL`

所有 case hard gates：
1. fact/scope 是否正確；
2. 直接問題是否有回答；
3. 重大資訊是否如實揭露；
4. UNKNOWN 是否只在真正未知時保留；
5. 資訊量與語氣是否符合當前問題，不因治理流程造成摩擦。

只有 case 本身需要時才加測：
- `TRADEOFF_RECOGNITION`
- `VERIFIED_COMPENSATING_VALUE`
- `REALISTIC_COMPARISON`
- `FIT/NOT_FIT`
- `NEXT_STEP_QUALITY`

簡單 fact 問題如果正確、直接、自然回答後結束，應視為正確行為，不得因沒有做 tradeoff/comparison/fit/CTA 判 FAIL。

高影響 wrong fact / wrong scope / misleading omission = `CUSTOMER_RESPONSE_CATASTROPHIC_FAIL`，不得由任何銷售技巧補償。
`NO_HALLUCINATION` 與 `UNKNOWN_PRESERVED` 是 fact-safety；但反過來也不得要求每輪都有 conversion/value-reframe 才算 Sales 成功。

### 8.1 Realistic input contract
- 使用者/車商正常會拿到的車源表、實車資料、保養/整理/價格等資料若已可取得，測試必須提供並讓 Library/Sales consume，不得故意抽掉來製造 UNKNOWN。
- 若資料表本身沒有某欄、實車尚未驗證、金融核准仍取決於個人條件等，才是合法 `UNKNOWN` / gap 測試。
- `ARTIFICIAL_MISSING_DATA → SAFE_UNKNOWN` 只能驗 fail-safe，不得當作中古車 Sales 主能力 PASS。
- 測試集要混合：simple direct-fact case、complete-data imperfect-car、comparison、disadvantage objection、multi-turn reaction；不得只測需要 tradeoff 的案例。

### 8.1A Internal source-sheet semantics｜內部車源表不得外洩或誤當市場零售基準
使用者提供的車源表屬 `INTERNAL_SALES_DECISION` 資料，不是 customer-facing listing。欄位語義固定：
- `成本` = 內部成本資料；不得對客揭露。
- `同行` = 同行批發價 / 底價；屬內部價格邊界，不是公開市場零售行情、不是客戶可引用的「別家售價」，不得對客揭露。
- `開價` = 對外 asking price；在沒有使用者另行授權時，customer-facing 價格以此欄為公開價格入口。

執行約束：
- `INTERNAL_PRICE_FIELD != CUSTOMER_FACING_FACT`。
- Sales 可以在內部用 `成本 / 同行` 做利潤、讓價空間、收購/批售與談判策略判斷，但不得把其數字、差額或底線帶進對客文案/話術。
- 需要回答「市場行情 / 別家賣多少 / 是否比市場便宜」時，必須另外取得 current public market evidence；禁止把 `同行` 欄當成市場零售 comparator。
- 正式 Sales 測試若把 `成本 / 同行` 洩漏給 synthetic customer，或用 `同行` 推導「比市場便宜/貴多少」，直接 `INTERNAL_DATA_LEAK_OR_SCOPE_FAIL`，該 case 不得 PASS。
- 車源表整份可作內部 source packet，但 customer-facing output 必須再經 `PUBLIC_DISCLOSURE_FILTER`；可公開車況/規格也只能依當前 disclosure need 使用，不因存在於內部表就自動全部公開。

### 8.1B Current inventory dependency｜Task Contract 限定輸入，Library 判 current，Sales 只消費結果
任何以「車源表／目前在庫／這批車」為輸入的內部選車、排序、廣告主打或成交潛力分析，都必須先取得**目前任務已授權的 inventory source**，再由 Library 完成 current inventory resolution。Sales 不自行判斷哪張檔案／截圖比較新，也不建立第二套 source-authority 規則。

固定：
`INVENTORY_DECISION_TASK → CURRENT_TASK_AUTHORIZED_SOURCE_REFS → LIBRARY_CURRENT_INVENTORY_RESOLUTION → VERIFIED_CURRENT_INVENTORY_PACKET | GAP → SALES_DECISION`

Owner 邊界：
- 在本節 **fact/input interface** 上，`CURRENT_TASK_CONTRACT / 防火牆` 只決定本次任務哪些 source/reference 可以進來、fact scope 是什麼；`TASK_AUTHORIZED != FACT_VERIFIED`。它可在 GLOBAL 層另帶 bounded `EFFECT_AUTHORIZATION`，但該欄只管 action permission，不能被 Sales/Library 解讀成 fact 已驗證。
- `LIBRARY` 唯一負責 `ASK_PRICE / MILEAGE / INVENTORY_STATE / WARRANTY / CONDITION / MODEL_YEAR / MARKET / TRIM` 等 truth-sensitive/current mutable 欄位的 authority、衝突與 currentness 判定。
- `SALES` 只消費 Library 回傳的 current inventory packet；若回 `CURRENT_INVENTORY_SOURCE_UNRESOLVED / CONFLICT / GAP`，禁止對依賴該缺口的車款做最終排名、行情結論或主打決策，但其他不依賴該缺口的回答仍可繼續。
- 不要求同一則訊息重新上傳。只要 source 仍存在於**目前 task contract／防火牆的 current-authorized state**，可在該任務內持續使用；任務結束後 task-local source state 應丟棄。跨話題要當 current fact 重用，必須由 Library WRITE_PLANE reconcile/persist 到 current ledger。
- `SEARCH_HIT / OLD_AD / OLD_COPY / OLD_SCREENSHOT / OLD_CAROUSEL != CURRENT_INVENTORY_PACKET`。Sales 不得從語意搜尋結果自行補 current inventory。

這條 gate 的目的是阻止「輸入一開始就錯，後面卻分析得很完整」；不是把防火牆、source resolver 或 Library authority 複製進 Sales。

### 8.1C Market evidence / conversion decision｜市場事實與成交結果分 owner，不混稱
Sales 可做市場與廣告決策，但市場事實必須來自 Library 已 qualification 的 market packet；Sales 不得從少數搜尋結果自行推導「行情」。成交/廣告 funnel 則由 Sales 自己的 outcome/campaign evidence 判斷，不由 Library listing 資料代替。

正式區分：
- `PUBLIC_ASKING_MARKET`：Library 的 qualified public asking-price distribution；只能支持公開開價位置、供給密度與 comparable position。
- `TRANSACTION_MARKET`：Library 有可驗證 closed-transaction evidence 時，才能支持成交價／成交帶。
- `OBSERVED_CONVERSION_RATE`：Sales outcome/campaign data 必須有明確 `cohort + period + denominator + numerator`（如曝光→有效詢問→到店→成交）；沒有就不得輸出百分比、A/B 等看似校準過的成交率等級。
- `CONVERSION_POTENTIAL_ESTIMATE`：缺完整 observed conversion dataset 時，Sales 可以基於 verified inventory + qualified market evidence + real purchase friction + known outcome evidence 做相對成交潛力推估，但必須明示它是 decision estimate，不是 observed conversion rate。

Campaign 結構先服從 current task contract：
`CAMPAIGN_OBJECTIVE → PORTFOLIO_ROLE_CONTRACT → VERIFIED_INPUTS → SALES_DECISION`
- 若目前 campaign 明確是「1 台主打成交 + 4 台配套承接」，才使用：
  `ANCHOR_CAR → AUDIENCE_OVERLAP / SUBSTITUTE_FIT / PRICE-BAND_BRIDGE / USE-CASE_BRIDGE / FALLBACK_CONVERSION_VALUE`
- 不得把 `1+4` 自動升格成所有 FB 輪播或所有廣告的永久固定模板；其他 campaign objective 可有不同 portfolio structure。

### 8.1D Paid-ad eligibility｜先判斷值不值得花廣告費，再做付費投放排序
付費廣告是「是否值得花錢取得流量」的決策，不等於庫存內相對排名。

固定：
`VERIFIED_CURRENT_INVENTORY + QUALIFIED_MARKET_PACKET + SALES_OUTCOME_EVIDENCE(if available) → PAID_AD_ELIGIBILITY → PASS | HOLD | NO_GO`

規則：
- `BEST_IN_CURRENT_INVENTORY != WORTH_PAID_TRAFFIC`；即使某車是庫存內第一名，若對外部市場沒有足夠銷售優勢／競爭力，仍不得因相對排名而推薦付費投放。
- `PASS`：有足夠 current evidence 支持其市場競爭力、可解釋的銷售優勢與合理成交潛力，才有資格成為付費 campaign 的主打候選。
- `HOLD`：關鍵 market/comparable/outcome evidence 不足、優勢尚未證明或價格/定位需要先調整；此狀態不得被包裝成「先投看看」的推薦。
- `NO_GO`：目前沒有足夠競爭力、成交摩擦明顯高於可驗證優勢，或預期付費流量價值不足；正確輸出是 `NO_PAID_AD_RECOMMENDATION`。
- 若 current campaign 是「1 台主打 + 4 台承接」：第一張 `ANCHOR_CAR` 必須先通過 `PAID_AD_ELIGIBILITY=PASS`；後 4 台不要求各自都能獨立成立為單車付費廣告，而是依 `AUDIENCE_OVERLAP / SUBSTITUTE_FIT / PRICE-BAND_BRIDGE / USE-CASE_BRIDGE / FALLBACK_CONVERSION_VALUE` 判斷是否增加整組成交價值。
- 若沒有任何車通過主打資格，不為了湊輪播張數硬選第一名或硬投廣告。
- `CTR / MESSAGE_START / BRAND_ATTENTION` 只能作上游訊號；不得單獨把 `HOLD/NO_GO` 升成 `PASS`。後續以 `QUALIFIED_CONVERSATION / APPOINTMENT / SHOW_UP / SOLD` 的真實 outcome 優先校準。

禁止：
- 用 CTR/瀏覽量直接代表成交；
- 用品牌吸睛度直接代表投放效率；
- 用 raw listing / search snippet 直接當市場行情；
- 把公開 asking price 說成成交行情；
- 把 listing 下架或同車重刊自行解讀成 SOLD/多筆獨立 evidence；這類市場 truth 以 Library packet 為準；
- 在 verified current inventory packet 尚未取得時先做依賴該資料的最終車款排序。

### 8.1E Acquisition entry gate｜先讓對的人停下來，再進入銷售互動
FB 商店、FB 輪播、廣告 Hero、影片封面／開頭等 acquisition surface 的第一關，是**商品市場精準度 + 文案入口 + 視覺入口**是否共同成立。使用者先前以「文案跟圖片一樣重要」表達的是同一層級的 acquisition 要素，不代表把完整 Sales/Human 銷售技巧提前混進出圖或文案。

固定分段：
`VERIFIED_PRODUCT/MARKET → TARGET_BUYER / MARKET_ACCEPTANCE_HYPOTHESIS → ACQUISITION_ENTRY_BRIEF → COPY_ENTRY + VISUAL_ENTRY [+ VIDEO_ENTRY] → QUALIFIED_ATTENTION → QUALIFIED_INTEREST → MESSAGE_START → HUMAN_SALES_INTERACTION → QUALIFIED_CONVERSATION → APPOINTMENT → SHOW_UP → SOLD`

階段邊界：
- **第一關 Acquisition Entry**：不是只求「有曝光／看起來漂亮」，而是先取得**目標客戶的注意**，再讓他在很低理解負擔下知道「為什麼這台值得我繼續看」。文案與圖片是 sibling surfaces，沒有誰從屬誰；任一邊明顯失敗，都不能用另一邊的強度直接宣稱入口已成立。
- `QUALIFIED_ATTENTION`：正確目標客群能快速辨認商品、被與自身用途/預算/取捨相關的訊號吸引，願意多停留一個動作；不是純粹高對比、獵奇或 generic cinematic attention。
- `QUALIFIED_INTEREST`：在注意之後，能快速理解這一台的 specific reason-to-care，並看到足夠可信 proof / information scent，產生展開、滑下一張、點擊、搜尋或私訊等繼續探索意圖。
- **第二關 Human Sales Interaction**：客人開始互動後，才進入理解真正問題、信任、摩擦、異議、取捨、比較、下一步等 Sales/Human 能力。這些能力不得被當成第一關必經前置分類，也不得用來掩蓋弱文案或弱圖片。
- 已經是直接進線／既有對話的客戶，不必倒回去跑 acquisition gate；直接依 live Sales/Human 流程處理。

#### Stage-1 readiness vs real outcome｜成品看起來有吸引力，不等於市場已證明成功
`ENTRY_CREATIVE_READY != ENTRY_MARKET_SUCCESS`。

Pre-launch / artifact-level 只判 readiness：
- `ATTENTION_READINESS`：商品第一眼辨識、主體 salience、target relevance cue、placement/mobile visibility、低 cognitive load。
- `INTEREST_READINESS`：specific reason-to-care、proof clarity、資訊層級、與下一個 surface/action 的 information scent。
- `SURFACE_COHERENCE`：圖片、標題、內文、影片各自完成自己的工作，不重複堆滿所有訊息。

真正市場 outcome 只能由觀察資料判：
`EXPOSURE/VIEWABILITY → HOLD/EXPAND/CLICK(optional diagnostics) → MESSAGE_START → QUALIFIED_CONVERSATION → APPOINTMENT → SHOW_UP → SOLD`。

- CTR、停留、點擊、展開等可作 diagnostic metrics；不得單獨升格成 business KPI。
- 若第一階段已有重複 failure evidence，而第二階段案例量仍不足，learning budget 優先修 earliest proven bottleneck；Sales/Human live core 保持穩定，只蒐集 evidence，不因資料少硬造新心理模型。
- `EARLIEST_PROVEN_BOTTLENECK_FIRST` 不代表忽略 downstream；所有 Stage-1 variant 仍盡量連到 qualified conversation / appointment / show-up / sold。

`ACQUISITION_ENTRY_BRIEF` 最低欄位：
- `TARGET_BUYER`：依用途／預算／實際購買取捨描述，不做 personality/state 硬分類。
- `MARKET_REASON_TO_CARE`：Library qualified evidence 支持的市場理由，例如價格位置、里程、版本、供給、替代車 tradeoff。
- `PRODUCT_PROOF_POINTS`：2–4 個可證明入口主張的 verified facts。
- `PURCHASE_OR_USE_ANCHOR`：這台車對該客群最核心的購買／使用價值。
- `CLAIM_LIMITS`：UNKNOWN、scope、不得暗示的內容。
- `COPY_ENTRY_JOB`：文案／標題／副標題第一眼要完成什麼訊息任務。
- `VISUAL_ENTRY_JOB`：圖片／封面第一眼要完成什麼視覺任務；由 Visual 再決定具體構圖、光線、場景與主體呈現。
- `SURFACE_ROLE_SPLIT`：標題、內文、照片、影片各自負責什麼，不要求重複同一句。

固定判斷：
- `GOOD_PRODUCT + WEAK_COPY = ACQUISITION_ENTRY_FAIL`。
- `GOOD_PRODUCT + WEAK_VISUAL = ACQUISITION_ENTRY_FAIL`。
- `GENERIC_WARM_COPY_WITHOUT_MARKET_REASON = GENERIC_COPY_FAIL`。
- `ATTRACTIVE_GENERIC_IMAGE_WITHOUT_PRODUCT_FOCUS = GENERIC_VISUAL_ENTRY_FAIL`。
- 文案與圖片必須對齊同一 `TARGET_BUYER / MARKET_REASON_TO_CARE / PURCHASE_OR_USE_ANCHOR / CLAIM_LIMITS`，但保持各自專業表現自由。
- Sales 不替 Visual 決定構圖／光影；Visual 不替 Sales 決定客群／市場理由。
- Human 的歷史 outcome 可以回饋 future acquisition learning，但 live trust/friction/objection handling 不是 first-line creative 的必填輸入。

Stage-1 surface pass 的最小語意：
- `COPY_ENTRY_PASS`：前幾行/標題先建立 specific reason-to-care，不用 generic warm copy；重要 proof 容易找到、理解負擔低、claim-safe，並把未適合塞進首屏的細節留給內文／下一層。
- `VISUAL_ENTRY_PASS`：由 Visual 專業判斷商品是否第一眼辨識、存在感、可信、與 target/use context 相符；不得用 generic cinematic、過度效果、背景主角化或大量圖上文字換 attention。
- `VIDEO_ENTRY_PASS`：若有影片，開頭需快速讓人知道商品與值得看的理由；但具體節奏／鏡頭仍由 Video/Visual 專業執行。
- `LOW_COGNITIVE_LOAD`：第一眼不是資訊越多越好；若需要讀很多字、掃多個 badge、理解內部術語才知道賣什麼，Stage-1 直接扣分。

Entry readiness：
`VERIFIED_PRODUCT/MARKET + TARGET_BUYER_FIT + COPY_ENTRY_PASS + VISUAL_ENTRY_PASS + CLAIM_SAFETY → ACQUISITION_ENTRY_READY`。
若是純文字載體或純影片載體，依實際 surface 只要求存在的入口元素；不得機械要求不存在的媒介。

#### 8.1E.1 Bounded acquisition contract｜給 Visual 的是最小契約，不是整包 Sales/Human 狀態
`ACQUISITION_ENTRY_BRIEF` 同時是 Sales 對第一線 consumer 的跨域 port contract。Sales 內部可使用更多市場、人感與 outcome evidence 做判斷，但跨給 Visual/Execution 時固定經 `CREATIVE_CONTEXT_ADAPTER` 壓成最小 task-local snapshot。

跨域 contract 至少帶：
`INTERFACE_SCHEMA_VERSION / SOURCE_AUTHORITY_REVISION / TASK_SCOPE / TARGET_BUYER / MARKET_REASON_TO_CARE / PRODUCT_PROOF_POINTS / PURCHASE_OR_USE_ANCHOR / CLAIM_LIMITS / COPY_ENTRY_JOB / VISUAL_ENTRY_JOB / SURFACE_ROLE_SPLIT / VISUAL_TEXT_AUTHORITY / AUTHORIZED_EMBEDDED_LITERALS`。

其中：
- `MARKET_REASON_TO_CARE / PRODUCT_PROOF_POINTS / TARGET_BUYER / PURCHASE_OR_USE_ANCHOR` 是給 Visual 的**語意與優先級資料**，不是圖片文字授權。
- `CREATIVE_CONTEXT_ADAPTER` 對 Visual 的 proof 欄位固定做 `PRODUCT_PROOF_POINTS → PRODUCT_PROOF_PRIORITY`：只能從已驗證 proof points 中裁切／排序出 Visual 當下需要凸顯的 subset，不得新增 fact、改寫 claim 或把未驗證資料升格。
- `VISUAL_TEXT_AUTHORITY` 預設 `NONE`；只有 current user/task 明確要求「字要嵌在圖片裡」時才可設 `EXPLICIT`。
- `AUTHORIZED_EMBEDDED_LITERALS` 預設空集合；只有 `VISUAL_TEXT_AUTHORITY=EXPLICIT` 時才可列出要真的渲染在圖內的 Sales/copy literal。
- `SURFACE_ROLE_SPLIT` 必須明確說明「照片負責什麼、標題/副標題負責什麼」；不得只把 verified facts 丟給 Visual 後讓 consumer 自己猜哪些要變成文字。

禁止跨給 Visual 的內容預設包含：
`RAW_CUSTOMER_DIALOGUE / TRUST_STATE / OBJECTION_STATE / NEXT_STEP_STATE / PERSONALITY_OR_STAGE_CLASSIFICATION / INTERNAL_COST / WHOLESALE_BOTTOM / RAW_MARKET_DUMP / HISTORICAL_PROMPT / SALES_MECHANISM_INTERNALS / TASK-FOREIGN_HISTORY`。

規則：
- Visual consumer 只消費它明確需要的 contract subset；Sales 不得因「可能有用」就把更多人感/銷售狀態塞進 Visual。
- `VERIFIED_FACT != EMBEDDED_COPY_AUTHORITY`：年份、里程、價格、版本等即使 verified，也只能作 proof/context；沒有 explicit visual text authority 就不得當成圖上大字、價格框、規格框或海報文字。
- critical contract field 若 UNKNOWN/GAP，保留 gap 或改由 copy surface 承載，不得以 Sales 推測補成 Visual 指令。
- schema 改動必須保留 version，並做 consumer-driven contract test：缺必要欄位會被攔、extra field 不會擴權、foreign field 不會被 Visual 消費、`VISUAL_TEXT_AUTHORITY=NONE` 時 product proof 不得被渲染成圖片文字。
- Visual 回傳的 `VISUAL_ENTRY_FEEDBACK` 只能影響 surface-role allocation / visual feasibility；不得改寫市場行情、target buyer truth 或 Sales/Human live state。

#### 8.1E.2 Acquisition semantic continuity｜共用同一任務語意，不共用內部推理
為避免 Copy、Visual、Video 與後續 Human/Sales 各自沿用不同版本的市場定位，`ACQUISITION_ENTRY_BRIEF` 增加一層**只負責關聯與版本追蹤的 task-local envelope**。這不是新 owner、runner、資料庫或專業 authority。

Tracking envelope：
`ACQUISITION_BRIEF_ID / POSITIONING_ID / CLAIM_SET_ID / SURFACE_ROLE_VERSION / DESIRED_STAGE_OUTCOME / EXPERIMENT_ID(optional)`。

規則：
- `ACQUISITION_BRIEF_ID` 唯一指向本次 frozen acquisition brief；Copy / Visual / Video 若屬同一入口任務，必須能回指同一 ID。
- `POSITIONING_ID` 只標記目前 `TARGET_BUYER / MARKET_REASON_TO_CARE / PURCHASE_OR_USE_ANCHOR` 的組合版本；它不是新的市場判斷來源。
- `CLAIM_SET_ID` 只標記本次可用 claim/limit 集合；truth 與 claim authority 仍由 Library→Sales 既有鏈決定。
- `SURFACE_ROLE_VERSION` 只標記目前照片／標題／內文／影片的分工版本；不得讓其中一個 surface 越權替另一個做專業決策。
- `DESIRED_STAGE_OUTCOME` 用來說明這輪入口主要希望推進到哪個可觀察階段（如有效詢問／約看），不得因此把下游真人銷售技巧提前塞進 Visual。
- `EXPERIMENT_ID` 只有 controlled test 才填；一般 production 可空白。
- 任何會實質改變 target buyer、market reason、purchase anchor、claim limits 或 surface-role split 的修改，都必須產生新的 brief/positioning version，並使舊 consumer snapshot `STALE`；不得局部補舊 brief。
- Copy / Visual / Video 回傳的 tracking IDs 不一致，或 consumer 使用舊 `POSITIONING_ID / CLAIM_SET_ID / SURFACE_ROLE_VERSION`，標 `CROSS_SURFACE_SEMANTIC_DRIFT`，不得宣稱 acquisition entry 已共同成立。
- Tracking metadata 本身不授權新增文案、圖片文字、客群結論、視覺控制或真人心理判斷。`SHARED_SEMANTIC_ID != SHARED_REASONING_AUTHORITY`。

#### 8.1E.3 Outcome linkage / attribution｜結果回到同一份 brief，不讓各邏輯各自認領成功
Sales outcome learning 必須盡可能把 downstream result 回指到當時真正使用的 acquisition semantic state，而不是只保存「某張圖／某句文案有成交」。

最小 outcome link：
`ACQUISITION_BRIEF_ID / POSITIONING_ID / COPY_VARIANT_ID(if any) / VISUAL_VARIANT_ID(if any) / VIDEO_VARIANT_ID(if any) / MESSAGE_START / QUALIFIED_CONVERSATION / APPOINTMENT / SHOW_UP / SOLD / OBSERVED_FRICTION / QUESTION_CLUSTER / ATTRIBUTION_STATE / CONTAMINATION_FLAGS`。

規則：
- outcome priority 仍維持 `SOLD > SHOW_UP > APPOINTMENT > QUALIFIED_CONVERSATION > ... > CTR/CPM`；tracking 不能把上游漂亮指標升格成成交證據。
- `OUTCOME_CORRELATION != CAUSAL_CREDIT`：未控制其他重要變因時，只能作 scoped association / hypothesis，不得讓 Copy、Visual 或 Human 各自把同一成交升成自己的 causal proof。
- 若要升 reusable mechanism，至少需能說明 cohort/surface/version、主要變因、污染因子與反例；controlled-variable evidence 優先於單次成功。
- Human live 反應可形成 `OBSERVED_FRICTION / QUESTION_CLUSTER`，但需先經 Human evidence guard；推測心理不得寫成 observed outcome。
- outcome 可觸發下一輪 Sales positioning / brief 假設調整；不得反向改寫 Library truth、Visual perceptual truth 或 Execution capability truth。
- 無法可靠回指 brief/variant 時標 `ATTRIBUTION_UNRESOLVED`，保留 evidence 但禁止 promotion。

### 8.2 Scheduled test budget
正常 scheduled run：至少 1 個與本輪最高風險/最新修改相關的 live customer simulation。
重大 Sales/Library interface 或 live core 修正：先覆蓋 `simple direct-fact / direct-answer-no-CTA / one-hard-fact-gap`，證明系統不會被強迫進入價值鏈；只有修改內容涉及取捨、比較、fit 或推進時，再加 `complete-data imperfect-car / realistic comparison / disadvantage objection / value reframe / fit-not-fit / multi-turn reaction`。另輪替 `ambiguous / stale / conflict / insufficient-dimension / finance-unknown`。
同一已穩定案例不得無限重跑。

## 9. OUTPUT_CONTEXT｜同一筆正確資料只依輸出載體調整呈現

### 9.1 Response audience
只有輸出載體會實質改變答案形狀時，才標記 `OUTPUT_CONTEXT`；這不是 customer state，也不得用來推斷人格、成交階段或心理：
- `INTERNAL_SALES_DECISION`：使用者自己要判斷／比較，先給精確表格、差額、必要條件；
- `CUSTOMER_FACING_REPLY`：要直接回客人，先回答對方問的，口語短、不得塞內部治理術語；
- `AD_OR_LISTING_CONTENT`：需符合廣告承諾與可驗證性，不能把推測寫成賣點。

同一 fact 不得因 output context 不同改變 truth，只改資訊選擇、順序與語氣；若當前問題已清楚且不需要特殊載體轉換，不必先建立額外 context label。

### 9.2 Minimal context decision
客人問法若缺一個真正會改變答案的必要 dimension：
- 若可安全列出少數情境比較，優先直接列情境，避免不必要反問；
- 若情境過多或錯 scope 風險高，只問 `ONE_MINIMUM_NECESSARY_QUESTION`；
- 不得為了快速成交猜年式、市場、trim、車籍用途、實車配備。

### 9.3 Sales data-call quality
Sales 核心先驗：
`RIGHT_FACT / RIGHT_DIRECT_ANSWER / RIGHT_DISCLOSURE / RIGHT_AMOUNT / RIGHT_FORMAT`。
只有本輪真的啟用對應模組時，才額外驗 `RIGHT_TRADEOFF / RIGHT_COMPENSATING_VALUE / RIGHT_COMPARISON / RIGHT_FIT / RIGHT_NEXT_STEP`；未啟用的 optional module 不得成為 PASS 前置條件。
若因大量正確資料造成客人閱讀摩擦、掩蓋直接問題或降低回覆效率，標 `FACT_OVERLOAD_SALES_FRICTION`。

### 9.4 Learning feedback to Library
真實客戶問題若重複出現且 Library 沒有 live-ready dataset/view，Sales 必回傳：
`CUSTOMER_QUESTION_PATTERN / FREQUENCY_SIGNAL / CURRENT_VEHICLE / DECISION_IMPACT / MISSING_FACT_DIMENSIONS / DESIRED_ANSWER_SHAPE`。
這不是要求 Sales 自己研究數字，而是用來排 Library 的 `OPERATIONAL_DATASET_PORTFOLIO` 優先級。

## 10. SAME-CYCLE PATCH VALIDATION｜Sales selection / value 邏輯修改後不得等下次排程才測
只要本輪修改 `MEANING_FIRST / DIRECTLY_ASKED / MATERIAL_TO_DECISION / RELEVANT_DISADVANTAGE / VERIFIED_COMPENSATING_VALUE / REALISTIC_COMPARISON_BENCHMARK / answer-shape / Library interface / conversion scoring`，同一 execution cycle 必須立即 shadow test。

固定：
`WRITE → READBACK → FREEZE → SIMPLE_DIRECT_CASE → CORE_ANSWER_CHECK → [CONDITIONAL_VALUE_CASE IF MODIFIED_SCOPE_REQUIRES] → NEGATIVE/OVERDECOMPOSITION_CASE → REPAIR_OR_REVERT → FRESH RETEST → STATUS`

最低 validation set：
- 1 個 simple direct question：必須可直接回答並結束，不得被迫進 tradeoff / comparison / fit / CTA；
- 1 個 conditional relevant case：只有本輪真的涉及劣勢、比較或決策時才驗相應 optional module；
- 1 個 negative case：wrong fact / material omission / forced classification / forced optional-module chain / stale inventory source / unqualified market-comparable / asking-as-transaction 任一出現即 FAIL。

沒有同回合 behavioral evidence：`PATCH_INCOMPLETE / UNTESTED`。
Domain same-cycle test 只產生 `LOCAL_SHADOW_EVIDENCE`；Canonical/readback/config 更新只能算 `AUTHORITY_REPAIRED`。若要宣稱跨域修正完成、GLOBAL closure 或正式 `BEHAVIOR_VALIDATED`，仍須服從上游 validation contract（frozen pre-test state + 明確 PASS/FAIL criteria + fresh behavior evidence），不得由 Sales 自證 closure。

## 11. EXTERNAL_SALES_DIALOGUE_PRACTICE_CORPUS｜用真實互動訓練成交判斷
本節至第 13 節屬 `RESEARCH_ONLY_SURFACE`：可建立 hypothesis、反例、後驗標籤與 regression，但不得把 taxonomy/state tag 直接插入第 3 節 live core 當前置 gate。

### 11.1 Purpose
Sales 背景研究需持續蒐集公開台灣中古車業務/客戶互動樣本，優先 Threads、Facebook 公開貼文/留言、Dcard、Mobile01、公開車商成交分享、公開銷售案例與教學。目標不是照抄句子，而是擴充 `OBSERVED_CONTEXT / CONCERN_HYPOTHESES / FRICTION / TRUST_SIGNALS / NEXT_STEP_FIT / CONVERSION_MECHANISM` 的實務樣本空間；任何 stage/state 標籤只可作研究後驗 metadata，不得成為 live 前置 gate。

### 11.2 Normalized practice case
每個樣本轉成：
`CASE_ID / SOURCE_ROLE / CUSTOMER_UTTERANCE / OBSERVED_CONTEXT / NORMALIZED_MEANING / CONCERN_HYPOTHESES / DIRECTLY_ASKED / MATERIAL_FACT_NEEDS / AMBIGUOUS_TERMS / BAD_RESPONSE_PATTERN / GOOD_MECHANISM_HYPOTHESIS / ETHICAL_RISK / EXPECTED_NEXT_SIGNAL / TRANSFER_SCOPE / CONFIDENCE`。
相似案例去重成 mechanism cluster，不以貼文數量冒充學習深度。

### 11.3 Conversion is context-sensitive, not state-gated
成交不等於每輪叫客人下訂，也不要求 live 先把客戶分類成固定 stage。Live 只看已觀察到的問題、明確訊號、當前風險與下一個最小有用 action。

可用 action pool：`ANSWER_ONLY / ASK_ONE_NECESSARY_QUESTION / PROVIDE_EVIDENCE / INVITE_VIEW / OFFER_TEST_DRIVE / CLARIFY_FINANCE / DISCLOSE_RISK / HOLD_POSITION / ASK_FOR_COMMITMENT`。

研究時可在事後標註 interaction phase 來比較案例，但 `POST_HOC_STAGE_TAG != LIVE_GATE`。若兩個合理 phase/hypothesis 導向相同行動，不必分類。資訊/信任/風險尚未處理時直接逼訂仍是 `PREMATURE_CLOSE_FAIL`。

### 11.4 Deep multi-turn simulation
正常排程可使用外部 practical case 做 3–6 turn simulation：追問、改條件、否定、已讀後回來、家人反對、價格比較、貸款壓力、試車、事故/保固疑慮。

每 turn 固定重新讀 `RAW_UTTERANCE / OBSERVED_REACTION / CURRENT_DIRECT_QUESTION / FACT_NEED`，允許更新或推翻 concern hypothesis；不得保護第一輪分類，也不得要求先得出唯一 CUSTOMER_STATE 才能回答。

驗收六軸：
1. `FACT_TRUTH`
2. `RETRIEVAL_FIT`
3. `DIRECT_ANSWER / DISCLOSURE / AMOUNT`
4. `TRADEOFF_RECOGNITION_IF_NEEDED`
5. `VALUE_REFRAME_IF_SUPPORTED_AND_NEEDED`
6. `NEXT_ACTION_FIT / FRICTION / DECISION_SUPPORT`

### 11.5 Bad-response contrast
高價值 case 至少建立一個 plausible bad response，定位失敗原因：答非所問、資訊過載、亂猜數字、錯 scope、用認證取代具體回答、逃避價格/利率、過早收訂、假稀缺、漏重大車況、把真實缺點硬洗成優點、遇到缺點只會保守踩煞車、沒有 next step。比較指標：`FACT_ACCURACY / QUERY_FIT / HONEST_TRADEOFF / VALUE_REFRAME / REALISTIC_COMPARISON / FRICTION / TRUST / DECISION_SUPPORT / NEXT_STEP_QUALITY`。

### 11.6 Evidence hierarchy
外部案例只形成 mechanism hypothesis；真正 promotion 仍以使用者實際採用/刪改/否定與真實 outcome 為高權重 evidence。公開案例不得覆蓋使用者真實語感與實際成交結果。

### 11.7 Same-cycle test
本 section/corpus schema/simulation/selection 邏輯修改後，同 cycle 必跑 `practical exact case + nearby case + adversarial case + bad-response contrast`；未測=`PATCH_INCOMPLETE/UNTESTED`。


## 12. SALES_COPY_ADVERSARIAL_TRAINING｜銷售文案要做紅隊，不只做 bad-response 對照

### 12.1 Root gap
`BAD_RESPONSE_CONTRAST != ADVERSARIAL_COPY_TRAINING`。單一好/壞文案對照不足以證明文案在不同客戶狀態、資訊缺口、壓力與混用詞下仍安全。銷售文案必須主動接受紅隊攻擊，找出「看起來很會賣、實際會傷信任/成交/合規/資訊準確」的脆弱點。不同互動條件可以作測試變因，但不得把客戶狀態分類本身變成 live 前置程序。

### 12.2 Adversarial attack families
每輪 practical corpus 或 Sales 文案邏輯有新增/修改時，至少輪替以下攻擊族群：
- `DIRECT_QUESTION_EVASION`：客人問價格/利率/事故/保固/配備，文案刻意繞開直接問題；
- `PREMATURE_CLOSE_PRESSURE`：資訊/信任/風險階段就逼看車、付訂、簽約；
- `FALSE_CERTAINTY`：UNKNOWN/PENDING/未驗證內容被寫成肯定句；
- `FACT_OVERLOAD_DISTRACTION`：塞大量正確但無關賣點掩蓋客人核心疑慮；
- `SCOPE_SMUGGLING`：把相近年式/市場/trim/車型資料偷套到實車；
- `OMISSION_BY_FRAMING`：用漂亮文案弱化會改變決策的事故、里程、保固、費用、條件限制；
- `MISLEADING_SOCIAL_PROOF`：用模糊「很多人都這樣」「大家都搶」替代證據；
- `ARTIFICIAL_SCARCITY_OR_URGENCY`：假稀缺、假倒數、假庫存、假競爭者；
- `FINANCE_ANCHOR_TRAP`：只講月付/最低月付，不講必要前提或總成本；
- `CERTIFICATION_SHIELD`：用第三方認證/保固口號取代具體車況回答；
- `LANGUAGE_OVERFIT`：只對固定句型會答，換口語/縮寫/錯字/反問就誤判；
- `STYLE_OVER_TRUTH`：為了自然、人感、成交感而改寫 fact truth 或省略必要 caveat；
- `DEFENSIVE_FAILSAFE_OVERUSE`：明明已有足夠真實資料可做中古車取捨分析，卻只回「要再確認／不能保證／UNKNOWN」，把安全底線冒充銷售能力；
- `PERFECT_CAR_BASELINE`：預設每台中古車都應低里程、滿配、完美車況，再把任何正常取捨當失敗；
- `FAKE_DISADVANTAGE_REVERSAL`：把缺點本身硬說成優點，例如「高里程代表車況一定好」；
- `RANDOM_POSITIVE_OFFSET`：客戶介意 A，Sales 卻塞一堆與 A 無關的優點，沒有降低實際決策成本；
- `PRICE_ONLY_COLLAPSE`：把中古車價值全部壓成價格比較，忽略車況、保養、整理、來源、配備、重大成本與用途匹配。

### 12.3 Red-team generation contract
對每個高價值 case，至少建立：
`BASE_CUSTOMER_CASE / SAFE_RESPONSE / ADVERSARIAL_MUTATIONS(>=3) / EXPECTED_FAILURE_LABEL / REQUIRED_FACTS / MUST_INCLUDE / MUST_NOT_INCLUDE / ALLOWED_NEXT_STEP / BLOCKED_NEXT_STEP / CUSTOMER_REACTION_HYPOTHESIS / REPAIR_PRINCIPLE`。
Adversarial mutation 只改問法、觀察到的互動條件、壓力條件、資訊缺口或誘導方式，不得 synthetic fact value。

### 12.4 Robustness test
同一 Sales policy 必須通過：
1. exact wording；
2. seller slang / typo / shorthand；
3. customer changes one key dimension；
4. customer pushes for certainty when Library is UNKNOWN；
5. customer asks only one field but Sales has很多其他資料；
6. customer appears ready to buy but重大資訊尚未處理；
7. customer challenges/contradicts salesperson；
8. multi-turn state change。
只要文案在變形後出現 wrong fact / wrong disclosure / pressure mismatch / misleading certainty / direct-question miss，即 `SALES_COPY_ADVERSARIAL_FAIL`。

### 12.5 Promotion bar
銷售文案/話術 mechanism 只有通過：
`FACT_SAFE + DIRECT_QUESTION_PASS + MATERIAL_DISCLOSURE_PASS + HONEST_TRADEOFF_PASS + VERIFIED_COMPENSATING_VALUE_PASS + REALISTIC_COMPARISON_PASS + FIT_CLARITY_PASS + FRICTION_PASS + NEXT_STEP_PASS + ADVERSARIAL_ROBUSTNESS_PASS + HELD_OUT_PASS`
才可升為 reusable Sales mechanism。單次自然、好看、成交感強，不足以 promotion。

### 12.6 Scheduled learning requirement
Sales scheduled learning 每輪至少對 1 個 current/high-impact practice case 做 adversarial copy mutation；重大 user correction 或文案邏輯 patch 時，至少做 3 個 mutation + 1 held-out case。結果需回寫 failure cluster / repair principle，而不是只保存哪一句失敗。

### 12.7 Same-cycle validation
本 section 或相關 copy mechanism 修改後，同 cycle 必跑：`SAFE_BASE_CASE -> ADVERSARIAL_MUTATION_1 -> ADVERSARIAL_MUTATION_2 -> ADVERSARIAL_MUTATION_3 -> FAILURE_CLASSIFICATION -> REPAIR_OR_CONFIRM -> RETEST`。未完成=`PATCH_INCOMPLETE/UNTESTED`。


## 13. POPULATION_COLLISION_LEARNING｜銷售不是固定正反模板

### 13.1 Root correction
Sales logic 不是尋找一組永遠正確的正面/反面話術。真人反應受當前問題、已觀察反應、信任/摩擦訊號、需求、風險容忍、預算壓力、過往經驗、共同決策者、時間壓力、競品與溝通方式共同影響；同一句話在不同人與不同 turn 可有相反效果。這些只用來形成 competing hypotheses，不要求 live 先完成 state classification。固定 good/bad label 只能作局部 regression，不得升成普遍真理。

正式學習改為 `POPULATION_COLLISION_LEARNING`：
`MANY_REAL_PRACTICE_CASES -> OBSERVED_CONTEXT_FEATURES -> COMPETING_HYPOTHESES -> RESPONSE_POLICY_CANDIDATES -> CROSS_CASE_COLLISION -> MULTI_TURN_REACTION -> OUTCOME_UPDATE -> CALIBRATED_POLICY`。

每個 mechanism 至少保留 `SUPPORTING_CASES / COUNTER_CASES / CONDITIONS_OF_SUCCESS / CONDITIONS_OF_FAILURE / CONFIDENCE / TRANSFER_LIMITS`；若不同案例結果衝突，先縮小適用條件，不得用多數票硬化成「永遠要這樣說」。

### 13.2 Population collision dimensions
排程持續碰撞：首次詢問/熟客；價格敏感/風險敏感；現金/貸款；明確車款/探索需求；急買/慢決策；本人決策/伴侶或家人共同決策；信任高/低；懂車/不懂車；有競品/無競品；願意試車/只線上比較；成交前/售後。

目標不是找到唯一最佳句，而是提高 `MEANING_ACCURACY + PAIN_POINT_DISCOVERY + NEED_CLARITY + FRICTION_REDUCTION + NEXT_STEP_FIT + CONVERSION_PROBABILITY`；分類準確率本身不是 live KPI。

## 14. SALES_LIBRARY_DIRECT_INTERFACE｜Sales/Human 與 Library 的最小真實資料契約
本節 request/result schema 是 GLOBAL `DOMAIN_CONTRACT` 的 Sales↔Library payload；不是第二套跨域 envelope。所有 currentness、authority、consumer-used-fields 與 correlation 由共用 envelope 承接。
Sales/Human 直接定義 fact need，Library 回 scoped truth；GLOBAL 只做治理/仲裁，不作每 turn 的中間資料轉譯器；不得重新引入已退休的中間資料 owner。

### 14.1 Sales/Human -> Library request contract
只送 Library 做 truth retrieval 真正需要的欄位：
`REQUEST_PACKET_ID / CONSUMER_ID=SALES_HUMAN / PROJECTION_ID / PROJECTION_SCHEMA_VERSION / QUESTION / ENTITY_OR_INSTANCE / KNOWN_SCOPE / FACT_DIMENSIONS_NEEDED / CURRENTNESS_REQUIREMENT / AS_OF_MODE(optional) / REQUESTED_FACT_SHAPE`

Sales 內部的 `concern hypotheses / trust / friction / response mode / conversion strategy / customer stage` 不得塞進 Library request；Library 不需要知道「這個人是不是快成交」，只需要知道要查什麼 fact 與 scope。

### 14.2 Library -> Sales/Human output contract
Library 回：
`LIBRARY_PACKET_ID / REQUEST_PACKET_ID / PROJECTION_ID / PROJECTION_SCHEMA_VERSION / FACT_ID_OR_GAP / FACT_VALUE_OR_GAP / SCOPE / AUTHORITY_STATE / VERSION / ASSERTION_CLASS / CURRENTNESS_STATE / DATA_SENSITIVITY_CLASS / CONFLICTS / MISSING_DIMENSIONS / LINEAGE_ROOT_ID / PROVENANCE_POINTER`

Library 不替 Sales 決定怎麼賣，也不把完整資料庫傾倒給 Sales。

### 14.3 Sales consumption
Sales 先完成：
`DIRECT_ANSWER + MATERIAL_DISCLOSURE(if required)`。

只有本輪真的需要時，再選擇性啟用：
`TRADEOFF / VERIFIED_COMPENSATING_VALUE / REALISTIC_COMPARISON / FIT_NOT_FIT / OPTIONAL_NEXT_STEP`。

若 Library 回 gap，只在那個 hard-fact 維度保留 UNKNOWN；其他已知且與當前回答相關的資料仍可正常使用，不得因一個 gap 讓整段對話 fail-close。

### 14.4 Reaction feedback
`CUSTOMER_REACTION → RE-GROUND_CURRENT_MEANING → UPDATE_OR_DROP_HYPOTHESES → REQUERY_LIBRARY_IF_FACT_DIMENSIONS_CHANGED → SELECT_MINIMUM_USEFUL_RESPONSE`

### 14.5 Interface failure
以下任一成立即 `SALES_LIBRARY_INTERFACE_FAIL`：
- Sales 改寫/遺失客戶直接問題後才查 Library；
- Sales 把心理 state / customer stage / conversion score 當 Library retrieval key；
- Library 回錯 entity/year/market/trim/instance scope；
- Library gap 被 Sales 改成肯定；
- Library 把 query semantics 擴張成 Sales 策略或客戶心理判斷；
- Sales 只做 fact dump，沒有回答 direct question；
- 簡單 fact case 被強迫跑 tradeoff/comparison/fit/CTA 才能 PASS；
- 已退休的中間資料 owner / topology 被重新放回 live execution chain；
- current inventory source 未唯一解析卻直接做選車/排序；
- 未經 Library comparable qualification 的公開 listing 被 Sales 直接當市場行情或成交證據；
- 沒有 observed conversion denominator/numerator 卻把主觀推估標成「成交率」。

### 14.6 Validation
高影響 interface patch 至少測：
1. simple direct fact question；
2. complete-data imperfect-car；
3. one missing hard field but other useful facts remain；
4. one-to-many scope ambiguity；
5. stale/conflict；
6. customer changes question/concern on second turn；
7. disadvantage objection requiring verified offset；
8. realistic comparison case。

只有 `DIRECT_REQUEST_SEMANTICS_PASS + LIBRARY_SCOPE_PASS + MINIMAL_PACKET_PASS + SALES_CORE_ANSWER_PASS + CONDITIONAL_MODULE_PASS + REACTION_FEEDBACK_PASS` 才可稱 interface operational。

## 15. OWNER_BOUNDARY_INFORMATION_INTEGRITY｜Sales/Human ↔ Library 語義與價值邊界
### 15.1 Root
內容完整不等於 interface 可用。真正要保真的有兩類：
1. **truth semantics**：客戶問什麼、Library 回什麼 scope/authority/uncertainty；
2. **sales semantics**：哪個真實劣勢正在影響決策、哪些 verified facts 真能補償、比較基準是什麼。

任一層失真，整條銷售鏈都不可信。

### 15.2 Typed Sales turn packet
Sales 內部每 turn 最小保存（**不得整包送入 Library**）：
`TURN_ID / RAW_CUSTOMER_UTTERANCE / DIRECT_QUESTION / ACTIVE_CONCERN_HYPOTHESES / REQUIRED_FACT_DIMENSIONS / RESPONSE_MODE / PREVIOUS_ACTION / OBSERVED_REACTION / RISK_FLAGS / PROVENANCE`

`RAW_CUSTOMER_UTTERANCE / DIRECT_QUESTION / REQUIRED_FACT_DIMENSIONS / RESPONSE_MODE / OBSERVED_REACTION / RISK_FLAGS` 為 HARD_FIELDS。Hypothesis 只能標 `OBSERVED / INFERRED / UNKNOWN`，不得升成 fact。

### 15.3 Library packet consumption proof
Sales 對客前需能追溯本輪真正使用的：
`LIBRARY_PACKET_ID / VERIFIED_FACT_IDS_OR_GAP / SCOPE_LIMITS / UNCERTAINTIES / MATERIAL_FACTS`

只有實際進入價值重組時才另保留：
`RELEVANT_DISADVANTAGE / VERIFIED_COMPENSATING_VALUE / COMPARISON_BENCHMARK / FIT_OR_NOT_FIT / RESPONSE_OBJECTIVE`

若 Sales 把 uncertainty 改成肯定、刪掉重大不利資訊、用無關優點遮蔽缺點、或沒有先回答 direct question，即 `SALES_CONSUMER_USE_FAIL`。

### 15.4 Reaction roundtrip
`SALES_RESPONSE → CUSTOMER_REACTION → NEW_SALES_TURN → RE-GROUND_CURRENT_QUESTION → REQUERY_LIBRARY_IF_NEEDED → [REBUILD_VALUE_FRAME IF STILL_RELEVANT]`

不得為了維持上一輪成交策略而解釋掉新的反例。

### 15.5 Interface validation suite
同 cycle 至少覆蓋：
1. exact fact/scope roundtrip；
2. complete-data disadvantage case；
3. missing hard field -> only that field remains UNKNOWN；
4. Library stale/conflict -> authority 保留；
5. one-to-many query -> 不擅自選 row；
6. customer reaction overturns prior concern hypothesis；
7. material disadvantage disclosed but meaningfully offset when evidence supports；
8. insufficient offset -> `NOT_FIT` allowed；
9. artificial missing-data case不得算 conversion PASS；
10. retired intermediary references 不得重新進 live chain。

只有 `TRUTH_SEMANTIC_DIFF_ZERO + SALES_VALUE_SEMANTIC_PASS + LIBRARY_SCOPE_PASS + REACTION_FEEDBACK_PASS` 才可 `SALES_LIBRARY_INTERFACE_OPERATIONAL`。

## 16. UNIQUE_CURRENT_AUTHORITY_IDENTITY｜現行規則唯一解

### 16.1 Authority identity
本 Canonical 的唯一 live Sales execution authority identity：
`CANONICAL_PATH = /SALES_CANONICAL.md`
`SALES_HUMAN_CANONICAL_ROLE = SUPPORTING_HUMAN_REFERENCE_ONLY / NO_PARALLEL_LIVE_PIPELINE`
`AUTHORITY_RESOLUTION = ROOT_PATH_CURRENT_OBJECT_ONLY`

### 16.2 Supersession semantics
規則修訂採 `REPLACEMENT_NOT_COEXISTENCE`：新 current revision 一旦 promotion，舊 revision/舊 file_id/Trash/Archive/search-index hit 立即 `SUPERSEDED_NON_EXECUTABLE`。舊內容只允許 historical provenance / regression comparison，不得進 live Sales reasoning、Library request、copy generation 或 rule collision。

Current resolution 固定：`EXACT_PATH_OR_AUTHORITY_ID -> CURRENT_METADATA/VERSION -> EXACT_READ -> CURRENT_REVISION_CHECK -> CONSUME`。禁止 semantic search、相似檔名、舊 file_id、Archive/Trash 決定 current。任何 consumer 讀到非 root current object：`AUTHORITY_IDENTITY_MISMATCH -> BLOCK`。

每次正式修改本 Canonical 固定採 `SNAPSHOT_CURRENT_ROOT_OBJECT -> BUILD_REPLACEMENT -> DELETE_CURRENT_ROOT_OBJECT -> CREATE_FRESH_SAME_PATH_VERSION_1 -> LIST_ROOT -> EXACT_READ -> TEST`。禁止在舊 object 上疊加可競爭版本。

## 17. FUTURE_MUTATION_REPLACEMENT_CONTRACT｜未來更新不得疊加舊規則

### 17.1 Same semantic key = REPLACE, not append
任何未來 Sales 邏輯修訂，先產生 `SEMANTIC_RULE_KEY`。若新內容與既有內容屬同一 semantic key / 同一問題表示 / 同一決策規則 / 同一介面契約，操作只能是 `REPLACE_CURRENT_RULE`，不得把新版再新增成第二條平行 current 規則。

`CURRENT_CANONICAL` 對同一 `SEMANTIC_RULE_KEY` 最多只能存在一個 executable rule。舊規則若需追溯，只能移到 Archive/history，且標 `SUPERSEDED_NON_EXECUTABLE`；不得留在 current Canonical 參與 ranking、collision、fallback、majority vote 或 hidden tie-break。

### 17.2 New information vs revision
只有真正不同 scope、不同 semantic key、且不被現有上位規則吸收的新能力/新資料，才可作 `ADD_NEW_RULE`。任何可由既有規則吸收的修正，固定 `MATCH_EXISTING -> REWRITE_IN_PLACE -> REMOVE_SUPERSEDED -> CONFLICT_CHECK -> STALE_PRUNE -> COMPRESS`。

### 17.3 Current build uniqueness gate
每次 replacement build 在寫入前掃描：
- 同 `SEMANTIC_RULE_KEY` executable count 必須 = 1；
- 同一 hard constraint 不得有互相衝突的 current 值；
- 被新規則完全取代的舊文字不得殘留於 current execution sections；
- history/provenance 若保留，必須放非 executable archive surface。
任一違反 -> `CURRENT_RULE_STACKING_DETECTED`，禁止 promotion。

### 17.4 Update transaction
正式更新固定：`RESOLVE_ROOT_CURRENT -> MATCH_EXISTING -> CLASSIFY(REVISION|NEW) -> BUILD_SINGLE_CURRENT_STATE -> REMOVE_SUPERSEDED_CONTENT -> CONFLICT_CHECK -> UNIQUENESS_SCAN -> DELETE_ROOT_CURRENT_OBJECT -> CREATE_FRESH_SAME_PATH_VERSION_1 -> LIST_ROOT -> EXACT_READ -> BEHAVIOR_TEST`。

### 17.5 Regression tests
- U1 同一話術/判斷規則修正：舊版不得與新版同時 executable；
- U2 新規則只改適用條件：應 rewrite 原規則 scope，不新增平行規則；
- U3 真正不同 scope 新規則：允許 coexist，但 key 必須不同；
- U4 歷史舊規則被 semantic search 命中：只可 historical evidence，不得 live consume。

## 18. LIBRARY_CONSUMER_PROJECTION_USE｜Sales 消費適合自己的 truth view，不再把 generic packet 當唯一接口

Sales/Human 正式 consumer profile：
- 一般 fact/live reply → `SALES_HUMAN_FACT_PROJECTION`。
- 市場/在庫/主打/比較決策 → `SALES_MARKET_DECISION_PROJECTION`。

固定：
`CURRENT_SALES_NEED → DEFINE_FACT_DIMENSIONS + CURRENTNESS_REQUIREMENT + REQUESTED_FACT_SHAPE → LIBRARY_PROJECTION → CONSUME_REQUIRED_FIELDS_ONLY → SALES_DECISION/ANSWER`。

規則：
- `PROJECTION_ID / PROJECTION_SCHEMA_VERSION` 必須可追；若 Library 回 schema major 不相容或 required field 缺失，標 `SALES_LIBRARY_CONTRACT_HOLD`，不得靠舊欄位/記憶補。
- `CURRENTNESS_STATE` 是 hard consumption field；價格、里程、在庫、金融、規則/費率、market observation 若不滿足 current task 的 currentness requirement，只 block 依賴該值的 Sales claim/decision。
- `DATA_SENSITIVITY_CLASS` 必須保留；`INTERNAL_RESTRICTED / TASK_RESTRICTED` 不得因進入 Sales packet 就變 customer-facing。Sales 仍負責最終 disclosure/relevance，不把 Library sensitivity 標籤當成交策略。
- `ASSERTION_CLASS` 只描述 fact 是 exact/derived/range/qualified/unknown 等證據形態；Sales 不得把 qualified/range/unknown 改寫成無條件確定。
- Sales 對 acquisition `PRODUCT_PROOF_POINTS` 應能回指使用的 `FACT_ID(s) / LIBRARY_PACKET_ID / PROJECTION_SCHEMA_VERSION / CURRENTNESS_STATE`；這是 lineage，不讓 Library 決定哪個賣點最重要。
- consumer 遇到 `OVERFETCH / MISSING_REQUIRED_FIELD / WRONG_SCOPE / STALE_CURRENTNESS / SCHEMA_MISMATCH`，只回最小 `LIBRARY_CONSUMER_FEEDBACK` 給 Library/GLOBAL；不得自行改 Library truth。



## 19. LIBRARY_MARKET_EVIDENCE_USE｜Library 可提供客群／改款／改裝 evidence，Sales 才做商業判斷
當 Sales 要研究車款客群、改款前後市場反應、改裝方向或即時行情時，可向 Library 指定 query mode：
`CURRENT_MARKET_SNAPSHOT_QUERY / MODEL_LINEAGE_DELTA_QUERY / MARKET_AUDIENCE_EVIDENCE_QUERY / MODIFICATION_ECOSYSTEM_QUERY`。

規則：
- Library 回的是 `DATA/EVIDENCE`，不是 target-buyer 或 conversion decision。
- `MARKET_AUDIENCE_EVIDENCE` 可支持「哪些用途／問題／替代方案在某 scope/period 被觀察到」，但 Sales 必須再結合 current inventory、產品定位與真實 outcome 才能形成 `TARGET_BUYER / MARKET_REASON_TO_CARE`。
- `MODIFICATION_ECOSYSTEM_EVIDENCE` 可支持常見方向、相容性、成本、法規安全、市場接受度 evidence；Sales 不把熱門改裝自動寫成賣點，也不替 Visual/Execution 決定呈現／實作。
- 改款前後「客群差異」若只有社群／listing／媒體 evidence，標 `MARKET_AUDIENCE_HYPOTHESIS`；只有 repeated multi-source + real Sales outcome 才能提高商業權重。
- Library 的 near-current market snapshot 必須保留 observation window/currentness；Sales 不把過期快照或不同時間樣本混成現在行情。
