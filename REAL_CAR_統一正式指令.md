# REAL_CAR｜Current Visual / Execution Shared Canonical

CURRENT_REVISION: `REAL_CAR_20260902_TEST_CIRCUIT_BREAKER_END_TO_END_RELEVANCE_GATE`
STATUS: `CURRENT`

### Authority partition｜同檔共用，不代表 owner 合併
本檔是 REAL_CAR 的單一 shared Canonical，承載 Visual Judge、Execution Lab 與兩者的 interface contract；**同檔共用不建立新的合併 owner**。

- `VISUAL_JUDGE_AUTHORITY`：決定可見結果是否 SAME_CAR、主體層級、3D/材質/光影是否成立、相對 baseline 是否進步、是否有 perceptual regression。Visual 可判 PASS/FAIL evidence，但不得宣稱某 route/tool 具有未被證明的控制能力。
- `EXECUTION_LAB_AUTHORITY`：決定目前 callable route、control scope、route eligibility、可執行變因、能力邊界與 causal learning。Execution 可提出/執行候選，但不得用「工具有跑完／畫面有變」自我認證最終視覺成功。
- `SHARED_REAL_CAR_INTERFACE`：USER GOAL、PROTECTED_STATE、CURRENT_TASK_BINDING_PACKET、delta、literal/object activation、post-result evidence packet。這些是跨兩 owner 的共用 contract，不把 fact truth 或 GLOBAL effect authorization 吸收到 REAL_CAR。
- 最終 closure 仍是 `EXECUTION_RESULT → VISUAL_JUDGE_EVIDENCE → GLOBAL_CROSS_DOMAIN/CLOSURE`；`EXECUTOR_SELF_CERTIFICATION = FORBIDDEN`。

### Typed Visual→Execution normal form｜先定義成品，再證明怎麼做
REAL_CAR live handoff 收斂成兩個 typed objects；下方既有細節只負責填欄與驗證，不再讓長 prose 直接成為 execution language。

**`PRODUCT_VISUAL_SPEC`（Visual authority）：**
`TASK/REQUIREMENT_IDS / IDENTITY_TARGET / CONDITION_VITALITY_TARGET / SOURCE_REFERENCE_ROLES / VIEW_FREEDOM_OR_LOCK / SURFACE_VISUAL_MODE / COMPOSITION_TARGET / SCENE_BACKGROUND_TARGET / LIGHT_EDGE_SEPARATION_TARGET / MATERIAL_GLASS_REFLECTION_TARGET / LITERAL_ROLE_TARGET / DELIVERY_TARGET / PROTECTED_STATE / NET_UPLIFT_CRITERIA`。

**`EXECUTION_CAPABILITY_PROFILE`（Execution authority）：**
`ROUTE_FAMILY + MODEL/TOOL_REVISION / IMAGE_REFERENCE_CONDITIONING / STRUCTURAL_CONDITIONING / NOVEL_VIEW_CONTROL / CONDITION_TRACE_FIDELITY / SCENE_LIGHT_RECOMPUTE / LOCAL_MASKING / DETERMINISTIC_FRAME_TRANSFORM / DETERMINISTIC_LITERAL_OVERLAY / DELIVERY_TRANSFORM / ISOLATION_LEVEL / MATCHING_SCOPE_EVIDENCE`。

### Observed capability status｜穩定規則與會變動的工具能力分離
本 Canonical 只定義「一個 route 必須具備什麼能力、什麼 evidence 才能合法化」；目前平台/模型/工具實際 exposed/callable 的能力與 matching-scope evidence 寫入 `/Runtime/REAL_CAR/CAPABILITY_STATUS_CURRENT.md`，作為 Execution owner 的**可重建 observed-status read model**，不成為新的 authority。

固定：
`REAL_CAR_POLICY_REQUIREMENT → FETCH CURRENT CAPABILITY STATUS → OBSERVED_TOOL/MODEL_REVISION + EVIDENCE_SCOPE/FRESHNESS → EXECUTION_CAPABILITY_PROFILE → LEGALIZATION`。

- status row 至少綁 `ROUTE_FAMILY / TOOL_OR_MODEL_REVISION / OBSERVED_AT / EXPOSED_NOW / CALLABLE_NOW / CAPABILITY_DIMENSIONS / MATCHING_SCOPE_EVIDENCE / NEGATIVE_EVIDENCE / ISOLATION_LEVEL / FRESHNESS_OR_INVALIDATION_EVENTS / STATUS`。
- `OBSERVED_TOOL/MODEL_REVISION` 與 current route 不一致、工具 surface 改版、或 contradicted by fresh evidence 時，舊 capability PASS 自動 stale；不得因 Canonical 曾寫「支援」就沿用。
- route capability finding、單次 pilot stability、當前平台限制優先更新 status/evidence；只有「如何判斷能力」的穩定方法才留 Canonical。
- status 不得替 Visual 決定美學，也不得替 GLOBAL 授權 side effect；它只回答 Execution 的 current capability truth。

`CAPABILITY_POLICY != CAPABILITY_STATUS`。
`STALE_ROUTE_EVIDENCE != CALLABLE_CAPABILITY`。

唯一 lowering：
`PRODUCT_VISUAL_SPEC → EFFECT_REQUIREMENTS → EXECUTION_CAPABILITY_PROFILE → LEGAL_EXECUTION_PLAN → RESULT → VISUAL_AUDIT`。

固定：
- Visual 不把某 execution method 升格成 aesthetic truth；Execution 不把 tool completion 升格成 visual PASS。
- 母圖角度、背景、輪廓光、使用痕跡等 requirement 都先進 `PRODUCT_VISUAL_SPEC`；route 能力只在 profile 中回答「能不能、控制到哪裡」。
- 若 precise output 可由 deterministic adapter 完成，從 generative effect 中拆出；不得用 prompt 承擔 exact literal/size。
- 下方 `CURRENT_TASK_BINDING_PACKET / REAL_CAR_RENDER_PACKET / effect graph` 等 existing structures 視為這兩個 typed object 的 compile/egress detail，不建立平行 semantic authority。

## 1. Only goal
把使用者的實車圖片做成「仍可信地是同一台車、第一眼真實、3D合理、比原圖更好、能服務銷售」的成品。

`USER GOAL → VISUAL TARGET → BEST AVAILABLE EXECUTION → HUMAN-EYE QA → DELIVERY`

不得把 route ideology、metadata、pixel equality 或歷史實驗流程升成最終目的。

## 2. Default production mode
預設：`IDENTITY_PRESERVING_VISUAL_PRODUCTION`

要求：
- 同一台實車 identity 必須可信。
- 車型、主要比例、stance、燈具、輪圈、關鍵 trim / 配備不可被明顯改成另一台。
- 不做會誤導買家的重大車況、配備或外觀事實變造。
- 最終畫面第一眼真實、3D一致、自然、可用，並相對 source baseline 有實質改善。

原始像素 = reality / quality anchor，**不是永久 pixel lock**。
生成本身不是視覺 fail；是否接受由最終 identity + visual nonregression 決定。

只有使用者當輪明確要求「原始像素不可改、鑑定級 source preservation、真正 source-pixel cutout」時，才切換 `STRICT_SOURCE_PRESERVING`。

### 2A. Source vehicle condition-trace preservation
REAL_CAR 預設必須把來源照片中屬於**實車真實狀態**的使用／車況痕跡視為 protected state，而不是自動美容項。

固定解析：
`SOURCE_VISIBLE_MARK → VEHICLE_CONDITION_TRACE? → CURRENT_USER/VERIFIED_OVERRIDE? → PRESERVE | AUTHORIZED_REPAIR | UNKNOWN_KEEP_SOURCE_FAITHFUL`

- 預設保留可辨識的真實使用痕跡，例如：細刮痕、石擊、漆面磨耗／老化、橘皮或局部質感差異、小凹痕、輪圈刮痕、飾板磨損、座椅／方向盤／按鍵等內裝磨耗。
- 不得因「更漂亮、像新車、畫面乾淨」而自行把上述痕跡磨皮、補漆、拋光消失、重建成新品表面，或以生成式重畫改掉真實車況。
- `IDENTITY_PRESERVING` 不只包含車型／幾何，也包含會影響買家對實車狀態認知的 condition traces；候選若把可見使用痕跡無授權消除，標記 `CONDITION_TRACE_ERASURE / VEHICLE_TRUTH_REGRESSION`。
- 只有 current user 明確要求修復／美容某項，或有 current verified condition 證明該痕跡已實際處理（例如已重新烤漆、已換新零件），才可把該項列入 `AUTHORIZED_CONDITION_REPAIR_DELTA`；授權只限指定項目，不得擴張成整車自動翻新。
- 若無法判斷某個視覺記號是實際車況、灰塵、反射、壓縮雜訊或拍攝 artifact，不得自行升格成「瑕疵」或「已修復」；預設維持 source-faithful appearance，必要時標 `UNKNOWN_CONDITION_MARK`。
- 光影、曝光、色溫或背景調整可以改變痕跡的可見程度，但不得刻意利用這些調整把已知車況痕跡隱藏到足以誤導買家。

Precall protected-state 必須包含：
`SAME_REAL_CAR_IDENTITY + SOURCE_CONDITION_TRACES + UNAUTHORIZED_REPAIR_EXCLUSION`。

Authority precedence：
`CURRENT_USER_EXPLICIT_REPAIR/VERIFIED_CURRENT_CONDITION > SOURCE_VISIBLE_CONDITION_EVIDENCE > AESTHETIC_POLISH_DEFAULT`。

### 2B. Reference-guided used-car vitality generation｜母圖傳遞真實性，不鎖死角度
REAL_CAR 對使用者提供的母圖／來源照片集合，預設角色是 `REALITY + IDENTITY + CONDITION + MATERIAL RESPONSE REFERENCE`，不是 `VIEWPOINT_LOCK`、不是「只能原角度換背景」，也不是永久 source-pixel edit target。

固定解析：
`SOURCE_REFERENCE_SET → REFERENCE_ROLE_MAP → IDENTITY_ANCHORS + CONDITION_TRACE_SIGNATURES + MATERIAL/LIGHT_RESPONSE_CUES + VIEW_EVIDENCE → PRODUCT_VISUAL_SPEC → CURRENT_VIEW/SCENE TARGET`。

**Reference role contract：**
- 母圖提供「這台實車是誰、實際用過的樣子、材質怎麼反光、哪些使用痕跡是真實存在、哪些 identity component 可被確認」；不得因 reference conditioning 而把 source camera pose 自動升成 hard preserve。
- `SOURCE_VIEW_EVIDENCE != VIEWPOINT_LOCK`。若 current task 目標是生成不同角度／不同背景，Visual 可建立新的 `HERO_VIEW_BAND / VIEW_CHANGE_TARGET / SCENE_TARGET`；Execution 只需誠實標示 route 的 viewpoint / identity / condition controllability，不得因「保同車」就退回固定母圖角度。
- 反之，若 current user 明確要求保原角度、同構圖或 strict source edit，才把 viewpoint/composition 升成 protected state。
- 多張母圖不是讓模型平均成一台『綜合車』；各 reference 依可見 component / condition / material evidence 分工，`multi-view corroboration > visual averaging`。

**Used-car vitality / condition truth：**
- 使用痕跡是實車生命力與可信度的一部分，不是預設要消除的 cosmetic defect。生成新的背景或視角時，應保留「對應材質／對應區域的使用狀態特徵」；不得把整車自動翻新成無痕新品。
- 建立 task-local `CONDITION_TRACE_SIGNATURES`：至少可記錄 `TRACE_ID / SOURCE_VIEW / VEHICLE_REGION / MATERIAL / TRACE_CLASS / SCALE / SEVERITY_BAND / VISIBILITY_CONFIDENCE / VIEW_DEPENDENCE`。它是 condition-truth projection，不是要求把某道刮痕以假精確座標貼到所有新視角。
- 新視角只需在該區域可見且幾何合理時保留相符的使用狀態；原本不可見的新表面不得憑空發明磨損。`TRACE_NOT_VISIBLE_IN_TARGET_VIEW != TRACE_ERASURE`。
- 允許整體更乾淨、更有銷售完成度，但改善必須來自背景、構圖、光影、主體分離、色階與局部整理；不得以消除真實使用痕跡換取『完美商品感』。
- Visual 成功目標固定是 `REAL USED-CAR VITALITY = CONDITION TRUTH + MATERIAL LIFE + NATURAL IMPERFECTION + PRODUCT SALIENCE`；不是 showroom-CG perfection。

**View freedom with fidelity：**
- `NOVEL_VIEW / DIFFERENT_BACKGROUND` 是合法的 visual target class；不得因 source 角度不同而自動降級成「只能換背景」。
- 但 novel view 屬較高風險：必須以 `SOURCE_INSTANCE_ANCHOR_SET + CONDITION_TRACE_SIGNATURES + DISTINCTIVE_COMPONENT_PRIORITY` 驗收 identity / condition；route 沒有精準 camera control 時標 `SEMANTIC_VIEW_CONTROL / UNPROVEN`，不能把 observed 角度變化冒充精準相機控制。
- 若 current route 支援 image-reference conditioning、structural conditioning、multi-reference guidance 或 masked/local edit，Execution 可依 task delta 組合；若不支援則不得在 Canonical 中虛構。`REFERENCE_CONDITIONING_DESIRED != CALLABLE_CAPABILITY`。

**Rim/edge separation across new scene/view：**
- 輪廓光不是 source pixels，也不是固定亮邊 recipe；它是 `PRODUCT_EDGE_SEPARATION / FORM_READABILITY` 的 outcome。當背景或角度改變時，必須依**目標場景**重新求解，而不是機械複製母圖原光。
- 固定 coupled chain：`TARGET_SCENE_LIGHT_FIELD → TARGET_CAMERA/GEOMETRY → VEHICLE_CURVATURE + MATERIAL RESPONSE → EDGE/TONAL SEPARATION → GLASS/REFLECTION → CONTACT/CAST SHADOW → NEAR-FIELD COUPLING`。
- 若新背景的自然對比已足夠，`NO_EXTRA_RIM` 可 PASS；若需要補分離，僅在幾何／材質／光源方向合理處增加局部 shaping。禁止 halo、outer glow、全車描邊、把白車漂白、把深色玻璃塗成死黑。
- 背景生成的成功條件之一就是能支持主車的 edge separation；若背景明暗／色溫／高亮物件讓主車輪廓消失，應先重算 scene/background/light target，而不是只把車硬加亮。

**Generic production mode for different vehicles：**
每次 source 車不同時，重新建立 task-local profile；不得把 Sienta/A250/Altis 等個案角度、磨損、輪廓強度、背景 recipe 升成通用模板。通用的是解析流程：
`SOURCE REFERENCES → VEHICLE/MODEL PROFILE → CONDITION/VITALITY PROFILE → VIEW/SCENE TARGET → LIGHT/EDGE TARGET → EFFECT LEGALIZATION → GENERATION/LOCAL OPS → DELIVERY → VISUAL AUDIT`。

### 2C. First-run adaptive product-image bundle｜一次正式出圖 = 內部閉環，不等於一次生成呼叫
當 current task 是對外商品車圖片（FB 商店／粉專、輪播首圖、廣告 Hero、一般公開庫存圖）且 current user 未另行覆寫時，REAL_CAR 預設編譯一個 **task-local `PRODUCT_IMAGE_BUNDLE`**。它只是一組既有 requirement 的預設 activation / orchestration view，不是新 owner、不是第五個 runtime object、不是固定美術模板。

目標是：使用者第一次下達正式「出圖」時，系統在同一個 workflow run 內先完成必要分析、合法化、執行與驗收，再只交付通過的 final artifact；不得把「第一次」誤解成「只能呼叫一次 generator」。

固定主鏈：
`CURRENT_TASK_SPEC → SOURCE/FACT BIND → ACQUISITION_ENTRY_BRIEF(if market-optimized) → VEHICLE_VISUAL_PROFILE → PRODUCT_IMAGE_BUNDLE → EXECUTION_DAG/LEGALIZATION → STAGED EFFECTS → PRODUCT_IMAGE_CHECKSET → FINAL DELIVERY`。

`PRODUCT_IMAGE_BUNDLE` 只聚合下列既有 requirement role，不複製其完整規則：
- `SAME_REAL_CAR + CONDITION_TRUTH = HARD`：identity、主要幾何、真實使用痕跡與未授權美容維持 protected。
- `WATERMARK = REQUIRED`：對外商品圖預設啟用 current authorized watermark literal / role；exact literal 仍依 §6A.1 與 §4A0.0 走合法 route。`EXACT_LITERAL` 只允許 current-authorized characters/tokens；電話 icon、斜線、加號、分隔點、裝飾符號等未列入 literal/glyph allowlist 的內容一律不得由 generator/adapter 自行補入。
- `PRIMARY_PLATE_COVER = REQUIRED_IF_VISIBLE`：對外 exterior 圖若主車正式車牌可讀／可辨識，預設自動 activation §6B `BLACK_CLOTH_SLEEVE`；主車牌不可見時不虛構遮牌物件，current user 可明確 override。此 activation 是 required node，不是風格建議；若 route 無法完成或缺 receipt，標 `EXECUTION_PATH_OMISSION / BLOCK_FINAL_PROMOTION`，不得以裸露可讀車牌的成品補交。
- `DELIVERY = HARD`：依 current delivery surface 套用 final size/format contract；raw generator size 不等於 final delivery。
- `VEHICLE_VISUAL_PROFILE = REQUIRED`：hero view、camera/perspective、subject occupancy、grounding、background ranking、edge separation、watermark visibility 由 current source/model/material/delivery role 自動求解，禁止固定 cookbook。
- `ACQUISITION_CONTEXT = BOUNDED`：若任務要宣稱市場／買家適配，使用現行 `ACQUISITION_ENTRY_BRIEF`；沒有該 brief 時仍可做純 visual-quality production，但不得冒充 market-optimized claim。
- `SURFACE_VISUAL_MODE = REQUIRED_FOR_PUBLIC_PRODUCT_HERO`：對外中古車庫存／商品首圖預設編譯 `USED_CAR_INVENTORY_HERO`；只有 current user 或明確 campaign task 要求品牌／生活形象素材時才切換 `BRAND_LIFESTYLE_CAMPAIGN`。這只是既有 acquisition/composition/salience requirement 的 task-local mode，不是新 owner 或固定美術模板。

**First-run selection policy：**
- 先從 current sources 中選最有機會達成 HERO / same-car / condition truth 的 source-backed view；只有存在正向 value hypothesis 且 route capability 足夠時才升級 novel view。
- 背景先依 `BACKGROUND_FAMILY_RANKING` + market/use context 建 candidate，再過 `SCENE_FIT_GATE + PHYSICAL_FIT_GATE + BACKGROUND_COMPETITION_CAP`；不得因某車款過去常用某背景就直接套用。
- `PRODUCT_EDGE_SEPARATION` 以 form readability 為目標；背景天然分離足夠時允許 `NO_EXTRA_RIM`，不足時才做最小局部 shaping，禁止 halo / outer glow。
- 若 advanced view/background/photometric node 無法合法化，但 hard requirements 可由更保守 source-backed plan 完成，Execution 必須 **re-lower 到較低風險合法方案**（例如保留來源視角／背景 + 合法 local/deterministic effects），而不是 whole-frame broad fallback。
- 若任一 active HARD op 仍無 legal route，沿用 §4A0.E `HARD_OP_ADMISSION=BLOCK`；不得為了「第一次一定要有圖」偷降級。

**`PRODUCT_IMAGE_CHECKSET`（promotion blocking）：**
`IDENTITY / CONDITION_TRUTH / PLATE_COVER(if activated) / WATERMARK / COMPOSITION_HERO / BACKGROUND_COMPETITION+PHYSICAL_FIT / MATERIAL_GLASS_DEPTH / EDGE_SEPARATION / DELIVERY / ACQUISITION_SUPPORT(if claimed)`。
- HARD check fail → block final promotion。
- 只有 downstream/local check fail 時，只 rerun / re-lower affected legal subgraph；已 PASS 的 source identity / hero / background 不因小項失敗自動 whole-frame 重抽。
- 第一個對使用者可見的 production deliverable 應是通過 checkset 的 final artifact；探索性 raw output 只能是 `NON_PRODUCTION_EVIDENCE`。平台若強制先顯示 raw generator result，必須誠實標示平台限制，不得把 raw result 說成 final PASS。

**Anti-bloat / long-term stability：**
- `PRODUCT_IMAGE_BUNDLE` 只保存穩定 activation semantics；角度、背景、輪廓光強度、磨損位置、單次 prompt 都是 task-local resolved values，不寫入 Canonical。
- 學習只更新 §3.5G 的 bounded prior / accepted-rejected evidence；單張成功、單一車款、一次生成差異不得建立新的 permanent rule。
- 同一 failure 若 existing requirement / gate 已能表達，優先修 execution consumption / capability / verifier；禁止再新增同義規則。
- route/tool capability 只寫 observed status/evidence，不寫死在 Canonical；工具改版由 capability freshness 失效機制重新判定。


**Bundle-to-runtime boundary｜Bundle 只描述 desired state，不具有工具呼叫權：**
- `PRODUCT_IMAGE_BUNDLE` 完成後只能編譯 `EXECUTION_DAG`；不得直接成為 image/render tool input，也不得由 adapter 把 bundle 重新壓縮成一個 broad prompt。
- `FIRST_RUN_COMPLETE` 的定義是「同一 workflow run 內所有 required nodes 都實際執行、驗證並 commit」，不是「第一個 image tool call 已經同時看起來有做到很多項」。
- 若 current route 無法合法完成 advanced background/view/light node，但 source-backed conservative lane 可完成 HARD obligations，優先保留來源實車與真實痕跡，再做可控 reframe / local object / exact literal / delivery；不得用整圖重畫換取流程表面完整。
- 生成式能力可用來產生**隔離資產**（例如不含主車的背景候選、黑布材質/overlay asset），前提是該 node 的 write envelope 不包含 protected vehicle artifact；最終 placement/composite 仍由 matching callable stage 執行並驗證。

**Production render-content admission｜控制／驗證資料不得取得畫面渲染權：**
REAL_CAR 在 production image call 前必須把「用來控制模型的內容」和「允許出現在成品裡的內容」拆開；不得因同一段自然語言同時包含視覺目標與驗收說明，就把後者一起變成圖上文字、箭頭、標註或資訊框。

固定分流：
`CURRENT_TASK_BINDING_PACKET → CONTROL_METADATA + VALIDATION_METADATA + VISUAL_SCENE_CONTENT + RENDERABLE_LITERAL_SET → RENDER_CONTENT_MANIFEST → PRODUCTION_IMAGE_CALL → RENDER_LEAK_AUDIT`。

- `CONTROL_METADATA`：composition target、subject hierarchy、background competition、edge separation、scene rationale、light/material target、route/control instructions、research-derived mechanism 等，只能影響視覺控制，**不得作為可讀內容渲染**。
- `VALIDATION_METADATA`：PASS/FAIL criteria、checklist、test goal、experiment label、百分比/門檻候選、研究 finding、比較說明、callout rationale、witness/diagnostic text 等，只供驗收，**不得作為可讀內容渲染**。
- `VISUAL_SCENE_CONTENT`：車、背景、人物/生活痕跡、光影、遮牌等真正畫面物件；只有 current task 已 activation/authorized 的 object 才可出現。
- `RENDERABLE_LITERAL_SET`：唯一可新增可讀文字來源。預設只包含 current task 已授權且角色/載體已綁定的 literal；若 `VISUAL_TEXT_AUTHORITY=NONE`，不得因研究／驗證文字存在而擴張。

`RENDER_CONTENT_MANIFEST` 至少記錄：
`SURFACE_ROLE / ALLOWED_VISIBLE_OBJECT_ROLES / ALLOWED_LITERAL_TOKENS / FORBIDDEN_META_CONTENT_CLASSES / SOURCE_AUTHORITY / TASK_REVISION`。

Precall hard policy：
- production payload 不得直接攜帶 raw research note、validation prose、checklist、rule name、percentage target、diagram/callout wording、explanatory heading、test instruction 或「本圖落地重點」等 meta-language，除非 current user 明確把本次 surface 改成 `INFOGRAPHIC/EXPLAINER` 並授權對應 literal。
- 若 adapter 只能把整包 desired state 重新壓成 broad natural-language prompt，且無法證明上述 meta-content 已被裁切，標 `RENDER_CONTENT_ADMISSION_UNPROVEN / BLOCK_PRODUCTION_PROMOTION`；可做 exploratory evidence，但不得冒充正式商品圖。
- 視覺目標必須先被 lowering 成 scene/object/composition/light/material 等非文字控制；不能把「車體主導、背景退讓、自然生活感」原句直接當成要畫進成品的說明。
- exact watermark/dealer literal 仍走既有 `AUTHORIZED_EMBEDDED_LITERALS` / §6 literal role contract；本 gate 不建立新的文字 authority。

Post-result fail-close：
- 未授權出現標題、條列、check box、百分比、箭頭、callout、規則名稱、教學框、驗證文字、研究說明或其他「解釋這張圖怎麼做」的可讀內容 → `CONTROL_METADATA_RENDER_LEAK / NON_PRODUCTION_ARTIFACT`。
- 此類輸出不得升為 winner、baseline、parent 或 behavior PASS evidence；只能作 negative execution evidence，修正 egress/adapter 後重新做乾淨成品驗證。
- `CONTENT_CORRECT_BUT_ROLE_WRONG = FAIL`；即使說明文字本身完全正確，也不能以正確性抵銷渲染角色錯誤。

`CONTROL_METADATA != RENDERABLE_CONTENT`。
`VALIDATION_CRITERIA != ON_IMAGE_COPY`。
`RESEARCH_FINDING != INFOGRAPHIC_AUTHORITY`。

## 3. Visual judgment order
`FIRST_GLANCE_SUBJECT_HIERARCHY → FIRST_GLANCE_REALISM_AND_SAME_CAR → 3D_WORLD_CONSISTENCY → IMPROVEMENT_VS_SOURCE → SALES_VALUE → EXACT_LITERALS/LOCAL_DETAILS`

第一眼先判斷：**觀者是否先看到車，而不是先看到招牌、建築、燈光、背景車或場景效果。** 若背景/店招取得更高 salience，即使畫面漂亮也不得判 Hero PASS。

metadata 不得排在人眼判斷之前。

### 3.1 Same-real-car major-component audit completeness
`SAME_REAL_CAR_IDENTITY` 不得只用單一總標籤結束。當 source 足以比較時，Human/Visual audit 至少明確掃描：
`SILHOUETTE/PROPORTION + STANCE + WHEEL_IDENTITY + LIGHT_IDENTITY + KEY_TRIM/EXTERIOR_PARTS + BADGE/EQUIPMENT_TRUTH + BODY/REFLECTION STRUCTURE`。

- `WHEEL_IDENTITY` 至少比較 spoke pattern、粗細/間距、finish/contrast、hub/spoke proportion、apparent wheel/tire proportion。
- 若輪圈、燈具、尾翼/擾流、飾條、徽章或其他 major visible component 明顯與 source 不同，必須 explicit report；不得因整體已判 identity FAIL 就把 major-component defect 埋在一句總結裡。
- 當輪正在測招牌、門牌、背景、刮痕等特定 delta，也不能因此跳過完整 identity sweep；`DELTA_FIXATION → MAJOR_COMPONENT_AUDIT_OMISSION` 視為 audit defect。
- 這是 judge completeness，不代表 current route 已具備控制這些 component 的能力。



### 3.2 Context-aware preservation / modification contract｜本次該改什麼、該保什麼動態分開

Visual Judge 不再用固定的「改得越多越好」或「保留越多越好」評分。每次驗收必須由 current task 先解析：
`CURRENT_DELTA + PROTECTED_STATE + EXPECTED_MATERIAL_UPLIFT → REQUIRED_MODIFICATION / REQUIRED_PRESERVATION / NON_TARGET_REGRESSION_BUDGET / NET_UPLIFT_GATE`。

固定判斷：
- `REQUIRED_MODIFICATION`：本次明確要改的內容是否真的改到足夠程度；完全沒做到 delta 不能因「同車很像」就 PASS。
- `REQUIRED_PRESERVATION`：非目標與 truth-sensitive identity 是否維持；不能因畫面變漂亮就抵銷輪圈、燈具、比例、車況等 material regression。
- `NON_TARGET_REGRESSION`：本次不應受影響的區域／屬性是否被 collateral redraw。
- `NET_UPLIFT`：只有 intended improvement 大於 preservation/regression cost，才有 promotion 資格。

不同 task 可有不同 preservation/modification 權重，但權重必須來自 current delta / protected state，不得由生成結果事後倒推。

### 3.3 Source-instance anchor set｜多視角同時提供 identity / condition / material evidence，不把母圖變成角度鎖

同一台實車若有多張來源照片，建立 task-local `SOURCE_INSTANCE_ANCHOR_SET` 作 Visual Judge 的 corroborating evidence。

至少記錄：
`ANCHOR_VIEW_ID / VIEWPOINT / VISIBLE_COMPONENTS / SOURCE_AUTHORITY / CONDITION_TRACE_VISIBILITY / CONFIDENCE`。

規則：
- current execution 仍有一個明確 primary source/reference；其他視角是 identity/condition corroboration，除非實際 route 明確可消費多視角，否則不得宣稱它們是 execution control。
- primary source 的 camera pose 預設只代表 evidence provenance，不自動成為生成目標；當 current task 要 novel view，`TARGET_VIEW` 由 PRODUCT_VISUAL_SPEC 建立，source views 轉為 cross-view identity / condition / material witnesses。
- 輪圈、頭尾燈、spoiler、bumper、trim、車身比例、車況痕跡等，以「哪個來源視角真的看得到」為 evidence boundary；看不到就 `UNKNOWN`，不從其他車／常識補造。
- multi-view disagreement 先查 source/time/condition difference；不得投票合成一台不存在的『平均車』。
- 這一層主要降低 Visual Judge 的 source-instance 誤判風險，不改變 Execution capability boundary。

### 3.4 Composition geometry / spatial-control contract｜構圖、相對位置、角度分層控制

使用者對「車太小、衝擊感不夠、離下緣太遠、前方留白太多、太置中、角度不夠有力量」等回饋，先轉成可觀測的 composition delta；不得把所有回饋都模糊成「再生成一張更好看」。

固定解析：
`USER_COMPOSITION_FEEDBACK → STRUCTURAL_DIAGNOSIS → LEAST_INVASIVE_ACTION_CLASS → COMPOSITION_TARGET → ROUTE_SPATIAL_CONTROL_CHECK → EXECUTE | HOLD/CAPABILITY_BOUNDARY → COMPOSITION_QA`。

#### A. Action hierarchy｜先用最小幾何改動，不把 shift/zoom 偷換成 view change
依風險由低到高區分：
1. `REFRAME_SHIFT/CROP`：移動裁切窗口、調整上下左右留白；不改車與場景的物理相對位置。
2. `UNIFORM_ZOOM/FRAME_SCALE`：等比例放大或縮小整體 framing，使主車在畫面中的佔比改變；不得用非等比拉伸改車身比例。
3. `SUBJECT_RELATIVE_SHIFT_SCALE`：讓主車相對背景真正平移／等比例縮放；這已是 object relocation，必須同步重算 local effects envelope。
4. `VIEW_CHANGE/PERSPECTIVE_CHANGE`：改相機高度、左右/前後位置、俯仰、繞車角度、相機距離或 focal-perspective；屬高風險，不能把成功的 shift/zoom 當成 view-change capability proof。

優先原則：能用較低風險 action 達成同一 visible goal，就不得自動升級到高風險 action。

#### B. Feedback grounding｜「更有衝擊感」不是單一參數
`IMPACT / HERO_PROMINENCE` 至少拆查：
- `SUBJECT_FRAME_OCCUPANCY`：主車佔畫面大小；
- `VERTICAL_ANCHOR / BOTTOM_CLEARANCE`：輪胎最低點、接地陰影與下緣的張力；
- `LATERAL_POSITION`：偏左／偏右／置中是否服務車頭朝向與視線流；
- `FRONT_SPACE / REAR_SPACE / TOP_SPACE`：方向性留白與無效空間；
- `GROUND_CONTACT + HORIZON_RELATION`：車是否穩定落在地面與場景透視中；
- `PERSPECTIVE_EMPHASIS`：近側車頭／輪圈是否因相機距離、廣角或低機位被強化；
- `BACKGROUND_COMPETITION`：背景高 salience 是否削弱主車；
- `THUMBNAIL_READABILITY`：縮圖時主車是否仍快速、完整、清楚。

`IMPACT_LOW != AUTO_SCALE_UP`。若使用者只說「衝擊感不夠」，Visual Judge 先依上述項目定位最可能結構原因；若使用者已明確說「車再靠下／前方留白減少／車再大一點」，該具體 delta 直接取得 current task authority，不再改寫成其他構圖偏好。

#### C. Composition target｜使用相對 baseline 的可驗證目標，不建立固定萬用座標
`COMPOSITION_TARGET` 以 current source/baseline 為 reference，至少可包含：
`ACTION_CLASS / SUBJECT_SCALE_DELTA / SUBJECT_CENTER_DELTA / BOTTOM_CLEARANCE_DELTA / FRONT_SPACE_DELTA / REAR_SPACE_DELTA / TOP_SPACE_DELTA / GROUND_CONTACT_ANCHOR / VIEWPOINT_STATE / CAMERA_HEIGHT_STATE / PERSPECTIVE_STATE / CROP_SAFETY`。

規則：
- 預設記錄「相對 baseline 增加／減少／維持」與 small/moderate/material 等 bounded delta；除非 route 真的暴露 pixel/box/point control，否則不得用假精確座標冒充 execution control。
- 不設全域固定 subject-area%、固定下緣 px、固定中心點或固定三分線為唯一最佳；不同車身、來源角度、用途與畫幅可以有不同 optimum。
- `CROP_SAFETY` 必須保護車頭、車尾、車頂、後視鏡、四輪、輪胎最低點、接地陰影與必要方向性留白；「靠近下緣」不等於貼邊或裁輪。
- `FRONT_SPACE` 要和車頭朝向／視覺動勢一起判；減少留白可以增加張力，但不得壓縮到讓車頭看似撞框或失去自然呼吸空間。

#### D. Viewpoint / focal-perspective boundary｜角度改變屬真正 3D delta
當使用者要求「更低機位、車頭更有壓迫感、近側輪圈更有力量、換成另一個 3/4 角度、視角更扁平／更壓縮」時，分類為 `VIEW_CHANGE/PERSPECTIVE_CHANGE`，不得只用 2D crop/scale 宣稱已達成。

`VIEW_CHANGE_TARGET` 可描述：
`CAMERA_HEIGHT / CAMERA_AZIMUTH_OR_ORBIT / CAMERA_DISTANCE / PITCH_YAW / FOCAL_PERSPECTIVE_CLASS / NEAR_SIDE_EMPHASIS / HORIZON_STATE`。

- 短 focal / 近距離可增加近側尺寸差與空間張力，也更容易扭曲保桿、輪圈、車身比例；長 focal / 較遠距離傾向壓縮深度。這些只作視覺機制與 target 描述，不得假裝 current route 暴露真實鏡頭 mm 控制。
- view change 必須使用 `SOURCE_INSTANCE_ANCHOR_SET` 做輪圈、燈具、車身比例、stance、trim 等跨視角 identity regression。
- current route 若只能接受語意提示、不能提供 auditable spatial/viewpoint control，標 `SPATIAL_CONTROL_LEVEL=SEMANTIC_ONLY/UNPROVEN`；輸出角度變了只能算 observed result，不能宣稱精準 camera control 已學會。

#### E. Relocation / harmonization coupling｜車位置改了，周圍物理關係也要跟著改
只要 action 超過單純 `REFRAME_SHIFT/CROP`，並改變車相對場景的位置／尺度，固定重算：
`TIRE_GROUND_CONTACT / CONTACT+CAST_SHADOW / LOWER_BODY+GLASS_REFLECTION / LOCAL_OCCLUSION_ORDER / GROUND_TEXTURE_SCALE / NEAR_FIELD_LIGHT_COLOR / BACKGROUND_DISOCCLUSION`。

車本身 identity 是 protected state；環境效果可為了新的位置合理重建。若車移了但影子、反射、接地或被遮住/露出的背景仍停在舊位置，標 `PLACEMENT_HARMONIZATION_FAIL`。

#### F. Visual Judge composition QA｜主體更大不一定構圖更好
Composition PASS 至少同時檢查：
`INTENDED_DELTA_ACHIEVED + VEHICLE_COMPLETE + SUBJECT_HIERARCHY + SURFACE_VISUAL_MODE_FIT + GLOBAL_RELATIONSHIPS + GROUNDING + PERSPECTIVE_PLAUSIBILITY + IDENTITY_NONREGRESSION + THUMBNAIL_FIRST_GLANCE + NET_UPLIFT_VS_BASELINE`。

不得只因車面積變大就 PASS；若下緣太緊、方向性留白錯、透視變形、接地/陰影破裂、背景關係失衡或同車 identity 退化，仍 FAIL。

### 3.5 Adaptive vehicle / model product-salience policy｜依車型、車款與來源幾何自動形成任務視覺策略

REAL_CAR 不使用一套固定 hero 構圖套所有車，也不建立「某車款固定角度／固定下緣 px／固定輪廓光強度」的 cookbook。Visual Judge 先建立 task-local `VEHICLE_VISUAL_PROFILE`，再把 HERO、構圖、光影、背景與浮水印需求投影到 Execution。此 profile 是 bounded projection，不是新 owner、不是長期個案資料庫，也不能突破 SAME_REAL_CAR / condition truth / route capability。
母圖/source view 是 profile 的 reality evidence，不是 viewpoint ceiling；`HERO_VIEW_BAND` 可以相對 source 改變，只要 current task 需要、Visual 有正向 value hypothesis，且 Execution 對 novel-view identity/condition風險做 capability-legalized處理。

固定解析：
`SOURCE_INSTANCE_FEATURES + BODY_ARCHETYPE_PRIOR + MODEL_GEOMETRY_ADAPTATION + CURRENT_SOURCE_VIEW + COLOR/MATERIAL + DELIVERY_SURFACE + SURFACE_VISUAL_MODE + VISUAL_ENTRY_HYPOTHESIS(optional) → VEHICLE_VISUAL_PROFILE → PRODUCT_SALIENCE_TARGET → COMPOSITION/PHOTOMETRIC/BACKGROUND/WATERMARK PROJECTIONS → EFFECT LEGALIZATION`。

#### A. Hierarchical adaptation｜先有車身原型 prior，再依實際車款與來源修正
`VEHICLE_VISUAL_PROFILE` 至少依序消費：
1. `BODY_ARCHETYPE_PRIOR`：MPV/minivan、hatchback、sedan、coupe/sports、SUV/crossover、pickup/utility、wagon 等只提供初始 prior；
2. `MODEL/SOURCE_GEOMETRY`：實際 hood/cabin ratio、車高、軸距/前後懸、glasshouse、輪拱/輪胎、前後視覺圖形、stance、可見配備與特殊外觀；
3. `CURRENT_SOURCE_VIEW_EVIDENCE`：目前來源真的提供哪些角度、哪些 identity components 可被可靠觀察；
4. `COLOR/MATERIAL/LIGHT_CONTEXT`：車色、玻璃、亮/黑飾件、漆面反射與來源光場；
5. `DELIVERY/ACQUISITION_ROLE + SURFACE_VISUAL_MODE`：FB hero、輪播、一般庫存圖、封面等對縮圖可讀性與商品存在感的需求；同時區分 `USED_CAR_INVENTORY_HERO` 與使用者明確要求的 `BRAND_LIFESTYLE_CAMPAIGN`，不得只因畫面更 cinematic 就把商品主圖滑成品牌形象照。

原型 prior 只能作起點；當 current model/source geometry 與 archetype generic prior 不一致時，以 current source evidence 為準。單一案例不得升格成「所有同車款永遠同一角度」。

#### B. Profile outputs｜把「這台車怎麼最好看」變成可驗證的 bounded target
`VEHICLE_VISUAL_PROFILE` 至少可輸出：
`HERO_VIEW_BAND / CAMERA_HEIGHT_BAND / PERSPECTIVE_AGGRESSION_CAP / SUBJECT_FRAME_OCCUPANCY_BAND / BOTTOM_CLEARANCE_BAND / FRONT_REAR_TOP_SPACE_BAND / LATERAL_BIAS / GROUND_CONTACT_PRIORITY / DISTINCTIVE_COMPONENT_PRIORITY / PRODUCT_EDGE_SEPARATION_TARGET / BACKGROUND_FAMILY_RANKING / BACKGROUND_COMPETITION_CAP / WATERMARK_VISIBILITY_TARGET`。

- `HERO_VIEW_BAND` 是候選角度區間，不是假精確相機座標；優先選能同時呈現該車辨識特徵、比例、輪圈/燈具/車身姿態且有 current source evidence 的角度。
- `CAMERA_HEIGHT_BAND / PERSPECTIVE_AGGRESSION_CAP` 必須服從該車真實比例；不得為了 hero 感把 MPV/SUV/轎車/跑車都壓成同一低機位性能車模板。
- `BOTTOM_CLEARANCE_BAND` 由輪胎接地、車身高度、畫幅、crop safety 與縮圖張力共同決定；不是全車種固定下緣值。
- `SUBJECT_FRAME_OCCUPANCY_BAND` 以「第一眼商品存在感」為目標，但不得以裁車、壓框、非等比縮放或 view distortion 換取面積。
- 若 current source 已在 profile 的合適 view band 內，優先用 deterministic reframe/zoom/shift 做 hero 提升；不得無必要升級到 novel view。
- 若 profile 判斷需要 materially different view，但 current route 沒有 matching-scope same-car capability，標 `PROFILE_TARGET_CAPABILITY_BOUNDARY`，不得為了達成風格而犧牲 identity。

#### C. Product salience objective｜光、構圖、背景都服務商品，不服務「整張圖效果」本身
`PRODUCT_SALIENCE_TARGET` 固定優先：
`VEHICLE_FIRST_GLANCE_DOMINANCE + FORM_READABILITY + DISTINCTIVE_COMPONENT_READABILITY + MATERIAL_DEPTH + GROUNDING + THUMBNAIL_PRESENCE`。

任何 component 若只讓整張圖更 cinematic / 更漂亮，但讓車變小、變平、輪廓不清、車色髒、identity 退化或背景更搶，標 `SCENE_AESTHETIC_GAIN_WITH_PRODUCT_SALIENCE_LOSS / REJECT`。

#### C1. Used-car inventory hero boundary｜中古車商品主圖不是品牌形象廣告
對外中古車庫存／商品首圖（例如 FB 商店首圖、輪播首圖、一般公開 inventory hero）在 current user 未另行指定時，`SURFACE_VISUAL_MODE=USED_CAR_INVENTORY_HERO`。它和 `BRAND_LIFESTYLE_CAMPAIGN` 共用 same-car、truth、3D、material 等底層品質要求，但**視覺優化優先序不同**。

`USED_CAR_INVENTORY_HERO` 固定優先：
`REAL_UNIT_PRODUCT_PRESENCE → FIRST_GLANCE_VEHICLE_DOMINANCE → REALISM/TRUST → FORM+MATERIAL_READABILITY → USE_CONTEXT_SUPPORT → ATMOSPHERIC/CINEMATIC BEAUTY`。

固定判斷：
- `NEGATIVE_SPACE = FUNCTIONAL_BUDGET`，不是形象廣告式美感預設。留白只能服務 `CROP_SAFETY / DIRECTIONAL_BREATHING / PERSPECTIVE / AUTHORIZED_LITERAL_CARRIER / VISUAL_BALANCE`；若大量 top/side/foreground 空間沒有商品功能，並降低 `SUBJECT_FRAME_OCCUPANCY / THUMBNAIL_PRESENCE / FIRST_GLANCE_FIXATION`，標 `INVENTORY_HERO_NEGATIVE_SPACE_FAIL`。
- `SCENE_SUPPORT != SCENE_STORY_HERO`。場景可提供家庭、通勤、停車、戶外、交易信任等用途聯想，但觀者不應先閱讀完整環境敘事才注意到車；若建築、夕陽、樹景、人物活動、空間感或版面文字形成可獨立成立的第二主角，標 `BRAND_CAMPAIGN_DRIFT / SUBJECT_HIERARCHY_FAIL`。
- `CINEMATIC_LIGHT_ALLOWED != CINEMATIC_LOOK_REQUIRED`。golden hour、逆光、戲劇光線本身不禁用；只有當它提升車體 form/material separation 且仍像可信實拍、沒有讓氛圍比商品更重要時才有正向價值。`PRETTY/CINEMATIC` 不得抵銷商品佔比、真實感或主體層級退化。
- `HUMAN/LIFE_TRACE = CONTEXTUAL_SUPPORT`。人物、車流、生活痕跡只需足以讓時間／場所／用途顯得自然；不得為了「人感」硬加敘事人物，也不得把單次「白天公園太空」升成「公園必須有人／必須黃昏」的固定規則。
- 對 `USED_CAR_INVENTORY_HERO`，§5.1 的 `SCENE_FIT_GATE` 通過仍不等於可用；還必須過 `INVENTORY_PRODUCT_DOMINANCE_GATE = VEHICLE_FIRST + FUNCTIONAL_NEGATIVE_SPACE + BACKGROUND_COMPETITION_WITHIN_CAP + THUMBNAIL_PRODUCT_PRESENCE + NATURAL_SALES_PHOTO_FEEL`。
- `BRAND_LIFESTYLE_CAMPAIGN` 只有 current user 明確要求，或 task surface 本身就是品牌／形象 campaign 時才啟用；此模式可容許更大的敘事留白與環境情緒，但不得反向污染中古車 inventory hero 的預設。
- 不設固定車體佔比%、固定 crop、固定黃昏、固定人物數或固定背景複雜度；一律依 current vehicle/source/delivery role 做相對 baseline 的 bounded optimization。

#### D. Product-centric edge / rim separation｜輪廓分離只在商品需要的地方成立
`PRODUCT_EDGE_SEPARATION_TARGET` 不是「整台描一圈亮邊」，固定先判：
`LOCAL_VEHICLE_BACKGROUND_CONTRAST → BODY_CURVATURE/MATERIAL → SOURCE_LIGHT_DIRECTION → EDGE_SEPARATION_NEEDED? → LOCAL_SHAPING | NO_EXTRA_RIM`。

- 只有車身邊界在 current background 上失去辨識、玻璃/A柱/黑飾件互相糊在一起，或 body form 因 tonal merge 變平時，才啟用局部 shaping。
- 優先用背景明度差、車體表面反射流、negative fill、局部 tonal shaping 解決；最後才是薄弱且服從現場光源的 rim/edge highlight。
- 禁止 halo、outer glow、全景泛光、為了氛圍把非商品區域一起抬亮；`RIM_VISIBLE != PRODUCT_SEPARATION_PASS`。

#### E. Background profile ranking｜背景先依這台車排序，再過既有 scene/physical gate
`BACKGROUND_FAMILY_RANKING` 只提供 task-local candidate prior，至少評估：
`USE/OCCASION_FIT + VEHICLE_COLOR/LUMINANCE_SEPARATION + PERSPECTIVE_COMPATIBILITY + GROUNDING_OPPORTUNITY + REFLECTION/LIGHT_COMPATIBILITY + LINE/OBJECT_CLUTTER + READABLE_LITERAL_RISK + BUYER/SALES_CONTEXT`。

背景不能因「某車種通常配某場景」就直接通過；最終仍必須通過 §5.1 `SCENE_FIT_GATE + PHYSICAL_FIT_GATE`。反過來，§5.1 也不得每次從零猜背景而忽略 current `VEHICLE_VISUAL_PROFILE` 的 candidate ranking。

#### F. Human-visible watermark target｜浮水印依實際畫面自動調整能見度，不固定同一 opacity/size
`WATERMARK_VISIBILITY_TARGET` 至少包含：
`FINAL_SIZE_READABILITY / THUMBNAIL_READABILITY / CARRIER_CONTRAST / LOCAL_TEXTURE_COMPLEXITY / PERSPECTIVE_FIT / OCCLUSION_RISK / MAX_SALIENCE_RELATIVE_TO_VEHICLE`。

- 浮水印必須在 final delivery size 人眼可讀；若用途包含縮圖/手機瀏覽，另做 thumbnail readability check。
- 大小、明暗、透明度、必要的局部描邊/陰影與位置可依 carrier 自動調整；不得用一組固定 opacity 套所有車色與玻璃背景。
- 達到可讀後即停止增強；若浮水印成為第一眼焦點、破壞車身曲面或比車的辨識特徵更搶，標 `WATERMARK_OVER_SALIENCE`。
- carrier 太亂或對比不足時，先在**主車允許的玻璃/車身 carrier**內換位置或做最低必要 local contrast treatment；不得為了可讀遷移到背景、店招或四角。
- exact literal 仍優先走 deterministic literal route；visibility policy 只決定人眼呈現，不重新定義文字內容。

#### G. Adaptive learning｜學的是 bounded policy，不是背一張圖
Visual/Execution learning 對車型適配固定使用：
`ARCHETYPE_PRIOR → CURRENT_MODEL/SOURCE_FEATURES → TASK_LOCAL_PROFILE → CANDIDATE/PILOT → VISUAL+SALES_OUTCOME → ACCEPT/REJECT EVIDENCE → UPDATE_BOUNDED_PRIOR`。

- 只有 SAME_REAL_CAR、truth、3D/photometric 與 output contract 均無 material regression 的候選，才可提供正向 hero/composition/background/watermark 學習。
- 學習可更新「某類比例/視角/畫幅下哪些 band 較常成功」與 rejected set；不得從單一車、單張圖硬寫固定相機座標、固定下緣或固定背景。
- model-specific evidence 足夠時可形成較窄 prior，但仍須由 current source geometry/task 重新校正，歷史成功不自動取得 current task authority。
- 若目前 route 不提供可重複控制，只保留 judge/selection evidence，不把 output variance 升成 execution control。

## 3A0. Acquisition visual interface｜圖片是第一關 sibling，不是 Sales 技巧的附屬輸出
當 current task 是 FB 商店、輪播、廣告 Hero、影片封面／第一線 acquisition 素材，Visual/Execution 可以消費 Sales 產生的 current `ACQUISITION_ENTRY_BRIEF` 作為**市場定位輸入**；但完整 Sales/Human 對話技巧、信任處理、異議處理、next-step 不進入 Visual 決策鏈。

固定：
`ACQUISITION_ENTRY_BRIEF → VISUAL_ENTRY_HYPOTHESIS → COMPONENT_VALUE_GATE → EXECUTION → FIRST_GLANCE_AUDIT`

Visual 最低只消費：
`TARGET_BUYER / MARKET_REASON_TO_CARE / PRODUCT_PROOF_PRIORITY / PURCHASE_OR_USE_ANCHOR / VISUAL_ENTRY_JOB / CLAIM_LIMITS`。

邊界：
- 文案入口與圖片入口是同一 acquisition stage 的 sibling；Visual 不需要服從 copy wording，copy 也不能以文字策略支配視覺專業。
- Sales 決定「賣給誰、商品／市場為什麼值得看」；Visual 決定「如何讓這台車第一眼好看、可信、聚焦，並有利於該市場定位」。
- Visual 不得自行發明行情、客群心理、價格優勢、稀缺性或配備 claim；market/product truth 仍由 Library→Sales 提供。
- `VISUAL_ENTRY_JOB` 不等於一定加字，可透過主體尺度、角度、構圖、場景、光線、材質、細節優先級等完成。
- FB 卡片標題／副標題若屬圖片外 UI/copy surface，由 Sales/copy 決定；若嵌入圖片，仍通過 literal whitelist / role / salience gate。
- 圖片本身必須先通過 Visual 的真實感、same-car、主體層級與 material uplift；Sales 市場定位不能覆蓋 Visual FAIL。
- 純視覺品質改善任務不要求先有 acquisition brief；只有要宣稱「市場精準型廣告入口」時才需要對應市場定位輸入。

`VISUAL_QUALITY_PASS != ACQUISITION_ENTRY_PASS`；同樣，`COPY_ENTRY_PASS != VISUAL_PASS`。兩者互相不能代替。

#### 3A0.A Stage-1 visual attention / interest support｜圖片先讓對的人看見商品，再支持繼續探索
當 `VISUAL_ENTRY_JOB` 屬 acquisition Stage-1，Visual 把任務收斂成兩個 bounded outcome，不建立新 owner／新 runner：
- `QUALIFIED_ATTENTION_SUPPORT`：第一眼先辨認「這一台車」、主體足夠有存在感、畫面層級乾淨、mobile/thumbnail 下仍清楚；不能靠 generic cinematic、過低機位、過度輪廓效果、背景奇觀或未授權大字只求停留。
- `QUALIFIED_INTEREST_SUPPORT`：讓 target buyer 容易看出與這台車真正相關的車身比例、特色部位、使用價值/可信狀態，產生看下一張／讀 copy／私訊的資訊動機；Visual 只用畫面支持 reason-to-care，不自行創造 Sales claim。

固定驗收補充：
`PRODUCT_ID_FIRST_GLANCE + TARGET_RELEVANCE_SUPPORT + LOW_VISUAL_COGNITIVE_LOAD + SAME_CAR_TRUST + PRODUCT_SALIENCE + NEXT_SURFACE_INFORMATION_SCENT`。

- `LOW_VISUAL_COGNITIVE_LOAD`：避免同時存在過多 badge、icon panel、說明文字、裝飾、背景亮點與競爭焦點；使用者需先看車，不需先解讀版面。
- `VISUAL_ENTRY_READINESS != MARKET_SUCCESS`：Visual 只能判 readiness / perceptual evidence；真實 attention、message-start、qualified conversation 與成交 outcome 回 Sales 做 attribution。
- Surface-role split 優先：圖片負責商品辨識/存在感/可信/形體，copy 負責需要語言才能說清楚的理由與 proof；除非 explicit render authority，不把 reason-to-care 轉成圖上說明。

#### 3A0.1 Visual anti-corruption adapter｜只翻譯必要市場定位，不把 Sales domain 帶進來
Visual 對 `ACQUISITION_ENTRY_BRIEF` 採 consumer-defined minimum contract。跨域輸入先經 task-local adapter，將 neutral acquisition fields 映射成 Visual 自己的 `VISUAL_ENTRY_HYPOTHESIS`；Sales/Human 的 raw state 不得直接進 Visual Canonical/runtime reasoning。

Visual allowlist：
`INTERFACE_SCHEMA_VERSION / SOURCE_AUTHORITY_REVISION / TASK_SCOPE / ACQUISITION_BRIEF_ID / POSITIONING_ID / CLAIM_SET_ID / SURFACE_ROLE_VERSION / EXPERIMENT_ID(optional) / TARGET_BUYER / MARKET_REASON_TO_CARE / PRODUCT_PROOF_PRIORITY / PURCHASE_OR_USE_ANCHOR / VISUAL_ENTRY_JOB / CLAIM_LIMITS / SURFACE_ROLE_SPLIT / VISUAL_TEXT_AUTHORITY / AUTHORIZED_EMBEDDED_LITERALS`。

Visual denylist：
`RAW_CUSTOMER_DIALOGUE / TRUST_STATE / OBJECTION_STATE / NEXT_STEP_STATE / PERSONALITY_OR_STAGE_CLASSIFICATION / INTERNAL_COST / WHOLESALE_BOTTOM / RAW_MARKET_DUMP / HISTORICAL_PROMPT / SALES_MECHANISM_INTERNALS / TASK-FOREIGN_HISTORY`。

固定：
- `ACQUISITION_BRIEF_ID / POSITIONING_ID / CLAIM_SET_ID / SURFACE_ROLE_VERSION / EXPERIMENT_ID` 只作 opaque correlation/version metadata；Visual 必須原樣保留／回傳供 GLOBAL 對帳，但不得用這些 ID 自行推導市場、客群或視覺內容。
- 若同一 market-optimized task 的 tracking envelope 與 current Sales brief 不一致／stale，標 `CROSS_SURFACE_SEMANTIC_DRIFT / CONTRACT_HOLD`；不得自行從舊 prompt/history 補成 current。純 visual-quality task 不依賴 acquisition brief 時不受此 gate 阻塞。
- adapter 只做語義翻譯與欄位裁切，不新增市場/客群判斷。
- `PRODUCT_PROOF_PRIORITY` 必須可追溯到同一 `ACQUISITION_ENTRY_BRIEF` 的 verified `PRODUCT_PROOF_POINTS`；它只允許 adapter 做裁切／排序，不得新增或改寫 proof。來源對不上時標 `PROOF_MAPPING_MISMATCH / CONTRACT_HOLD`。
- `TARGET_BUYER / MARKET_REASON_TO_CARE / PRODUCT_PROOF_PRIORITY / PURCHASE_OR_USE_ANCHOR / CLAIM_LIMITS` 預設是 **SEMANTIC_CONTEXT_ONLY**：用來決定主體尺度、角度、構圖、場景、光線、材質、細節優先級與 visual salience，不自動取得可讀文字渲染權。
- `SEMANTIC_CONTEXT != RENDERABLE_LITERAL`；`PRODUCT_PROOF_PRIORITY != ON_IMAGE_TEXT`；`MARKET_REASON_TO_CARE != POSTER_COPY`。即使年份、里程、價格、版本等 facts 已驗證，也不能因為它們進入 acquisition brief 就直接做成圖上大字、規格框、價格框或海報條。
- `SURFACE_ROLE_SPLIT` 是 Visual 必須實際消費的欄位，用來知道哪些訊息應由照片、標題、副標題或其他 copy surface 承載；不得只收 product proof 卻忽略 surface 分工。
- `VISUAL_TEXT_AUTHORITY` 預設為 `NONE`。只有 current user/task 明確要求把銷售文字嵌入圖片，或 current task contract 已明確授權時，才可為 `EXPLICIT`，並且只允許 `AUTHORIZED_EMBEDDED_LITERALS` 中的 literal。Sales 的市場資料本身不能建立這個 authority。
- dealer name / dealer phone / watermark / plate cover 等 REAL_CAR 既有文字物件仍走本檔 §6 的 literal/object authority；不得把它們與 Sales embedded-copy authority 混為一談。
- adapter 輸出固定分成兩條：`VISUAL_SALIENCE_OBJECTIVES` 與 `RENDERABLE_LITERAL_SET`。Execution 可以把前者轉成視覺控制，但只有後者可以被當成新增可讀文字；若 `VISUAL_TEXT_AUTHORITY=NONE`，則 Sales-derived `RENDERABLE_LITERAL_SET=EMPTY`。
- Execution 不得直接消費 raw `ACQUISITION_ENTRY_BRIEF` 來自行挑文字；只消費 Visual 已裁切後的 `VISUAL_ENTRY_HYPOTHESIS + RENDERABLE_LITERAL_SET`。
- contract 為 immutable task snapshot；不得把 Sales packet 存成 Visual 長期 state，也不得用上一次 brief 自動補本次缺欄。
- critical allowlist field 缺失時只 block 依賴該欄位的 market-optimized visual claim，不 block 純 visual quality work。
- extra/unrecognized field 預設忽略並標 `FOREIGN_OR_UNUSED_CONTRACT_FIELD`；不得因 provider 多送資料就擴大 Visual scope。
- Post-result 若出現 Sales-derived 年份／里程／價格／規格／市場賣點等可讀文字，但 `VISUAL_TEXT_AUTHORITY != EXPLICIT` 或 literal 不在 `AUTHORIZED_EMBEDDED_LITERALS`，標 `UNAUTHORIZED_ACQUISITION_COPY_RENDER / INTERFACE_CONSUMPTION_FAIL`；不得升為 winner/baseline，即使文字本身事實正確。
- Visual 可回最小 `VISUAL_ENTRY_FEEDBACK = ACQUISITION_BRIEF_ID / POSITIONING_ID / CLAIM_SET_ID / SURFACE_ROLE_VERSION / EXPERIMENT_ID(if any) / FEASIBILITY / SALIENCE_CONFLICT / MATERIAL_UPLIFT_STATE / MESSAGE_BETTER_CARRIED_BY_COPY(if applicable)`；tracking IDs 只供對帳，feedback 本體仍是 representation feedback，不是市場 truth 或 Sales decision。
- schema/interface 修改後必做 contract regression：required-field missing、extra-field injection、Sales/Human-state injection、stale-task brief、surface-role omission、unauthorized-copy-render、reverse-feedback scope 至少各驗一個。

## 3A. Objective binding before any optional visual choice
「知道最高目標」不足以構成正確 execution。任何會改變畫面的可選 component（背景、展間/門面、構圖、光線、時間氛圍、店家識別、文字、反射、景深、效果、裝飾）在被選入 production 前，必須先通過 `COMPONENT_VALUE_GATE`。

固定判斷：
`CURRENT_USER_GOAL → VEHICLE/PHOTO CONTEXT → CANDIDATE_COMPONENT → EXPECTED_VALUE_DELTA → SELECT | REJECT`

`EXPECTED_VALUE_DELTA` 至少檢查：
- `FIRST_GLANCE_ATTRACTION`：是否讓目標買家更容易停下來看這台車；
- `SAME_CAR_TRUST`：是否維持實車可信度、沒有讓畫面更像虛構廣告；
- `AESTHETIC_COHERENCE`：與車色、角度、鏡頭高度、光線、空間關係是否協調；
- `SALES_VALUE`：是否實質提升質感、可信度、產品聚焦、品牌信任或成交意願；
- `REGRESSION_COST`：是否搶主體、增加雜訊、造成 AI/過度精修感、遮蔽重要車況或引入 truth risk。

規則：
- component 不需要「必要」才可使用；只要整體 net value 為正即可。展間、車行門面、街景、停車場等都可以成為最優解。
- `未指定 ≠ 禁止`，但 `可生成 / 有品牌資訊 / 看起來完整 ≠ 有加分`。
- 若候選沒有可說明的正向 value hypothesis，或可預期主要作用只是填滿畫面、重複資訊、展示車行本身，預設不選。
- 先選「對這台車與這張圖有加分的搭配」，再處理 component 細節；不得先固定 component 類型，再事後替它找理由。
- Post-render audit 必須驗證原先的 value hypothesis 是否真的成立；不成立即 `COMPONENT_VALUE_NEGATIVE`，不得因技術完成度高而升為 baseline/winner。


### 3B. Baseline-dominance / material-uplift gate
來源原圖／current approved baseline 是 incumbent，不是和新候選平權的其中一張。任何非必要視覺修改都必須證明相對 baseline 有**實質淨提升**，才值得取代原圖。

固定：
`SOURCE/CURRENT BASELINE → CANDIDATE → DELTA_VS_BASELINE → MATERIAL_UPLIFT? → REGRESSION_COST → PROMOTE | REJECT_AND_KEEP_BASELINE`

- `NOT_WORSE` 不等於 `IMPROVED`。
- 小幅真實感、氛圍、空間感等局部優點，若不足以讓整體美感／可信度／銷售價值明顯變好，視為 `INSUFFICIENT_UPLIFT`。
- 候選若同時帶來 literal error、identity drift、AI/精修感、資訊干擾、主體競爭等成本，必須從 value delta 扣除。
- 若淨提升不明確或只與 baseline 打平，直接保留 baseline；不得因『已經生成一張』而交付。
- 背景、展間、光線、構圖等 optional component 都受此 gate 約束；沒有 material uplift 時，最好的背景可以就是原圖既有背景。

## 4. Execution selection
Execution 只回答：哪個目前可用方法最有機會達成上面的可見結果。

- 某 route 失敗，不等於整個目標不可做。
- 已證明沒有新資訊增益的同 route 不重抽碰運氣。
- image_gen 可在允許生成式修改的任務使用；不得全域封鎖。
- deterministic/local pixel route 可在需要精準保留、文字、mask、局部合成時使用。
- `edit_op:null / parent_gen_id:null` 只表示沒有 observable source-bound receipt；不是自動視覺 FAIL。
- 若當輪明確是 strict source-preserving，沒有 source-bound evidence 的結果不得冒充 strict edit。


### 4.1 Precall eligibility vs post-render promotion
`BASELINE_DOMINANCE` 不得被錯誤實作成「render 前已證明 candidate 比 baseline 好」。完整 material uplift 必須看 fresh output 才能判。

因此任何會直接顯示結果的 generation/edit route 固定：
`BASELINE + REJECTED_FAMILY_STATE → PRECALL_ELIGIBILITY → ONE PILOT → POST_RENDER DELTA_VS_BASELINE → PROMOTE | REJECT_KEEP_BASELINE`

**Output-count / visible-call binding：**
- 使用者只說「出圖」而未指定張數時，預設 `OUTPUT_COUNT=1`；若工具暴露 `n` / count 參數，必須明確要求 1。
- `INPUT_REFERENCE_COUNT != OUTPUT_COUNT`：一次提供多張來源圖，只代表 reference set，不授權一圖對一輸出，也不得因附件數量自動生成多張。
- 只有使用者當輪明確要求多張／比較組／指定張數時，才可提高 output count；其餘情況一次最多一個 visible pilot。
- 對單張 pilot，`VISIBLE_IMAGE_TOOL_CALL_BUDGET=1`：一次使用者授權只允許一次 visible image tool invocation。第一個可見結果一回來即 `HARD_STOP → AUDIT_ONLY`，不得在同一授權內再自動呼叫第二次工具，即使第一張失敗、想換角度或想順手再測一次也不行。
- `OUTPUT_COUNT=1` 同時約束「單次 tool call 回傳張數」與「同一授權下的 visible image tool call 次數」；不得只把 `n=1` 當成已滿足而連續呼叫兩次。
- 一個 image tool call 若意外回傳多於授權數量，或同一單張授權被執行第二次 visible image tool call，均標記 `OUTPUT_COUNT_DISCIPLINE_FAIL / SINGLE_PILOT_CALL_BUDGET_FAIL`；額外結果只作 failure evidence，不得因已生成而升為 candidate/winner/baseline。

`PRECALL_ELIGIBILITY` 必須同時 PASS：
- `SOURCE/TASK_BINDING_VALID`；
- `STRONG_UPLIFT_HYPOTHESIS`：預期提升不是「稍微更有氛圍／比較完整」，而是有合理機會明顯提高 final aesthetic / trust / sales outcome；
- `MATERIAL_DIFFERENCE_FROM_REJECTED`：若上一個 scene/action family 已因 insufficient uplift 被 reject，不得只換小構圖、微調夕陽、改招牌位置後重抽同 family；
- `KNOWN_REGRESSION_NOT_REPEATED`：不得主動重帶已知 literal/identity/foreign-context defect。

Post-render 才執行真正的 `MATERIAL_UPLIFT_VS_BASELINE`。工具結果可能直接顯示，但**可見 ≠ promotion ≠ winner ≠正式交付**。若 FAIL，立刻 `REJECT_KEEP_BASELINE`，禁止成 parent/baseline。

當 current route 沒有 hidden staging 時，無法保證失敗 pilot 在 UI 完全不可見；不得宣稱具有這種能力。能控制的是：提高 precall admission bar、每輪最多一個 pilot、禁止無新價值的同 family 重抽、以及 post-render 不污染 state。



### 4.2 Delta-scope / route-controllability gate
`CURRENT_TASK_BINDING_PACKET` and a strong uplift hypothesis are necessary but not sufficient. The selected route must also be capable of changing the intended delta without repeatedly destabilizing higher-priority protected state.

Fixed admission sequence:
`CURRENT_DELTA → PROTECTED_STATE → ROUTE_CONTROL_SCOPE → MATCHING_SCOPE_EVIDENCE → ROUTE_ELIGIBLE | ROUTE_INELIGIBLE`

- Example: if `CURRENT_DELTA=BACKGROUND/SCENE` while `SAME_REAL_CAR_IDENTITY` is protected, a route that routinely redraws headlamps, bumper, grille, wheels, body proportions, paint/reflections, or viewpoint is a scope mismatch even if the new background might be attractive.
- A whole-image generative route is not globally forbidden. It is eligible only when its uncontrolled variation does not threaten the current protected state, or matching-scope evidence shows identity stability sufficient for this task.
- Repeated post-render identity drift is matching-scope negative evidence. Once established, the same route/delta combination must fail precall until materially different control evidence exists.
- When the requested value improvement is mostly scene/background/composition, prefer a source-anchored edit/reference/composite/local route whose controllable scope matches that delta.
- If no available route can preserve the protected state to an acceptable degree, keep the source/current baseline or state the capability boundary; do not broaden the edit just to produce a candidate.

## 4A0. REAL_CAR compiled execution packet｜出圖前只能有一包最新、唯一、可追溯的指令

### 4A0.R Requirement projection compiler｜先保留需求身份，再拆成 Visual / Execution / Audit 投影
REAL_CAR 對同一個使用者需求不得用「composition 一條、lighting 一條、literal 一條、audit 再一條」的方式各自取得平行 authority。先消費 GLOBAL task-local `CANONICAL_REQUIREMENT`，再由既有 owner 做 bounded projection。

固定：
`CANONICAL_REQUIREMENT → VISUAL_TARGET_PROJECTION → EXECUTION_CONTROL_PROJECTION → REAL_CAR_EFFECT_OP_GRAPH → ROUTE_LEGALIZATION → REAL_CAR_EXECUTION_PACKET → STAGED_EXECUTION → VISUAL_VERIFICATION_PROJECTION → REQUIREMENT_STATUS`。

每個進入 `CURRENT_TASK_BINDING_PACKET / REAL_CAR_EXECUTION_PACKET` 的 task-derived field，必須能回指：
`REQUIREMENT_ID / PARENT_REQUIREMENT_ID(optional) / SEMANTIC_OWNER / PROJECTION_ROLE / DERIVATION_SOURCE`。
無法回指 requirement 或 current domain semantic key 的欄位標 `UNBOUND_DERIVED_FIELD`，不得靠「看起來合理」直接進 live image call。

REAL_CAR 固定採以下語意聚合：
- `HERO / VEHICLE_IMPACT` 是一個 Visual outcome requirement；`COMPOSITION_TARGET / VIEWPOINT / SUBJECT_FRAME_OCCUPANCY / BOTTOM_CLEARANCE / PHOTOMETRIC_DEPTH / REFLECTION_FLOW / RIM_OR_EDGE_SEPARATION / BACKGROUND_COMPETITION` 是其可能的 derived projections，不是各自新的需求 authority。修正「首圖衝擊感」先回到同一 HERO requirement，再重算受影響 projections。
- `PLATE_COVER` 是一個 object requirement；`ACTIVATION / TARGET_ROLE / REQUIRED_STATE / CONSTRUCTION / RENDER_STATE / ALPHANUMERIC_HIDDEN` 是 child constraints。任一 child 漏失即同一 `PLATE_COVER_REQUIREMENT` incomplete，不得分散成多個互不相干的 patch。
- `WATERMARK` 是另一個獨立 requirement；可與 plate cover 同屬 local-object package，但不得因位置相近就合併語意，也不得因 watermark PASS 就推論 plate-cover requirement fulfilled。
- `SAME_REAL_CAR / CONDITION_TRUTH` 是 protected requirement；Execution 的 route/control 只能作 fulfillment mechanism，不得反向降低其 protected semantics。

Failure attribution 先 requirement-centric，再 layer-centric：
`VISIBLE_FAILURE → REQUIREMENT_ID → WHICH_PROJECTION_OR_CONSUMPTION_EDGE_FAILED? → CURRENT_STATE | COMPILATION | CONSUMPTION | ROUTE_CONTROLLABILITY | VERIFICATION`。
同一 requirement 在多層同時出現 manifestation 時，先產生**一個 root finding + 多個 affected projections**；不得每個 layer 各新增一條 Canonical 規則。

Current user correction 若改變 requirement intent：
`REVISE_REQUIREMENT_CORE → INVALIDATE_VISUAL/EXECUTION/VERIFICATION_PROJECTIONS → RECOMPILE_PACKET → PRECALL_DIFF_AUDIT`。
若只改 execution mechanism 而 requirement intent 未變，僅重編 execution projection；不得連帶改寫 Visual target。

### 4A0.E Capability-legalized effect graph｜把「想要什麼」lower 成 target 真正能做的影像操作
Requirement lineage 解決語意不散掉；本節解決另一半：**不能再把 composition、背景、光影、遮牌、浮水印、尺寸全部壓回一個 broad generative prompt，然後期待每個 requirement 都精準落地。**

REAL_CAR 以既有 Execution owner 產生 task-local `REAL_CAR_EFFECT_OP_GRAPH`；它不是新 owner，也不是另一份 Canonical。每個 derived control 必須成為 typed effect op，並先通過 route legality。

影像 effect class 固定使用最小必要集合：
- `PRESERVE_INVARIANT`：SAME_REAL_CAR / condition truth / major geometry 等 protected state，只定義不可被破壞的 invariant。
- `DETERMINISTIC_FRAME_TRANSFORM`：crop / pad / uniform resize / translate 等不需重畫車體的 frame operation。
- `GLOBAL_GENERATIVE_EDIT`：scene/background/whole-frame photometric 等可能改動大範圍像素的生成操作。
- `LOCAL_GENERATIVE_EDIT`：plate-cover、局部物件加入/移除等應限於 local semantic/resource scope 的生成操作。
- `DETERMINISTIC_LITERAL_OVERLAY`：要求 exact readable text/phone/watermark 且 callable deterministic renderer 存在時使用。
- `DELIVERY_TRANSFORM`：最終尺寸/格式/quality adaptation。
- `VERIFY_ONLY`：不修改 artifact，只驗 requirement/postcondition/invariant。

每個 op 至少記錄：
`OP_ID / REQUIREMENT_ID / INPUT_ARTIFACT / EFFECT_CLASS / TARGET_REGION_OR_ROLE / READ_SET / WRITE_SET / PRESERVE_SET / HARDNESS / REQUIRED_CAPABILITY / SELECTED_ROUTE / ROUTE_CAPABILITY_VERSION / LEGALITY / DEPENDENCIES / POSTCONDITION / OUTPUT_ARTIFACT`。

#### Route legality｜route 不是「能產圖」就算適配
固定：
`EFFECT_OP → REQUIRED_CAPABILITY + ALLOWED_WRITE_ENVELOPE → ROUTE_CAPABILITY_PROFILE → LEGAL | SOFT_EXPLORATORY | ILLEGAL`。

- `LOCAL_GENERATIVE_EDIT` 若 current route 沒有 machine-verifiable mask/locality，或 fresh evidence 顯示 edit 會跨出目標區重畫 protected state，預設只能 `SOFT_EXPLORATORY`；不能因 prompt 寫了「只改車牌」就視為 local-control proof。
- `GLOBAL_GENERATIVE_EDIT` 若 `SAME_REAL_CAR/CONDITION_TRUTH=HARD`，只有在 matching-scope evidence 顯示 source identity/protected state 足以維持時才可 production-legal；反覆 `edit_op:null / parent_gen_id:null` 且出現 identity/condition reinterpretation，屬 negative capability evidence。
- 參考圖驅動的 generative node 應把能力拆開標示：`IMAGE_REFERENCE_CONDITIONING / STRUCTURAL_CONDITIONING / NOVEL_VIEW_CONTROL / CONDITION_TRACE_FIDELITY / SCENE_LIGHT_RECOMPUTE / LOCAL_MASKING`。這些是 capability requirements/profile，不新增 effect class；只有 current environment 實際 exposed + callable 的項目才可取得 execution authority。
- 需要「母圖真實性 + 新角度自由度」時，不得把結構 conditioning 一律拉到最高強度而實質鎖死 source pose；Visual target 先決定 identity/condition 與 viewpoint freedom 的 priority，Execution 再選擇可用 conditioning strength/route。沒有該控制參數時只標 semantic constraint。
- `EXACT` literal 與 exact delivery size 優先 lower 到 callable deterministic post-process；若沒有 deterministic route，標 capability boundary，不得用更多 prompt 冒充 precision control。
- composition 若 `DETERMINISTIC_FRAME_TRANSFORM` 足以達成 HERO requirement，不得升級到會重畫車體的 view/whole-frame route。
- 一個 HARD requirement 若找不到 legal route，可以保留 exploratory pilot，但 `PRODUCTION_LEGALIZATION=FAIL`；不得為了「一定要有一張圖」把 requirement 偷降級。

#### Hard-op precall admission｜production legality 必須真的攔在 image tool call 前
本節修補「規則已知道 HARD op 不合法，但 live execution 仍直接呼叫 broad generator」的 consumption/enforcement 缺口；不新增 effect class、不改 Visual target，也不把 prompt 加嚴當修正。

固定：
`CURRENT_TASK_SPEC(default=PRODUCTION unless explicitly EXPERIMENT/EXPLORATORY) → EXECUTION_DAG → HARD_OP_ADMISSION → RENDER_EGRESS_CONTRACT → TOOL_CALL`。

- `PRODUCTION` 任務只要任一 active HARD requirement 為 `ILLEGAL | SOFT_EXPLORATORY | UNFULFILLED/CAPABILITY_BOUNDARY`，即 `HARD_OP_ADMISSION=BLOCK`，**不得呼叫 image/render tool**。`PRODUCTION_LEGALIZATION=FAIL → BLOCK_IMAGE_TOOL_CALL`，不是「仍出一張再事後判 REJECT」。
- whole-frame semantic generation 不得作為 local/source-preserving/deterministic requirement 的 fallback。若它是 current 唯一 callable image route，但其 write envelope 會碰 protected state，production path 固定停在 capability boundary；不得把多個 effect op重新壓回單一 broad generation。
- `EXPLORATORY` 只有 current task 明確授權 pilot/研究時才可繞過 production block；該 output 必須標 `NON_PRODUCTION_EVIDENCE`，不得直接成為交付候選、winner 或 production PASS。單純使用者說「出圖」沿用 §2 default production mode，不自動解讀為 exploratory authorization。
- tool call 前必須形成 task-local `HARD_OP_ADMISSION_RECEIPT = TASK_ID / TASK_MODE / ACTIVE_HARD_OPS / LEGALITY / SELECTED_ROUTE / OBSERVED_WRITE_ENVELOPE / MATCHING_CAPABILITY_EVIDENCE / ADMISSION(PASS|BLOCK)`；receipt 缺失、stale、或任一 HARD op 非 legal，直接 `PRECALL_ADMISSION_MISSING_OR_BLOCKED / BLOCK_IMAGE_TOOL_CALL`。
- `RENDER_EGRESS_CONTRACT` 只能由 `HARD_OP_ADMISSION=PASS` 產生 production-call eligibility；renderer adapter 不得自行把 blocked/unfulfilled op重新語意化成 prompt constraint。
- 若平台沒有機械 middleware 可證明此 gate 不可繞過，能力誠實標記 `IMAGE_PRECALL_ENFORCEMENT_CAPABILITY=SOFT_GOVERNED`；但 live owner/adapter 仍必須在可控制的呼叫點 fail-close，不能用「平台不是 hard-enforced」當作主動呼叫違規 route 的理由。

#### Staged execution + verifier｜每一關真的做過才算，不讓最後一步掩蓋前面漏執行
一般順序依 dependency 決定；當同一 artifact 同時含生成與 deterministic requirements 時，預設：
`SOURCE/BASELINE → LOW-RISK FRAME CONTROL(if needed) → GLOBAL GENERATIVE PASS(if legal) → LOCAL GENERATIVE PASS(if legal) → EXACT LITERAL/OVERLAY PASS(if legal) → DELIVERY_TRANSFORM → FINAL VERIFY`。
其中 `GLOBAL GENERATIVE PASS` 若任務是 reference-guided new scene/view，必須在 egress 中同時帶入 `REFERENCE REALITY/IDENTITY/CONDITION TARGET + TARGET VIEW/SCENE + TARGET LIGHT/EDGE SEPARATION`；不得退化成只描述背景，也不得把 source view 誤當 hard pose lock。

- 每個 mutating op 完成後立即跑與該 op 相依的 requirement verifier + protected-state regression check；hard fail 時停止 promotion。
- `OP_RECEIPT` 必須綁 `OP_ID + INPUT_ARTIFACT + ACTUAL_OUTPUT_ARTIFACT + ROUTE/CAPABILITY_VERSION + OBSERVED_WRITE_SCOPE + POSTCONDITION_RESULT`。下一個 op 只能吃 predecessor output。
- `DELIVERY_TRANSFORM`、exact watermark/phone overlay 等 deterministic stage 若只存在 packet 裡但沒有 receipt，直接 `EXECUTION_PATH_OMISSION`；不能因 raw image 看起來差不多就算完成。
- 若某一 downstream op fail，只重跑/re-lower affected legal subgraph；不得因遮牌、浮水印、尺寸其中一項失敗就自動 whole-frame 重抽，避免把已通過的 SAME_CAR/HERO 再次暴露給 stochastic regression。

#### Single-dispatcher node state machine｜真正修補「DAG 有寫，但實際只呼叫一次 generator」
成熟 workflow 的 enforcement 不靠每個 worker 自己記得流程；REAL_CAR 因此把現有 `EXECUTION_DAG` 實作成單一 dispatch path。這是 Execution owner 內部 runtime mechanism，不新增 Owner，也不新增第五個 authority object。

固定節點狀態：
`PENDING → READY → RUNNING → VERIFYING → SUCCEEDED | FAILED | BLOCKED | SKIPPED`。

固定執行鏈：
`EXECUTION_DAG → RESOLVE_READY_NODE → NODE_ADMISSION → COMPILE_NODE_EGRESS → DISPATCH_ONE_NODE → NODE_RECEIPT → NODE_VERIFY → COMMIT_OUTPUT → ADVANCE_CURSOR`。

規則：
- **唯一 tool-call path**：所有 image/render/postprocess side effect 只能由 Execution 的 `DISPATCH_ONE_NODE` 觸發；`PRODUCT_IMAGE_BUNDLE`、`PRODUCT_VISUAL_SPEC`、raw Canonical prose、上一張結果都不得直接呼叫工具。
- `EXECUTION_DAG` 內每個 mutating node 都要有 `NODE_STATE / DEPENDENCIES / INPUT_ARTIFACT / REQUIRED_CAPABILITY / ALLOWED_TOOL_FAMILY / WRITE_ENVELOPE / POSTCONDITIONS / RECEIPT_REQUIREMENT`。沒有成為 `READY` 的 node 不可執行。
- `READY` 前必須證明：所有 predecessor receipt 已 `SUCCEEDED`、input artifact 正是 predecessor committed output、current effect authorization / capability status / route revision 仍 fresh、該 node 的 admission 為 PASS。
- 每次 tool call 前由 DAG 內部產生**單次使用** `NODE_EXECUTION_TOKEN`：`TASK_ID / DAG_REVISION / NODE_ID / ATTEMPT_ID / INPUT_ARTIFACT_ID / ALLOWED_TOOL_FAMILY / ROUTE_REVISION / WRITE_ENVELOPE / REQUIRED_POSTCONDITIONS / TOKEN_STATE=UNUSED`。它是 DAG nested runtime field，不新增獨立 authority。
- `RENDER_EGRESS_CONTRACT` 改為**per-node sealed projection**：一次只允許投影 current token 對應的那一個 node。Sibling node 的 watermark、delivery、plate cover、背景等需求若不是 current node，不得塞入同一 call 讓 generator「順便做」。
- adapter 收到 missing / stale / already-used token、tool-family mismatch、input artifact mismatch、extra effect intent，直接 `NODE_DISPATCH_REJECT / NO_TOOL_CALL`。成功 dispatch 後 token 立即 `CONSUMED`，不得重放。
- tool 返回 artifact 不等於 node 成功。必須產生 `NODE_RECEIPT = TOKEN + ACTUAL_TOOL + OUTPUT_ARTIFACT + OBSERVED_WRITE_SCOPE + RESULT_METADATA`，再跑 node verifier；只有 verifier PASS 才 `COMMIT_OUTPUT` 並把 node 標 `SUCCEEDED`。
- FAILED/BLOCKED node 的 output 進 `QUARANTINED_CANDIDATE`，不得成為下一 node input、baseline、winner 或 final。平台若已把 raw generator result 顯示給使用者，仍只能視為 raw/non-final evidence；不可因此跳過 commit gate。
- downstream retry 只建立新的 `ATTEMPT_ID` 重跑該 node或受影響 subgraph；已 `SUCCEEDED` 且未被 dependency invalidation 影響的 node 不重跑。
- 若 required mutating nodes > 1，但 actual execution trace 只有一個 broad generative receipt，或單一 receipt 被拿來同時宣稱 background + plate cover + watermark + delivery 完成，直接 `DAG_COLLAPSE_DETECTED / EXECUTION_CONSUMPTION_FAIL`。
- `FINAL_DELIVERY` 只能在所有 required nodes `SUCCEEDED`、所有 HARD check PASS、最後 artifact lineage 連續時 commit；任何 required deterministic node 無 receipt 都不得交付。

#### Pre-dispatch plan commit + orphan side-effect firewall｜先承諾一條合法路徑，再允許第一個副作用
本節修補 fresh Sienta test 暴露的 defect：DAG / conservative lane 已正確存在，但 production 仍先執行一個後來完全不被 final lineage 使用的 whole-frame generation，之後才切換到 source-backed deterministic lane。這不是 Visual/requirement 缺口，而是 **未先 commit production path 就允許 side effect**。

成熟 workflow 的共同原則在此收斂成既有 Execution dispatcher 的一個 pre-dispatch phase，不新增 Owner、不新增第五個 runtime object：
`DRAFT_EXECUTION_DAG → ANALYSIS_ONLY_PHYSICAL_PLAN_OPTIMIZATION → ROUTE/LANE_SELECTION → GRAPH_REDUCTION → PLAN_ADMISSION → COMMIT_PLAN → DISPATCH_READY_NODE`。

固定：
- `EXECUTION_DAG` 在第一個 mutating/visible side effect 前皆為 `DRAFT`；`DRAFT_DAG` **沒有 tool-call authority**。
- `ROUTE/LANE_SELECTION` 必須先在所有合法候選中選定一條 production lineage；advanced generative lane、conservative source-backed lane、strict source-preserving lane 等是**互斥的 execution alternatives**，不是可以先各跑一次再看哪張好。
- `GRAPH_REDUCTION` 必須把不在 selected lineage、guard=false、capability-ineligible、被較低風險合法節點支配、或不再需要的 node 標成 `PRUNED/SKIPPED`；這些 node 不得進 `READY`。`OPTIONAL_NODE_PRESENT != PERMISSION_TO_EXECUTE`。
- 只有 reduction 後的 node set + dependency + input artifact + capability revision + output contract 通過 `PLAN_ADMISSION`，才產生 task-local `COMMITTED_PLAN_ID / PLAN_DIGEST / SELECTED_LANE / ACTIVE_NODE_SET / PRUNED_NODE_SET / FIRST_EFFECT_CLASS`。它是 `EXECUTION_DAG` 的 nested committed state，不建立平行 authority。
- 第一個 `NODE_EXECUTION_TOKEN` 必須綁同一 `COMMITTED_PLAN_ID + PLAN_DIGEST`。token 無 plan digest、node 不在 `ACTIVE_NODE_SET`、node 已被 `PRUNED/SKIPPED`、或 selected lane 不匹配時，`NODE_ADMISSION=REJECT / NO_TOOL_CALL`。
- **Effect gateway = 唯一 side-effect boundary**：所有 image generation/edit、deterministic composite、literal overlay、delivery transform 皆必須從 current committed plan 的 `DISPATCH_ONE_NODE` 通過。任何實際 tool call 找不到 matching committed node/token，立即標 `ORPHAN_SIDE_EFFECT / UNPLANNED_EFFECT`；該 output quarantine，run 停止 promotion，後續「做出一張正確 final」不能把這個違規抵銷。
- `SIDE_EFFECT_PIVOT`：任何會對使用者可見、不可可靠撤回、或會改變 production artifact lineage 的 first mutating call 視為 pivot。pivot 前可重新規劃；pivot 後不得在同一 production authorization 靜默切換到另一條 lane。若 selected lane 失敗，只能依該 lane 的合法 retry/re-lower 規則處理；要改成 materially different lane 必須建立 `PLAN_REVISION+1` 並重新 admission，且若前一 pivot 已對使用者可見，該 run 結束為 failure/non-final，不在同一輪再輸出第二個 production artifact。
- `IDEMPOTENCY / EXACTLY-ONCE INTENT`：每個 mutating node 使用 `TASK_ID + PLAN_DIGEST + NODE_ID + ATTEMPT_ID` 作 execution key。相同 key 重放只能回同一 receipt / reject duplicate，不得產生第二份副作用；retry 必須新 `ATTEMPT_ID` 並受 node retry policy 約束。
- `DECLARED_IO_SANDBOX`：node adapter 只能讀 `INPUT_ARTIFACT + DECLARED_INPUTS`，只能寫 `DECLARED_OUTPUT_ARTIFACT/WRITE_ENVELOPE`；不得從 raw history / sibling requirements /未宣告附件補輸入。平台不能機械 sandbox 時，標 `SOFT_HERMETICITY`，但 egress 仍 default-deny。
- `VISIBLE_INTERMEDIATE_GATE`：若某 route 的 intermediate artifact 會被平台強制直接顯示給使用者，且本次 contract 只允許一個 final production artifact，該 route不得被選作 hidden helper node。它只能是 final-candidate node、explicit exploratory node，或被 `PRUNED`。不得先顯示 generative helper/candidate，再用 deterministic lane 交付第二張並聲稱 single-run clean success。
- `RECONCILE_TRACE`：run 結束時以 `COMMITTED_PLAN.ACTIVE_NODE_SET` 對實際 `TOOL_CALL_TRACE` 做雙向比對：`planned-but-missing → EXECUTION_PATH_OMISSION`；`actual-but-unplanned → ORPHAN_SIDE_EFFECT`；`one receipt claims sibling nodes → DAG_COLLAPSE_DETECTED`。三者任一存在都不能 `FINAL_DELIVERY=PASS`。

#### Analysis-only physical-plan optimizer｜先比較所有合法方案，再 commit 最值得做的一條
本節修補 latest fresh Sienta source-backed run 暴露的新 defect：orphan side effect 已可避免，但 Execution 仍可能把「第一條能合法完成 HARD requirements 的保守方案」直接當 winner，造成 SAME_REAL_CAR 很安全、作品卻只有最低限度 uplift。這不是 Visual target 不足，也不是再加更多美術規則；根因是 **legalization 之後缺少 quality-aware physical-plan optimization**。

它收斂在既有 Execution `DRAFT_EXECUTION_DAG` 的 analysis-only phase，不新增 Owner、不新增第五個 runtime object、不建立車款 cookbook。固定：
`PRODUCT_VISUAL_SPEC + EXECUTION_CAPABILITY_PROFILE + SOURCE_INSTANCE_ANCHOR_SET → ENUMERATE_CANDIDATE_PHYSICAL_PLANS(no side effects) → HARD_FEASIBILITY_FILTER → VALUE/RISK ESTIMATION → DOMINANCE_PRUNE → SELECT_BEST_LEGAL_PLAN → PLAN_ADMISSION → COMMIT_PLAN`。

固定規則：
- **Analysis-only symbolic phase = zero production side effect**：候選 physical plan 的建立、legalization、初步比較期間不得產生任何使用者可見 production artifact、Library mutation、baseline/winner mutation 或 visible generative helper。若 current capability 明確支援 hidden deterministic staging，可在下述 `SANDBOX_PREVIEW` 以 ephemeral scratch artifact 實測 reversible deterministic plan；該 preview 不是 production side effect、不得取得 final/baseline authority，且第一個 production side effect 仍只能發生在 `COMMIT_PLAN` 之後的 `DISPATCH_ONE_NODE`。
- `FIRST_LEGAL_PLAN != BEST_LEGAL_PLAN`：若 current callable surface 存在兩條以上 materially different、皆可滿足 HARD requirements 的合法 plan，Execution 必須先比較，不得因某條最保守／最先列舉／歷史最常用就直接 commit。
- candidate plan 只能由**目前真正 callable 的 operators**組成；不能為了排名好看虛構 segmentation、mask、hidden staging、novel-view control 或其他 unavailable capability。不可執行的 plan 在 hard feasibility stage 直接淘汰，不進 value ranking。
- **Constraint-first / lexicographic optimization**：先 HARD feasibility，再比較 risk/value；任何 `SAME_REAL_CAR / CONDITION_TRUTH / REQUIRED_LITERAL / DELIVERY / activated HARD object` 不合格的 plan 一律淘汰，禁止用高 aesthetic score 抵銷 HARD fail。其餘合法 plan 依序比較：
  1. `PROTECTED_STATE_REGRESSION_RISK`：identity/condition/geometry/literal collateral risk 越低越優先；
  2. `EXPECTED_PRODUCT_UPLIFT`：依 Visual `NET_UPLIFT_CRITERIA` 比較 hero、form readability、material depth、grounding、thumbnail presence、background competition 等；
  3. `LOCAL_EFFECT_FEASIBILITY/QUALITY`：plate cover、watermark carrier、局部 tonal/edge shaping 等 operator 是否有足夠 target geometry / implementation reliability；
  4. `EXECUTION_COMPLEXITY + VISIBILITY/RETRY COST`：在前面價值相近時，較少節點、較少 visible pivot、較低 retry/lineage risk 的 plan 優先。
- 不使用一個會把 HARD、風險、美學全部揉成同一分數的巨型 weighted score。numeric estimate 若存在只作 task-local ranking aid；最終順序仍服從上述 lexicographic constraints。
- `SOURCE/CURRENT BASELINE` 永遠是 candidate-zero/incumbent。若所有合法修改 plan 的 predicted net uplift 都不足以明顯勝過 baseline，optimizer 可選 `KEEP_BASELINE + REQUIRED_LOCAL/DELIVERY_ONLY`；不得因「已經可以做某個 operator」就自動增加修改。
- `SOURCE_SELECTION` 是 physical-plan decision 的一部分。當多張 source view 都在 `HERO_VIEW_BAND` 內且 truth evidence 足夠，optimizer 應比較 `source + reframe` 組合的 hero/completeness/crop-safety/visible-component value；不得固定沿用上一張 source，也不得把單一 source 的 pixel crop 變成長期 recipe。
- `DOMINANCE_PRUNE`：若 plan A 對所有 HARD constraints 不差於 plan B、regression risk 不高於 B、預期 product uplift 不低於 B，且 complexity/visibility cost 不高於 B，則 B 標 `DOMINATED/PRUNED`；不必送進 commit。
- selected winner 至少形成 task-local `PHYSICAL_PLAN_DECISION = PLAN_ID / SOURCE_CHOICE / OPERATOR_SET / HARD_FEASIBILITY / REGRESSION_RISK_CLASS / EXPECTED_PRODUCT_UPLIFT / LOCAL_EFFECT_FEASIBILITY / COMPLEXITY_VISIBILITY_COST / DOMINANCE_REASON / SELECTED=true`，並寫入同一 `EXECUTION_DAG` nested committed state；它不是新的 authority object。
- operator 的視覺缺陷（例如黑布太方、接觸陰影不自然、watermark carrier fit 不佳）優先修 **operator implementation / precondition / verifier / bounded parameter policy**，不要在 Canonical 一直追加「再皺一點／再薄一點／固定某座標」等案例句。穩定 semantic contract 留 Canonical；implementation/evidence 留 Execution/operator status。
- 長期學習只更新 bounded planner statistics / accepted-rejected evidence，例如某 archetype/source-view band 的成功率、某 operator 在特定 geometry class 的失敗型態、retry/quality distribution；不得把單次 Sienta/A250/Altis 的 source ID、crop px、plate polygon、opacity、背景配方升成永久 rule。

**Planner anti-bloat invariant：**
`NEW FAILURE → EXISTING REQUIREMENT/OPERATOR/VERIFIER CAN EXPRESS? → FIX IMPLEMENTATION/ESTIMATE/CONSUMPTION → ONLY ADD CANONICAL SEMANTICS IF TRUE SEMANTIC GAP`。合法方案選擇品質不足時，先修 cost/value estimation、candidate enumeration、operator capability evidence；禁止回頭堆疊同義視覺規則。


#### Sandboxed preview + spatial binding contract｜把「預測合法」升級成「實際幾何與成品預覽已驗證」
latest fresh Sienta source-backed run 顯示新的失敗型態：whole-frame orphan generation 已被避免、SAME_REAL_CAR 也維持，但 final 出現明顯 blurred/padded band、黑布只遮到車牌局部且牌號仍可讀、watermark 沒有真正貼合 intended windshield/body carrier。這代表目前不是 lane-selection defect，而是 **predicted plan quality 未經 hidden materialized preview 驗證 + local target geometry 在 frame transform 後失去座標 lineage**。

成熟架構在此收斂成既有 Execution 的兩個 nested mechanism，不新增 Owner、不新增 runtime authority：
`SYMBOLIC_PLAN_ENUMERATION → SANDBOX_PREVIEW_ELIGIBILITY → EPHEMERAL_DETERMINISTIC_PREVIEW → SPATIAL/OPERATOR_VERIFY → VISUAL_PREVIEW_RANK → SELECT_BEST_LEGAL_PLAN → SAVE_PLAN_DIGEST → PLAN_ADMISSION → COMMIT_PLAN → APPLY_EXACT_PLAN`。

**A. Sandboxed deterministic preview｜可逆、隱藏、成功才 promote**
- 只有 current capability status 明確為 `HIDDEN_INTERMEDIATE_STAGING=AVAILABLE` 且 operator 為 deterministic / reversible / declared-I/O 的 plan，才可進 `SANDBOX_PREVIEW`。可包含 `crop/reframe/resize/pad/extent/tone/local composite/exact literal/delivery transform`；會直接對使用者顯示結果的 image-generation/edit surface 不得當 hidden preview helper。
- 每個 preview 使用 fresh scratch execroot / temporary artifact namespace，只掛 declared inputs；preview outputs 不進 Library、不改 current baseline、不取得 node receipt / production lineage，reject 後丟棄。只有 selected plan 的 exact parameters/transform metadata 進 `COMMITTED_PLAN`。
- optimizer 對 deterministic plan 不得只靠 predicted aesthetic metadata；當 preview 可安全產生時，必須在 **final delivery size / aspect** 實際檢查 `VEHICLE_COMPLETE / HERO / BACKGROUND_COMPETITION / FRAME_COHERENCE / LOCAL_EFFECT_QUALITY / WATERMARK_CARRIER_FIT / PLATE_COVER_RESULT` 後再排名。
- `FRAME_ADAPTATION`（crop、contain/pad、blur-fill、其他 source-backed framing）是 mutually comparable physical operators。blurred/mirrored padding 不是 default；若 final-size preview 出現明顯 band、重複邊界或「像補版」的視覺斷裂，且存在同 HARD feasibility 下更 coherent 的 source/crop plan，該 padding plan 直接 `DOMINATED/PRUNED`。
- selected plan 形成 `SAVED_PHYSICAL_PLAN = PLAN_DIGEST / SOURCE_HASH / OPERATOR_VERSIONS / OPERATOR_PARAMETERS / SPATIAL_BINDINGS / TRANSFORM_CHAIN_DIGEST / PREVIEW_ARTIFACT_HASH / FINAL_DELIVERY_CONTRACT`。production apply 必須執行 saved plan；source、operator version、transform/binding 或 delivery contract 任一 drift，標 `PLAN_APPLY_DRIFT / REPLAN_REQUIRED`，不得現場重新猜座標。

**B. Spatial-frame lineage｜所有局部物件跟著 frame transform 走，不再複製舊 absolute pixel 座標**
- 每個 raster artifact 必須有唯一 `SPATIAL_FRAME_ID`。任何 `crop / scale / translate / pad / extent / rotate / perspective` frame op 必須輸出 `PARENT_FRAME_ID / CHILD_FRAME_ID / T_PARENT_TO_CHILD / T_CHILD_TO_PARENT / OUTPUT_BOUNDS / TRANSFORM_CHAIN_DIGEST`。
- plate、windshield/body carrier、wheel、glass、local-light ROI 等 target geometry 優先錨定在**可追溯的 source/native frame 或 current artifact frame**，不得把某次 preview/final 的 absolute pixel polygon 當成跨 frame 可重用座標。
- downstream local op 固定建立：`SPATIAL_BINDING_RECEIPT = TARGET_ROLE / GEOMETRY_SOURCE / SOURCE_FRAME_ID / SOURCE_ROI_OR_POLYGON / GEOMETRY_CONFIDENCE / TRANSFORM_CHAIN / PROJECTED_ROI_OR_POLYGON / CURRENT_ARTIFACT_FRAME_ID / CLIP_STATE / BINDING_VALID`。
- 若 `BINDING_VALID != true`、target polygon 落出 expected bounds、transform chain 斷裂、或 geometry confidence 不足以滿足 HARD local object，node 必須 `BLOCKED` 或 optimizer 改選 target 更可解析的 source；不得以目測舊座標硬貼。
- perspective/local composite 使用明確 homography/affine matrix；ROI/write envelope 必須由 current projected geometry 產生。Local operator 只能改 ROI + 必要 feather/contact-shadow envelope，不能因 local placement 方便而取得 whole-frame write scope。

**C. Operator precondition + postcondition verifier｜結構先驗、preview 後驗、production 再確認**
- 每個 local/delivery operator 在 preview/apply 前先跑 structural verifier：input frame/hash、target binding、transform chain、output bounds、write envelope、required literal/object authority、delivery aspect/size 必須一致；不一致直接 invalid plan/node。
- `PRIMARY_PLATE_COVER` postcondition 不是「有黑色物件出現」，而是 current primary plate readable characters 已被實際遮住、cover 與 plate target 有足夠幾何重疊且沒有明顯漂移到 grille/body；construction/材質品質仍由既有 §6B + Visual judge 驗收。
- `WATERMARK` postcondition 不是「文字有畫出來」，而是 exact literal readable 且 bounding region 與 current authorized vehicle carrier（glass/body）實際相交；若落在 ceiling/background/foreign object，即 `WATERMARK_CARRIER_BINDING_FAIL`，不得因 literal 正確而 PASS。
- `DELIVERY_FRAME` 必須在 final 1080×1080（或 current contract）驗 `VEHICLE_COMPLETE + CROP_SAFETY + FRAME_COHERENCE + NO_LOW_VALUE_PADDING_ARTIFACT`；source-backed 不代表可以用明顯 letterbox/blur band 換取 square compliance。
- preview PASS 不能取代 production verify。Apply 後再以同一 saved plan/binding/postconditions 重驗；`PREVIEW_PASS + APPLY_DRIFT = FAIL`。

**D. Failure attribution / anti-bloat**
- `LOCAL_OBJECT_MISPLACED_AFTER_REFRAME` 優先歸因 `SPATIAL_BINDING/TRANSFORM_LINEAGE`，不是新增一條車款座標規則。
- `SAFE_BUT_VISUALLY_POOR_FRAME_FILL` 優先歸因 `FRAME_ADAPTATION_PLAN/preview ranking`，不是把「不要黑邊／不要模糊底」寫成全域固定禁令。
- `LITERAL_CORRECT_BUT_WRONG_CARRIER` 優先歸因 `TARGET_BINDING_VERIFIER`，不是加強 prompt。
- 只有 existing spatial/operator/preview contracts 無法表達的新 semantic gap 才可新增 Canonical；其餘修 operator implementation、geometry estimator、preview verifier 或 planner statistics。

**Source-backed dominance rule for current platform：**
當 current capability status 已顯示 whole-frame generation 對 `SAME_REAL_CAR / CONDITION_TRUTH` 不具 matching-scope production evidence，而 deterministic source-backed lane 能完成 active HARD requirements 時，`GRAPH_REDUCTION` 必須在**任何 image-generation side effect 前**直接 prune whole-frame generative node；不得「先生成看看，再決定其實不用」。只有 current task 明確需要且合法化了 generative value delta 時，生成 node 才能留在 committed active set。

**Current-platform conservative production lane：**
當 whole-frame generation 對 SAME_REAL_CAR / CONDITION_TRUTH 沒有 matching-scope production evidence時，不代表整個出圖任務一定停止。Execution 先嘗試 lower 成目前真正可控的 source-backed lane：
`SOURCE_SELECT → DETERMINISTIC_REFRAME/TONE(if legal) → ISOLATED_ASSET_GEN(if needed, does not touch car) → DETERMINISTIC_LOCAL_COMPOSITE(if target geometry is sufficiently resolved) → DETERMINISTIC_WATERMARK → DELIVERY_TRANSFORM → FINAL_VERIFY`。
若 local target geometry / composite capability仍不足以滿足 activated HARD object（例如黑布遮牌），才在該 node fail-close；不得回退成 whole-frame redraw。

#### Current platform truth boundary
ChatGPT/image editor 類 route 可接受上傳圖與區域編輯意圖，但 selection/local edit 並非機械保證，實際修改可能延伸到選區外；因此沒有 fresh machine-verifiable locality/source-binding receipt 時，REAL_CAR 不得把此類 route 標成 `HARD_LOCAL_CONTROL`。平台若會先顯示 raw generator result，也不得宣稱存在不可見 staging；架構能保證的是 final-promotion gate 與後續 legal post-process，不是假裝中間圖沒有出現。

#### Ambient-context sink + artifact-promotion attestation｜「送什麼」與「工具實際吃到什麼」分開治理
latest fresh Sienta visible image-generation run 暴露的 defect 與前一輪不同：current `RENDER_EGRESS_CONTRACT` 已明確 default-deny 非授權文字、source-backed lane 也已具 preview/spatial-binding contract，但實際 whole-frame image sink 仍重新生成整車，並在成品新增「實車拍攝／實車狀態／第三方鑑定／安心購買」等未在 `VISIBLE_LITERAL_ALLOWLIST` 的 caption/banner。這證明 **pre-call egress projection 正確，不等於 downstream sink 具有 hermetic context consumption**；若工具會隱式消費 ambient conversation/context，單靠 prompt/contract 無法物理保證其不吸收控制面、歷史或其他語意。

本節只修 Execution adapter / production-promotion boundary，不新增 Owner、不建立平行 image logic。成熟的 least-privilege、hermetic build、admission/enforcement、provenance/attestation 原則收斂為：
`RENDER_EGRESS_CONTRACT → TOOL_CONTEXT_CLASSIFY → PRODUCTION_SINK_ADMISSION → ACTUAL_TOOL → OUTPUT_SURFACE_AUDIT → ARTIFACT_PROVENANCE_ATTESTATION → PROMOTE | QUARANTINE`。

**A. Tool context-consumption class｜先證明工具能被隔離，才把 sealed egress 當硬邊界**
每個 render/edit route 的 observed status 必須標：
`TOOL_CONTEXT_CONSUMPTION_CLASS = HERMETIC_DECLARED_INPUT | EXPLICIT_SCOPED_CONTEXT | AMBIENT_CONTEXT_IMPLICIT | UNKNOWN`，並至少附 `EXPLICIT_PAYLOAD_CONTROL / AMBIENT_HISTORY_ACCESS / USER_VISIBLE_INTERMEDIATE / OUTPUT_TEXT_CONTROL / SOURCE_BINDING_EVIDENCE`。
- `HERMETIC_DECLARED_INPUT`：工具只能讀 declared source + sealed node payload；未宣告 context 不可見。
- `EXPLICIT_SCOPED_CONTEXT`：工具可見明確有限 context，且 scope/參數可驗證；依 matching-scope evidence 決定 production eligibility。
- `AMBIENT_CONTEXT_IMPLICIT`：工具的有效輸入會由整體 conversation/history/ambient state 隱式推導，adapter 無法證明只吃 sealed payload。
- `UNKNOWN`：無法證明 consumption boundary。
- `SEALED_EGRESS_SOFT_ENFORCEMENT` 不再可被誤用成 production isolation proof；當 `TOOL_CONTEXT_CONSUMPTION_CLASS ∈ {AMBIENT_CONTEXT_IMPLICIT, UNKNOWN}` 時，`RENDER_EGRESS_CONTRACT` 只能降低主動洩漏，不能宣稱 downstream tool 被隔離。

**B. Production sink admission｜平台可要求呼叫，不代表這個 sink 有 production authority**
`PLATFORM_REQUIRED_INVOCATION != REAL_CAR_PRODUCTION_AUTHORIZATION`。
- 對 `SAME_REAL_CAR / CONDITION_TRUTH / EXACT_LITERAL / VISIBLE_LITERAL_DEFAULT_DENY / NO_INVENTED_CLAIMS` 任一為 HARD 的 public product-image task，whole-frame `AMBIENT_CONTEXT_IMPLICIT/UNKNOWN` generative sink 預設 `PRODUCTION_SINK_ELIGIBILITY=NO`，除非 fresh matching-scope evidence 同時證明 source-binding、context isolation、literal surface 與 protected-state postconditions。
- 平台/host 若因上位產品規則仍強制觸發該 visible tool，該 artifact 固定標 `PLATFORM_RENDER_NONFINAL / EXPLORATORY_ONLY`；它可以被看見，但不得取得 `NODE_SUCCEEDED`、不得成為 baseline/winner、不得寫入 official production lineage，也不得因「畫面看起來不錯」改寫 production legality。
- 若 strict production contract 需要 single final artifact，而唯一可用 visible route 是 non-production ambient sink，標 `PLATFORM_EXECUTION_CONFLICT / CAPABILITY_BOUNDARY`；不得在 Canonical 宣稱已硬阻擋一個上位平台實際會強制執行的 call。
- deterministic source-backed route 若可合法完成 final，仍是 official-artifact lane；但 visible ambient render 不能偽裝成 hidden helper，也不能用來替 deterministic plan 取得 production evidence。

**C. Output surface provenance audit｜輸出端重新做 allowlist，不相信 renderer 自律**
pre-call literal allowlist 保留，但新增 post-result `OUTPUT_SURFACE_AUDIT`：
- 每一個可讀文字／caption／badge／banner／UI-like panel 分類為 `SOURCE_PRESERVED_TEXT | AUTHORIZED_LITERAL | GENERATED_UNAUTHORIZED_TEXT | UNKNOWN_TEXT_ORIGIN`。
- `SOURCE_PRESERVED_TEXT` 必須有 source-backed pixel/region lineage；whole-frame generative reconstruction 不能只因文字看似與來源相同就冒充 source-preserved。
- `AUTHORIZED_LITERAL` 必須能回指 current `VISIBLE_LITERAL_ALLOWLIST + literal role + carrier binding`。
- `GENERATED_UNAUTHORIZED_TEXT` 或 `UNKNOWN_TEXT_ORIGIN` 在 default-deny public product image 中直接 `VISIBLE_TEXT_PROVENANCE_FAIL / NO_PROMOTION`。
- `FACT_TRUE != RENDER_AUTHORIZED`：即使「第三方鑑定」等 claim 在 Library 有事實依據，只要 current task 未授權為 visible literal，也不得自行生成；truth gate 與 render authority 分離。
- 若 output 把 `NON_RENDERABLE_CONTROL_METADATA`（例如驗收名稱、內部賣點分類、audit label）轉成圖上 caption/icon/banner，標 `CONTROL_METADATA_RENDER_LEAK`。

**D. Artifact promotion attestation｜只有可證明的產物才叫 final**
`FINAL_DELIVERY` 前新增 nested `ARTIFACT_PROMOTION_ATTESTATION`，至少包含：
`FINAL_ARTIFACT_HASH / SOURCE_HASHES / COMMITTED_PLAN_DIGEST / ACTUAL_TOOL_CHAIN / TOOL_CONTEXT_CLASS / NODE_RECEIPTS / TRANSFORM_CHAIN_DIGEST / VISIBLE_TEXT_PROVENANCE_RESULT / PROTECTED_STATE_AUDIT / LOCAL_OBJECT_POSTCONDITIONS / DELIVERY_CONTRACT / TRACE_RECONCILIATION`。
- promotion attestation 必須由 actual receipts/output audit 形成，不得由 planner 自我聲明。
- actual tool chain 與 committed plan 不一致、context class 比 admission 時更弱、存在 unauthorized text、SAME_REAL_CAR/condition regression、或 trace 有 orphan effect，全部 `ATTESTATION_FAIL / QUARANTINE`。
- `TOOL_OUTPUT_EXISTS != OFFICIAL_FINAL`；只有 attestation PASS 的 artifact 才可成為 production winner/baseline。此規則吸收 SLSA/in-toto 類「產物必須能回溯到被授權步驟與輸入」概念，但不建立新的 provenance Owner。

**E. Anti-bloat / failure attribution**
- 最新 Sienta 的「底部四格廣告 banner」不是新增一條「禁止底部 banner」案例規則；歸因 `AMBIENT_CONTEXT_CONSUMPTION + OUTPUT_TEXT_PROVENANCE_FAIL`。
- whole-frame vehicle reconstruction 不是再補更多 SAME_CAR prompt；歸因 `PRODUCTION_SINK_ELIGIBILITY / SOURCE_BINDING_CAPABILITY`。
- 只有當新的 failure 無法被 `tool context class / sink admission / output provenance / artifact attestation` 表達時，才新增 Canonical semantics。

#### Runtime contraction + sealed render egress｜四個 runtime 物件，最後一公尺採 default-deny
為避免 Requirement / profile / packet / effect graph / prompt 在 runtime 形成多份可執行狀態，REAL_CAR 收縮為四個 task-local runtime 物件；既有細部欄位仍保留，但只能作這四個物件的 nested fields / compatibility projection，不再取得獨立 runtime authority。

1. `CURRENT_TASK_SPEC`：GLOBAL 已授權的 current goal / source / scope / hard constraints / output contract。
2. `PRODUCT_VISUAL_SPEC`：Visual 唯一商品視覺 desired state；吸收 `VEHICLE_VISUAL_PROFILE + PRODUCT_SALIENCE_TARGET + composition/photometric/background/watermark visibility projections`。
3. `EXECUTION_DAG`：Execution 只收錄 **目前真正 callable** 的 operation nodes、dependencies、legality 與 node receipt requirement；`REAL_CAR_EFFECT_OP_GRAPH / REAL_CAR_EXECUTION_PACKET` 只作此 DAG 的內部/相容表示，不再是第五、第六份執行狀態。
4. `RENDER_EGRESS_CONTRACT`：由 `EXECUTION_DAG` 的 current READY node + single-use `NODE_EXECUTION_TOKEN` 編譯出的 **per-node** sealed payload；工具端只准讀這一份，一次只執行一個 node。

固定主鏈：
`CURRENT_TASK_SPEC → PRODUCT_VISUAL_SPEC → EXECUTION_DAG(DRAFT) → ANALYSIS_ONLY_PHYSICAL_PLAN_OPTIMIZATION → GRAPH_REDUCTION/PLAN_ADMISSION → COMMITTED_PLAN → READY_NODE/TOKEN → RENDER_EGRESS_CONTRACT(per-node) → ACTUAL_TOOL → NODE_RECEIPT/VERIFY → COMMIT → NEXT_NODE → TRACE_RECONCILIATION → VISUAL_RECONCILIATION`。

**Actual-callable-only DAG**：
- 只有 current environment 實際 exposed + callable 的 stage 才能成為 executable node。
- 若目前只有 whole-frame semantic generation surface，DAG 只能誠實表示該 stochastic node（再加真正可呼叫的 deterministic post-process / verify）；不得因 Canonical 想要 local edit、overlay、delivery adapter 就虛構獨立 node。
- 找不到 matching node 的 requirement 保留為 `UNFULFILLED/CAPABILITY_BOUNDARY` 或 exploratory semantic constraint，不得用假的 stage receipt 補滿。

**`RENDER_EGRESS_CONTRACT` allowlist（最小必要）**：
`EGRESS_SCHEMA_VERSION / TASK_ID / SOURCE_BINDING / VEHICLE_PRESERVE_CONSTRAINTS / COMPOSITION_RENDER_TARGET / PHOTOMETRIC_RENDER_TARGET / BACKGROUND_RENDER_TARGET / LOCAL_OBJECT_RENDER_TARGETS / VISIBLE_LITERAL_ALLOWLIST / OUTPUT_MODE_OR_NATIVE_REQUEST / NEGATIVE_RENDER_CONSTRAINTS`。

**一律不可進 renderer 的 `NON_RENDERABLE_CONTROL_METADATA`**：
`REQUIREMENT_ID/NAMES / VEHICLE_VISUAL_PROFILE LABELS / PRODUCT_SALIENCE/JUDGE CRITERIA / WATERMARK_VISIBILITY CHECK LABELS / privacy-or-compliance rationale / audit findings / witness findings / defect codes / stage names / internal benefits/feature labels / research notes / explanations / historical failure narrative / Sales-Human internal states`。
這些可存在於 `CURRENT_TASK_SPEC / PRODUCT_VISUAL_SPEC / EXECUTION_DAG / VERIFY`，但 egress compiler 必須丟棄，**不得重新措辭成圖上文字、badge、icon caption、標語或 UI panel**。

Readable-text render authority 採 default-deny：
- `VISIBLE_LITERAL_ALLOWLIST` 是唯一可主動產生可讀文字的集合；沒有在 allowlist 的 literal，無論是否「概念正確、對銷售有幫助、來自內部驗收名稱」，都 `NOT_RENDER_AUTHORIZED`。
- `AUTHORIZED_LITERAL_ABSENCE != PERMISSION_TO_INVENT_LITERAL`；當 allowlist 只有 watermark，就不得自行生成其他賣點／服務／說明文字。
- exact watermark / dealer literal 如有真正 callable deterministic overlay，應由 DAG 的 deterministic node執行；否則只能把 literal fidelity 標為 route capability risk，不得以內部 visibility target 擴寫成額外可讀內容。

Egress compile / audit：
`PRODUCT_VISUAL_SPEC + SELECTED_EXECUTABLE_NODE → PROJECT_RENDERABLE_FIELDS_ONLY → APPLY_VISIBLE_LITERAL_ALLOWLIST → DROP_NON_RENDERABLE_METADATA → SCHEMA_VALIDATE(DEFAULT_DENY) → EGRESS_DIFF_AUDIT → TOOL_CALL`。
- egress diff 必須證明：Visual desired state 的必要 render targets 沒掉、internal metadata 沒漏、visible literal set 沒擴張、source binding / route scope 沒被改寫。
- unknown field / extra visible-text intent / control-metadata leakage → `RENDER_EGRESS_SCHEMA_FAIL / BLOCK_PRODUCTION_CALL`。
- 工具前最後 input 若不是同一 `RENDER_EGRESS_CONTRACT` projection，標 `RENDER_EGRESS_CONSUMPTION_FAIL`。
- 平台若無法證明 hermetic context consumption，最多標 `SEALED_EGRESS_SOFT_ENFORCEMENT`；不得宣稱完全隔離，但仍必須用最小 egress 避免主動把控制 plane metadata送入 renderer。

REAL_CAR live image action 不得讓 Visual / Execution / image adapter 在出圖當下重新從 Canonical、project state、history、memory 或舊案例拼裝設定。GLOBAL current task state 先收斂成 `CURRENT_TASK_SPEC`，Visual 只產生一份 `PRODUCT_VISUAL_SPEC`，Execution 只產生一份 actual-callable `EXECUTION_DAG`；**image/render tool adapter 最終只能消費 sealed `RENDER_EGRESS_CONTRACT`**。

固定：
`GLOBAL_CURRENT_TASK_SPEC → PRODUCT_VISUAL_SPEC → EXECUTION_DAG/ROUTE_LEGALIZATION → RENDER_EGRESS_CONTRACT → EGRESS_AUDIT → ACTUAL_TOOL → RECEIPT`

至少解析：
- `REQUIREMENT_INDEX / REQUIREMENT_PROJECTION_MAP`：本輪所有 active `REQUIREMENT_ID` 與 Visual / Execution / Verification projection lineage；
- `EFFECT_OP_INDEX / EFFECT_DEPENDENCY_DAG / LEGALIZATION_STATUS`：每個 requirement projection 對應哪一個 typed effect op、前後依賴與 production legality；
- `OP_RECEIPT_REQUIREMENTS`：哪些 stage 必須實際產生 artifact/receipt 才能視為執行完成；
- `SOURCE_VEHICLE_REFERENCE / VEHICLE_IDENTITY / PROTECTED_STATE / CURRENT_DELTA`；
- `VEHICLE_VISUAL_PROFILE / PRODUCT_SALIENCE_TARGET / HERO_VIEW_BAND / CAMERA_HEIGHT_BAND / PERSPECTIVE_AGGRESSION_CAP / SUBJECT_FRAME_OCCUPANCY_BAND / BOTTOM_CLEARANCE_BAND / BACKGROUND_FAMILY_RANKING / PRODUCT_EDGE_SEPARATION_TARGET / WATERMARK_VISIBILITY_TARGET`；
- `COMPOSITION_ACTION_CLASS / COMPOSITION_TARGET / SPATIAL_CONTROL_LEVEL / VIEWPOINT_STATE / GROUND_CONTACT_ANCHOR`；
- `FINAL_DELIVERY_SIZE / GENERATOR_REQUEST_SIZE_OR_MODE / DELIVERY_ADAPTER / OUTPUT_COUNT / DELIVERY_SURFACE`；
- `WATERMARK_STATE + LITERAL + TARGET_ROLE / LITERAL_RENDER_REQUIREMENT / LITERAL_RENDER_ROUTE`；
- `PLATE_COVER_REQUIRED + PLATE_COVER_CONSTRUCTION`；
- `SCENE_STATE / BACKGROUND_DECISION`；
- `PHOTOMETRIC_OR_CONTOUR_STATE`；
- `DEALER_SIGNAGE_STATE / ALLOWED_LITERALS`；
- `AUTHORIZED_EMBEDDED_LITERALS`；
- `ROUTE_CONTROL_SCOPE / SOURCE_BINDING_REQUIREMENT`。

每個欄位記錄 `SEMANTIC_RULE_KEY / RESOLVED_VALUE / SOURCE_AUTHORITY / SOURCE_REVISION / REQUIREMENT_ID(optional when domain-only) / PROJECTION_ROLE`。同 key 若解析到兩個可執行值，直接 `REAL_CAR_RULE_COLLISION / BLOCK_IMAGE_CALL`，禁止 Execution 自選、禁止 majority vote、禁止依歷史成功率猜配套。若 task-derived 欄位彼此無法回指同一 requirement lineage，標 `REAL_CAR_REQUIREMENT_LINEAGE_BREAK / BLOCK_IMAGE_CALL`。

任何 current user correction 或 REAL_CAR Canonical 更新只要影響本次 packet 的 semantic key：
`INVALIDATE_PACKET → RECOMPILE → PRECALL_DIFF_AUDIT`。不得把新版值 patch 到舊 packet 後繼續使用其餘舊 context。

Precall 必須能回答：**「這台車的 current `VEHICLE_VISUAL_PROFILE` 是什麼；hero angle/機位/透視 aggression、主體佔比與下緣 band、product edge separation、背景 candidate ranking、浮水印能見度 target 各自如何由 current source/model/delivery role 推導；這一次最終交付尺寸、generator request、delivery adapter、浮水印、遮牌、背景、光影／輪廓、店家文字各自到底綁哪一個值？每個 required effect op 由哪個 callable route 執行、write scope 多大、是否合法、完成後要留下什麼 receipt？」** 無法唯一回答，或任何 HARD op 未 legalize，即不得把該計畫當 production-ready。

### 4A0.0 Delivery/native-size split + exact-literal route｜生成能力與最終交付契約分層
`FINAL_DELIVERY_SIZE` 是使用者／delivery surface 的成品要求；`GENERATOR_REQUEST_SIZE_OR_MODE` 是當前 callable route 真正能接受的生成規格。兩者不得再用單一 `OUTPUT_SIZE` 混成同一件事。

固定：
`FINAL_DELIVERY_CONTRACT → ROUTE_NATIVE_SIZE_CAPABILITY → GENERATOR_REQUEST → VISIBLE/RAW_RESULT → DELIVERY_ADAPTER → FINAL_ARTIFACT_AUDIT`。

規則：
- 若 final delivery 要求某尺寸，但 generator 不支援該 exact native size，先用 route 合法且不破壞構圖的最接近規格生成，再由 deterministic `DELIVERY_ADAPTER` 做 crop/pad/resize；只有 adapter 後的成品才接受 `FINAL_DELIVERY_SIZE` 驗收。
- 不得因 raw generator output 是正方形，就宣稱已滿足 exact 1080×1080；也不得因 final delivery 是 1080×1080，就虛構 generator 本身能直接請求該尺寸。
- 若 delivery adapter 會造成裁車、非等比拉伸、可見品質劣化或違反 crop safety，標 `DELIVERY_ADAPTER_FAIL`，不得以尺寸正確掩蓋 Visual regression。
- 對 phone、watermark、dealer identity 或其他要求 exact readable literal 的 activated object，先判 `LITERAL_RENDER_REQUIREMENT=EXACT | GENERATIVE_TOLERANT`。`EXACT` 時，若 generative route 沒有 matching-scope literal fidelity evidence，優先使用目前 callable 的 deterministic text/overlay/composite stage；沒有可用 route 就回報 `LITERAL_RENDER_CAPABILITY_BOUNDARY`，不得靠更多 prompt 假裝已取得精準文字控制。
- `SEMANTIC FACT PRESENT != RENDER AUTHORITY`；年份／版本／售價等 facts 即使正確，仍只有在 `VISUAL_TEXT_AUTHORITY=EXPLICIT` 且 literal 被 current task 授權時才可進 render path。

### 4A0.1 Failure attribution for visible drift
出圖後若發生「修 A 跑 B／遮牌有了但材質錯／浮水印有了但尺寸沒做／某個 downstream requirement 漏掉」，依 requirement + effect graph 比對：
- requirement/core 或 resolved packet 已是錯值／舊值 → `REAL_CAR_CURRENT_STATE_FAIL`；
- requirement projection 正確，但 effect op 分類、dependency、hardness 或 route legality lower 錯 → `EXECUTION_LOWERING/LEGALIZATION_FAIL`；
- effect graph / packet 正確，但工具前 input 或 artifact chain 沒消費同一 op → `EXECUTION_PACKET_CONSUMPTION_FAIL`；
- required op 在 plan 中存在但沒有實際 stage receipt/output artifact → `EXECUTION_PATH_OMISSION`；
- op、input、route、receipt 都正確，但 visible postcondition仍沒做到或 write scope 超出 envelope → `IMAGE_ROUTE_CONTROLLABILITY_FAIL`；
- visible result 正確但 verifier/closure 判斷錯 → `VERIFICATION_FAIL`。

只有在 current-state、lowering/legalization、consumption、path omission 都排除後，才把主要根因歸到生成隨機性／route control ceiling。

## 4A. Current-task binding before any image call
任何 REAL_CAR image generation/edit tool call——包含 production、pilot、research experiment、fresh validation——在工具呼叫前都必須先通過 GLOBAL `CURRENT_TASK_CONTRACT.EFFECT_AUTHORIZATION`，再建立並消費 `CURRENT_TASK_BINDING_PACKET`；不得只靠「這個話題大概在做哪台車」、domain owner 的 action proposal、上一張生成圖或歷史案例自行延續。

`GLOBAL_EFFECT_AUTHORIZATION_PASS → CURRENT_TASK_BINDING_PACKET_PASS → DOMAIN_PRECALL_GATES → IMAGE_TOOL_CALL`

`OWNER/ROUTE_SELECTED != IMAGE_CALL_AUTHORIZED`。若目前只是測試/分析出圖邏輯本身，而 test target 不需要真實 image call，應停在邏輯/contract evidence；不得為了「測試」這個字自行生成一張圖。反之，若 current user/task/validation contract 明確授權一個實際 pilot，則仍須完整通過下列 task binding、foreign-context 與 route eligibility gates。

`CURRENT_TASK_BINDING_PACKET` 自本 revision 起只保留為 compatibility view：它不得建立與 `CURRENT_TASK_SPEC / PRODUCT_VISUAL_SPEC` 平行的語意狀態；下列欄位應被映射進上述兩物件，再由 `EXECUTION_DAG → RENDER_EGRESS_CONTRACT` 執行。

`CURRENT_TASK_BINDING_PACKET` 至少包含：
- `REQUIREMENT_CORE / REQUIREMENT_INDEX`：本輪每個 active requirement 的 `REQUIREMENT_ID + SEMANTIC_OWNER + NORMATIVE_INTENT + FULFILLMENT_CRITERIA + PROTECTED_STATE + PARENT/CHILD`；後續欄位只能作其 bounded projection。
- `SOURCE_VEHICLE_REFERENCE`：本任務真正的來源車／來源影像集合；最新生成圖不得自動取代來源車 authority。
- `VEHICLE_IDENTITY`：車型／世代／車色／主要外觀 identity。
- `VEHICLE_VISUAL_PROFILE / PRODUCT_SALIENCE_TARGET`：依 §3.5 由 archetype prior + current model/source geometry + view/color/material + delivery role 編譯出的 task-local adaptive profile；包含 hero view/camera/perspective bands、frame/bottom-space bands、edge separation、background ranking 與 watermark visibility target。
- `LOCKED_LITERALS`：本任務已確認且畫面需要保留的 dealer / phone / watermark / plate 等。來源 literal 的事實 identity 與最終是否可讀，必須分開記；不得因為知道來源車牌號就推論成輸出必須顯示該號碼。
- `OBJECT_ACTIVATION_BINDINGS`：所有 conditional visual object 必須明確綁定 `OBJECT + TARGET_ROLE + REQUIRED_STATE + RENDER_STATE`。Domain standard 只回答『怎麼做』；task activation 才回答『這次要不要做、套到哪個物件』。
- `CURRENT_SCENE_STATE`：背景是 unresolved candidate、selected scene，還是 explicit change request。
- `CURRENT_DELTA`：這一輪真正要改什麼；未列入 delta 的 identity/brand/scene 不得自行重置。
- `COMPOSITION_BINDING`：若本輪涉及構圖／相對位置／角度，綁定 `ACTION_CLASS + COMPOSITION_TARGET + VIEWPOINT_STATE + SPATIAL_CONTROL_LEVEL + CROP_SAFETY + GROUND_CONTACT_ANCHOR`；未涉及則明確 `PRESERVE_BASELINE_COMPOSITION`。
- `CURRENT_COMPONENT_RATIONALE`：本輪新增/更換的背景、光線、構圖或其他 component 為什麼預期會讓 final visual/sales outcome 變好；不得空白或只寫「符合品牌/比較完整/工具可生成」。

### Precall binding gate
- 第一關先確認 GLOBAL `CURRENT_EFFECT_AUTHORIZATION` 對本次 image call、target、scope 仍有效；沒有或超 scope 直接 `BLOCK_IMAGE_SIDE_EFFECT`，不得進 route selection。
- 在 route dispatch 前建立並驗證 `RENDER_CONTENT_MANIFEST`；只有 `VISUAL_SCENE_CONTENT + RENDERABLE_LITERAL_SET` 可取得 visible-render authority。`CONTROL_METADATA / VALIDATION_METADATA` 若仍以可讀 prose 形式存在於 production egress，直接 `BLOCK_IMAGE_CALL_OR_MARK_EXPLORATORY_ONLY`。
- 再確認實際執行上下文仍指向 `SOURCE_VEHICLE_REFERENCE`，不是 last-generated image 或一般類別概念。
- 若當輪工具路徑無法可靠帶入來源車／current task context，禁止用「全畫面重新發明」冒充 production；改走較 source-anchored 的 edit/composite/reference route，或明確回報能力邊界。
- `BACKGROUND_UNRESOLVED` 只代表場景仍可探索，不代表 vehicle identity / dealer identity / literals 可一起重新抽。
- 若 dealer signage 出現，只能使用 current task 已確認 dealer identity；不得自行生成其他車商品牌。
- Conditional object 在工具呼叫前必須完成 `DOMAIN_STANDARD → TASK_ACTIVATION → TARGET_ROLE → RENDER_STATE` 解析。只知道 standard、但沒有 activation，不得自行擴張到所有相似物件；activation 已明確為 REQUIRED 時，也不得因 source literal 存在而退回未啟用狀態。
- 若 `CURRENT_DELTA` 含 composition：先判 `REFRAME/ZOOM` 是否足以達成；足以時不得為了「更有衝擊感」自動升級成 `VIEW_CHANGE`。
- 若 action 是 `SUBJECT_RELATIVE_SHIFT_SCALE` 或 `VIEW_CHANGE`，route 必須有 matching-scope evidence 能處理 identity + local effects；只有 broad text prompt 而無 spatial control receipt 時，只能標 `SEMANTIC_ONLY/EXPLORATORY`，不得承諾精準位置／角度。
- 若使用者只要求構圖微調而 current route 會高概率重畫整車，必須先評估 deterministic crop/scale/translate 或其他較 source-anchored route；無適配 route 時回報 capability boundary，不用 whole-frame 重抽碰運氣。


### Foreign-context quarantine｜Topic Firewall 的影像域負向隔離
這不是第二套獨立防火牆或新的 authority。它是 `TOPIC_FIREWALL_RUNTIME / CURRENT_TASK_CONTRACT` 在 REAL_CAR domain 的負向 context check，由 `CURRENT_TASK_BINDING_PACKET` 消費。

`CURRENT_TASK_BINDING_PACKET` 除了正向綁定，也必須做負向隔離：任何來自其他車款、其他任務、舊案例、history/memory hint 的可辨識 object/literal/brand cue，若不在 current task authority 或 current user request 內，視為 `FOREIGN_CONTEXT`，不得被 production route 消費。

Precall 固定做：
`CURRENT_EFFECT_AUTHORIZATION → CURRENT_ALLOWED_CONTEXT → FOREIGN_CONTEXT_SCAN → QUARANTINE_NONCURRENT_CUES → DOMAIN_PRECALL_GATES → TOOL_CALL`

Post-result 若出現 current task 從未授權的其他車款展示牌、品牌字樣、專案專屬物件或其他明顯 foreign cue，直接判 `CROSS_TASK_CONTAMINATION`；不得只做局部擦字後沿用整張結果，亦不得升為 parent/baseline。這種 fresh evidence 應回報 GLOBAL 做同回合 scope/authority repair，不等待使用者再次下「修正」。

### Post-result catastrophic drift check
結果一回來先檢查：`SAME_VEHICLE? / SAME_TASK_BRAND? / LOCKED_LITERALS_NOT_CONTRADICTED?`。
任一 core binding 變成另一台車、另一品牌或明顯衝突 literal，直接標 `CATASTROPHIC_TASK_DRIFT`，不得進入一般美感比較或把該圖當新 baseline。

注意：平台影像工具的結果可能會在工具回傳時立即顯示給使用者；本治理無法宣稱能在 UI 層物理隱藏所有失敗輸出。能做的是在 precall 最大化 binding，並在結果回來後立即判定、禁止錯誤結果污染後續 state。

## 5. Background and composition
車是主體；背景服務車。
`VEHICLE_PRIMARY → SALES_OUTCOME → REALISM/TRUST → SCENE_SUPPORT → DEALER_IDENTITY`

`VEHICLE_PRIMARY` 必須反映在**實際視覺 salience**，不能只存在文字目標：
- 車應取得第一眼 fixation 與主要面積/對比/清晰度/構圖權重。
- 店招、電話、建築、燈光、背景車與場景紋理只提供可信場景與識別，不得成為第一視覺主角。
- 背景不需要被機械式模糊或變暗；重點是降低競爭性 salience，同時保留真實環境脈絡。
- 若一張圖更像『展示車行環境裡有一台車』而不是『展示這台車，車行只是場景』，直接判 `SUBJECT_HIERARCHY_FAIL`。

背景類型預設開放，不因歷史連續使用自動升格。


### 5.1 Background dual gate｜語意適配與物理融入分開過關

任何新背景/場景候選必須依序通過兩個獨立 gate：

1. `SCENE_FIT_GATE`：`WHY_THIS_CAR_HERE / WHY_NOW / BUYER_OR_USE_OCCASION / VEHICLE_FIRST / MATERIAL_UPLIFT_VS_SOURCE`。只「合理、漂亮、像車行」不等於 hero value；當 `SURFACE_VISUAL_MODE=USED_CAR_INVENTORY_HERO` 時，另必須符合 §3.5 C1 `INVENTORY_PRODUCT_DOMINANCE_GATE`，避免 scene-fit 被誤讀成可以做品牌形象式大留白／完整環境敘事。
2. `PHYSICAL_FIT_GATE`：`PERSPECTIVE / SCALE / GROUND_CONTACT / LIGHT_DIRECTION / CONTACT+CAST_SHADOW / REFLECTION / GLASS / NEAR_FIELD_COUPLING / DEPTH+GRAIN COHERENCE`。語意再合理，只要物理融入破裂就不得 promotion。

`SCENE_FIT_PASS + PHYSICAL_FIT_FAIL = REJECT`；`PHYSICAL_FIT_PASS + GENERIC_SCENE = REJECT_OR_KEEP_SOURCE`。背景提升不得抵銷 source-instance/condition truth regression。

### Background selection / stability
- `DEALER_IDENTITY != DEALER_BACKGROUND_REQUIREMENT`：`SHOWROOM_REQUIRED_DEFAULT=FALSE`。店名、電話、品牌識別不代表背景必須是車行門面；但展間／車行門面也不被禁止，只要通過 `COMPONENT_VALUE_GATE`，能比其他候選更實質提升整體視覺與銷售價值即可。若 current acquisition brief 有 `TARGET_BUYER / PURCHASE_OR_USE_ANCHOR`，背景候選優先用它建立生活用途／購買情境聯想，再與車色、角度、光線、grounding 一起過 gate；不得把「某車種通常配某場景」硬鎖成模板。
- `ANTI_REPETITION != POSITIVE_SCENE_JUSTIFICATION`：避免同一業務／同一批車長期使用相似背景可以是換景動機，但「不要重複」本身不是任意新背景的正向選擇證據；替代場景仍必須說明為什麼更適合這台車／這張圖。
- 背景選擇必須服務主車與銷售目標；先提出相對於這台車、這個角度、車色、光線、買家/use case 與銷售用途的 `BACKGROUND_VALUE_HYPOTHESIS`，再生成/選擇。不得用『每次重新猜一個場景』代替 selection。
- Hero background 另外必須通過 `SCENE_OCCASION_FIT / CONTEXTUAL_INEVITABILITY`：回答 `WHY_THIS_CAR_HERE? / WHY_NOW? / WHAT_USE_CASE_OR_BUYER_LIFE? / WHAT_IS_THE_PHOTOGRAPHIC_REASON?`。若把主車替換成任意同級 generic vehicle，場景意義幾乎不變且沒有其他強 value reason，標記 `GENERIC_SCENE_FIT / HERO_VALUE_INSUFFICIENT`。這是通用 selection gate；§3.5 的 archetype/model profile 只能提供 candidate ranking prior，不是固定車種→場景 mapping，也不能取代本 gate。
- 車行／展間場景預設可提供 `TRANSACTIONAL / INVENTORY / DEALER-TRUST` 價值，但不因此自動具備 `HERO_AD_BACKGROUND` 資格；必須與其他場景一樣通過 occasion-fit + material-uplift gate。
- `EXPERIMENTAL_CONTROL_SCENE != SELECTED_SCENE`：若為隔離非背景變因而暫時固定場景，必須標成 control-only；不得因連續重複使用自動升格為 preference / winner / baseline / `SCENE_LOCKED`。測試結束後，若沒有 explicit selection / promotion，scene state 回到 unresolved。
- 若當輪主要在修車身、亮度、主體權重、文字或其他非背景變因，**只有已正式 selected/promoted 的背景**才預設維持不變；control-only scene 只是實驗工具，不構成背景選擇結果。
- 背景只有在三種情況可主動更換：`USER_REQUESTS_CHANGE`、`CURRENT_BACKGROUND_FAILS`、`DELIBERATE_BACKGROUND_COMPARISON`；但 unresolved/control-only state 本身不算 locked，因此可依新的高價值 hypothesis 進行 deliberate comparison。
- `DELIBERATE_BACKGROUND_COMPARISON` 必須有明確候選理由與比較基準；不是無控制變因重抽。
- 一旦某背景由使用者明確選定，或 post-render 通過 background selection/promotion，才可設 `SCENE_LOCKED=TRUE`。

`HERO_BACKGROUND_REPLACEMENT_BURDEN`：原圖/current baseline 是 incumbent；新背景若只是「合理、沒不好、有車行感、比較不重複」，不足以取代 baseline。只有在 fresh output 後能證明 first-glance / aesthetic / trust / sales net value materially higher，才可 promotion。

不得把某次 scene-family screening、3-family gate、winner-before-refine 等舊實驗流程當成全域 hard rule；scene lock 只在當前任務已選定背景後成立，不是永久背景偏好。

## 6. Literals / factual visual content
已驗證店名、電話、浮水印、車牌格式、門牌格式等屬 conditional correctness authority：
- 當畫面需要或已出現時必須正確。
- 不代表每張圖都必須強迫出現所有物件。
- 不得生成隨機可讀電話、門牌、車牌或錯誤店家身份。

### 6A. Readable-literal role / signage contract
REAL_CAR 的可讀文字不能只驗證「字串對不對」，還必須驗證**它出現在正確角色與載體**。

固定解析：
`READABLE_LITERAL → AUTHORITY/WHITELIST → TARGET_ROLE → CARRIER → REQUIRED? → RENDER → ROLE/SALIENCE_AUDIT`

- 每個可讀 literal 必須先綁定角色，例如 `DEALER_NAME`、`DEALER_PHONE`、`WATERMARK`、`ADDRESS_PLATE`、`OPTIONAL_SALES_CLAIM`；字串正確但角色錯誤仍是 FAIL。
- `WATERMARK` 是主車圖層／玻璃／車身上的識別角色；除非 current user 明確改變用途，**不得遷移到店招、建築招牌、地址牌或背景看板**。`WATERMARK_LITERAL_PRESENT != WATERMARK_ROLE_CORRECT`。
- 店招若啟用，只能消費 current task 明確允許的 dealer literals。未列入 whitelist 的口號、服務項目、保固、貸款、收車、買賣等可讀宣稱，預設 `NOT_AUTHORIZED_TO_GENERATE`；不得因「看起來像車行」自行補滿。
- `未指定 ≠ 可以自由生成文字`。對 truth-sensitive/readable background text 採 `WHITELIST_ONLY`；需要新增 literal 時，必須有 current user/task authority 或 verified authority。
- 同一 literal 可以在不同角色重複，只有 current task 明確允許才可；否則像 watermark 同時出現在玻璃與店招，標 `ROLE_DUPLICATION / CARRIER_MIGRATION`。
- 店招／電話是背景支援資訊，不得因字體、尺寸、對比、位置或資訊密度取得比主車更高的第一眼 salience。若先看到招牌而不是車，即使文字都正確仍 `SUBJECT_HIERARCHY_FAIL`。
- 店招不得因為「店名＋電話是 verified」就自動擴張成巨大主視覺；carrier 尺寸與資訊量仍受 `VEHICLE_PRIMARY` / `COMPONENT_VALUE_GATE` 約束。
- 店招資訊層級固定拆成角色，而不是把所有正確 literal 做成同等權重：`DEALER_NAME = PRIMARY_IDENTITY`、`DEALER_BUSINESS_POSITIONING = SECONDARY_CONTEXT`（只有 current task 明確授權時才可出現）、`DEALER_PHONE = TERTIARY_CONTACT`。電話不得與店名等大、等重或更搶眼；若只有店名＋電話兩項已授權資訊，不得為填滿大 carrier 而放大電話，應縮小／簡化招牌 carrier。
- 當 current task 已授權業務定位 literal 時，完整主招牌優先採 `DEALER_NAME > BUSINESS_POSITIONING > PHONE` 的資訊階層；業務定位用來回答「這家店做什麼」，電話只回答「怎麼聯絡」。不得為了補層級自行發明未授權的保固、貸款、認證、服務或收車宣稱。
- `DEALER_BUSINESS_POSITIONING` 是 **conditional**，不是公共商品圖 hard requirement。只有 `DEALER_SIGNAGE_STATE=ACTIVE + CURRENT_TASK_AUTHORIZED + PLAUSIBLE_DEALER_FASCIA/SUPPORT_CARRIER` 三者同時成立才可 render；任一不成立就 `OMIT`。因此「高價收車／中古車買賣」等業務定位不得因歷史常用、品牌資料已知或畫面留白而自動出現。
- 當 current brand/task 明確綁定「店名旁的支援資訊模組」時，優先 layout 為 `MAIN_IDENTITY_BLOCK(DEALER_NAME) + ADJACENT_SUPPORT_STACK(BUSINESS_POSITIONING ABOVE PHONE)`；business positioning 在上、phone 在下，兩者均 subordinate to dealer name。這只規範**店招已被選用時**的資訊結構，不會反向要求 scene 必須出現店招。`WATERMARK` 永遠不得進入此 support stack。
- `ADDRESS_PLATE` 必須同時通過 `ADDRESS_LITERAL + ADDRESS_OBJECT_ROLE + PHYSICAL_CARRIER`。門牌／地址牌屬**建築物地址識別物件**，預設只允許固定在該地址所屬建築物的外牆、柱面、門框／入口附近等合理建築載體；不得掛在電線桿、號誌桿、路燈桿、樹木、臨時立牌、車體或其他非建築地址載體上。
- 字串與版式正確但 carrier 錯誤仍是 `ADDRESS_PLATE_CARRIER_MISMATCH / FAIL`；不得因地址內容為 verified 就放行錯誤物理位置。
- 若 current task 未要求地址牌，地址資訊維持 conditional：可不出現；但一旦出現，就必須先解析 `ADDRESS_PLATE → TARGET_BUILDING → ALLOWED_BUILDING_CARRIER → RENDER → CARRIER_AUDIT`。

Fail conditions：
- verified literal 出現在錯誤角色／載體；
- watermark 跑進店招或背景看板；
- 生成 whitelist 外的可讀銷售宣稱／服務項目；
- 店招文字量、尺寸或對比使背景搶過主車；
- `DEALER_PHONE` 與 `DEALER_NAME` 同級或更高 salience，或把「店名＋電話」兩項硬撐成巨大完整主招牌而缺乏合理資訊層級；
- 用正確電話／店名掩蓋其他未授權文字 overgeneration。
- 門牌／地址牌掛在電線桿、路燈桿、號誌桿、樹木、車體或其他非所屬建築載體。

Authority / precedence：
`CURRENT_USER_OVERRIDE > CURRENT_TASK_LITERAL_ROLE_BINDING > CURRENT_TASK_LITERAL_WHITELIST > VERIFIED_DOMAIN_AUTHORITY > HISTORY/MEMORY_HINT`.


### 6A.1 Watermark human-visibility / salience contract
`WATERMARK` 除了 literal/role/career 正確，還必須滿足 §3.5 `WATERMARK_VISIBILITY_TARGET`。

**Exact literal grammar / no inferred decoration：**
`AUTHORIZED_LITERAL_TOKENS → EXACT_SEQUENCE → AUXILIARY_GLYPH_ALLOWLIST → CARRIER_LAYOUT → RENDER`。
- `AUXILIARY_GLYPH_ALLOWLIST` 預設 `NONE`。只有 current user/task 明確把 icon、斜線、加號、破折號、分隔點或其他符號列為 visible literal，才可渲染。
- 使用者以自然語言寫「電話+名稱／電話＋名稱」時，`+ / ＋` 預設是**組合運算語意**，不是要印出的字元；若 current authorized watermark 是兩個 token 串接，輸出只允許 token 本身與最低必要 layout whitespace，不得自行插入電話圖示、`/`、`｜` 或裝飾 punctuation。
- `LITERAL_CONTENT` 與 `LAYOUT_WHITESPACE` 分離；換行、間距可因 carrier 調整，但不得藉 layout 改變字串 identity。
- tool egress 若不能限制 extra glyph，該 route 對 exact watermark 只能標 `SOFT_EXPLORATORY`；不得把 generator 自行補的符號視為設計美化 PASS。

固定驗收：
`EXACT_LITERAL → AUTHORIZED_VEHICLE_CARRIER → FINAL_SIZE_READABILITY → THUMBNAIL_READABILITY(if applicable) → VEHICLE_RELATIVE_SALIENCE → PASS`。

- `WATERMARK_PRESENT != WATERMARK_VISIBLE`；字存在但因玻璃過暗/過亮、反射、透視、縮圖或局部紋理而難讀，仍 FAIL。
- `WATERMARK_VISIBLE != WATERMARK_SALIENCE_PASS`；可讀但搶過主車、像大型貼紙或破壞車體材質，也 FAIL。
- 允許依 current carrier 做最低必要的 size/contrast/opacity/outline-shadow/placement adaptation，但不得改 literal、不得跨出授權 carrier role。
- exact readable watermark 優先由 deterministic overlay/composite effect 執行；若只有 generative route，必須依 §4A0.E 標示其 literal/locality capability，不得把可讀性當成 prompt 必然結果。

## 6B. Plate-cover visual standard (REAL_CAR domain)
GLOBAL classification: `DOMAIN_LEVEL / REAL_CAR_VISUAL_OBJECT_STANDARD / CONDITIONAL_DEFAULT_WHEN_PLATE_COVER_IS_USED`.
This is a reusable REAL_CAR visual standard whenever the current task or §2C `PRODUCT_IMAGE_BUNDLE` activates official-plate covering, unless the current user/task overrides it.

### Current construction｜唯一現行版本：黑色布套遮蓋
`PLATE_COVER_CONSTRUCTION = BLACK_CLOTH_SLEEVE`。

Plate cover 仍拆成 `HOW_TO_COVER` 與 `WHETHER/WHERE_TO_COVER`；是否啟用由 current task `OBJECT_ACTIVATION_BINDINGS` 決定，§2C 的 public-facing default activation 也必須先編譯成該 task-local binding，不建立第二套 activation authority。

固定解析：
`PLATE_SOURCE_IDENTITY → TARGET_ROLE_RESOLUTION → PLATE_COVER_REQUIRED? → BLACK_CLOTH_SLEEVE | NORMAL_PLATE_POLICY`

- 若 `PRIMARY_SUBJECT_PLATE_COVER_REQUIRED=TRUE`，主車正式車牌必須 `COVERED / ALPHANUMERIC_HIDDEN`。
- 對 §2C public-facing exterior bundle，只要主車正式牌在 final composition 可辨識，`PRIMARY_SUBJECT_PLATE_COVER_REQUIRED` 必須編譯為 `TRUE`；若黑布 stage 未執行／未驗證，不得降級成「車牌可讀也算成品」。
- `PLATE_COVER_TARGET_ROLE=PRIMARY_SUBJECT_ONLY` 時只套主車；背景車不得繼承。
- task 未啟用遮牌時，不強迫所有車遮牌。

Required construction：
- 使用**黑色布套／柔性黑布**自然套覆正式車牌的可讀英數區域；視覺上必須是布料，不是硬卡紙、塑膠牌、數位黑矩形或 replacement plate。
- 布套應順著原車牌／牌架位置與透視貼合，可有自然皺褶、布料張力、柔軟垂墜或邊緣起伏；不得呈現硬直板材質。
- 車牌英數需被完整遮住；牌架、安裝位置與保桿結構仍保持合理，不因遮牌而改造車體。
- **不再要求白色金屬牌邊完整露出、不使用黑卡紙、不使用上下夾子作預設、不自動印車名／品牌文字。** 只有 current user/task 明確要求文字或固定方式時才另行啟用。
- 尺寸只覆蓋車牌／牌架合理區域，不得變成大型廣告牌。
- 光影、接觸陰影、透視、布料材質與當前畫面一致。

Fail conditions：
- current task 已要求遮牌但正式牌號仍可讀；
- 仍生成舊版 `black paper/card + clips`；
- 用 rigid black plate / digital rectangle / oversized board 取代布套；
- 布套漂浮、透視錯誤、遮到不合理車身區域；
- 未授權自行加入車名、品牌或其他可讀文字；
- 主車沒遮、反而把遮牌規格套到背景車。

### Supersession / no fallback
`BLACK_PAPER_CARD_WITH_CLIPS`、`TWO_CLIP_TOP_BOTTOM`、`MODEL_NAME_ON_CARD` 與「白牌邊必須完整露出」均為 `SUPERSEDED_NON_EXECUTABLE`。它們可留在 history/provenance，但不得由 REAL_CAR、project state、automation、Memory 或 Execution fallback 重新取得 live authority。

Authority / precedence：
`CURRENT_USER_OVERRIDE > CURRENT_TASK_OBJECT_ACTIVATION > CURRENT_TASK_VEHICLE_IDENTITY > THIS_CURRENT_DOMAIN_STANDARD > HISTORY/MEMORY_HINT`.
Task state 只需 reference `PLATE_COVER_STANDARD=INHERIT_REAL_CAR_DOMAIN` 與 activation/target，不複製 construction，以避免未來再次產生平行版本。

## 7. Communication
使用者不必知道 route / owner / receipt / canonical。
- 出圖：直接執行最適方法。
- 分析：先講可見結果。
- 修正：直接修可控制項；無法控制就明講。
- 不把內部工具選擇丟回使用者。

## 8. Task-local isolation
任何單張 defect、current stage、next action、pilot、route result、scene rejection、mask failure 都只屬 task-local evidence，不得寫進此 Canonical 或永久 Memory。

Live current-task authority **只來自 GLOBAL `TOPIC_FIREWALL_RUNTIME / CURRENT_TASK_CONTRACT` 的本次 task binding**，不得由固定 project-state 檔案自動取得。`/edit-fb-car-carousel_專案狀態.md` 是可重用的 **project-scoped state store**，只有當 current firewall 明確綁定 matching `PROJECT_ID/TASK_ID/SCOPE` 時，才可消費其中最小必要 current section；未綁定、換話題、換車、或 scope 不匹配時，一律 `REFERENCE/HISTORY_ONLY`，不得提供 source/effect authority。

`PROJECT_STATE_PRESENT != CURRENT_TASK_BOUND`；`PROJECT_STATUS_ACTIVE != LIVE_AUTHORITY`。所有 `(1)`、`_v*`、`snapshot`、舊副本即使自稱 CURRENT 也只能作 history/evidence。任務結束或切換後，下一個 task 必須由 firewall 重新 binding，不能靠 project file 的 `STATUS: ACTIVE` 延續。

執行時更進一步固定：`PROJECT_STATE/HISTORY/CANONICAL_RAW_TEXT != EXECUTOR_INPUT`。它們只能作 snapshot compiler 的候選來源；一旦 `REAL_CAR_EXECUTION_PACKET` 產生，Execution 不得再直接讀 raw project/history 規則補值。

## 9. Delivery bar
輸出尺寸/格式屬 `CURRENT_TASK_OUTPUT_CONTRACT`：只有 current user、current delivery surface 或已採用的 domain delivery standard 能建立 hard output requirement；Visual research/runtime 不得自行發明全域尺寸預設。若本次明確是 FB 商店／粉專方形車圖，且 current task 未另行覆寫，使用 `1080×1080 / 1:1`；其他用途依 current task contract。

成品只有在以下條件成立才可稱成功：
- 使用者要求的主體/成品真的存在。
- 同車 identity / 主要幾何無 material regression。
- source-visible condition truth 未被自動美容成新品；新視角中可見區域的使用狀態仍可信，且不得在不可見新表面憑空發明磨損。
- 若為新背景／新視角，輪廓分離必須依 target scene 成立：車體 form readable、玻璃/反射/陰影/接地互相支持，無 halo/outer glow/fake rim。
- 第一眼主體 hierarchy 正確：先看到車，背景/招牌不搶主角。
- 第一眼沒有明顯 AI 崩壞或合成穿幫。
- 3D / 接地 / 光影合理。
- truth-sensitive literal / fact 沒有重大錯誤。
- 實際成品可用，而不是只有中間步驟或內部路徑成功。


### 4.3 Platform invocation truth supersedes fictional route blocking
The execution contract must not claim capabilities that the current chat tool plane does not expose. For an explicit image-generation request, current platform/system routing can require the visible image generator. REAL_CAR Canonical cannot physically substitute an unavailable deterministic/local renderer or guarantee that an ineligible production route will never be invoked.

Therefore:
- `ROUTE_INELIGIBLE` in §4.2 means **not eligible for production promotion/final acceptance for that delta/protected-state scope**. It is not a promise that the platform invocation can always be blocked.
- Before the available image call, consume the real source/current task context as strongly as the tool permits and keep the requested delta narrow.
- After the visible result, run `SAME_REAL_CAR_IDENTITY → DELTA_VS_BASELINE → MATERIAL_UPLIFT → REGRESSION_COST`. Any identity regression fails final promotion even if the background is better.
- Repeated `edit_op:null / parent_gen_id:null` plus visible identity reinterpretation is capability evidence that this platform route does not currently prove source-bound background-only editing. Do not relabel another whole-frame result as a source-anchored production edit.
- If exact same-car identity preservation is non-negotiable and the available route cannot demonstrate it, report the capability ceiling rather than claiming a hidden/local route was enforced when it was not.


### 4.4 Executable-route availability gate
Before telling the user that the next run will use a source-anchored / deterministic / local-composite route, verify that the route is actually callable in the current chat environment.

`DESIRED_ROUTE → EXPOSED_NOW? → CALLABLE_NOW? → MATCHING-SCOPE EVIDENCE? → EXECUTE | CAPABILITY_BOUNDARY`

- Historical success, archived renderer code, or a prior project's route does not make that route currently available.
- If the current tool plane exposes only visible whole-frame generation, do not describe the next run as “原車直接保留、只改背景” or “source-pixel background-only” unless the actual call can consume/prove that behavior.
- For current same-real-car tasks, visible whole-frame generation may be used only as exploratory evidence; it is not a proven production edit when protected vehicle details are reinterpreted.
- If no callable route can reliably preserve the higher-priority vehicle identity for the requested delta, keep the source baseline and report the capability boundary instead of inventing an unavailable execution path.

### 4.4A Capability evidence version binding｜能力證據必須綁 route/model/control surface 版本
Capability evidence 不得只綁抽象工具名稱。固定 key：
`CAPABILITY_EVIDENCE_KEY = ROUTE_FAMILY + MODEL/TOOL_REVISION + CONTROL_SURFACE + TASK_SCOPE + PROTECTED_STATE_CLASS`。

規則：
- 舊 PASS/FAIL 只直接約束 matching tuple；route family、model/tool revision 或 exposed control surface materially 改變時，先降為 `HISTORICAL_CAPABILITY_EVIDENCE`，不得直接 promotion 成 current proof。
- 新 revision 不因官方 capability claim 或版本名稱改變就自動 PASS；先跑一個最小 matching-scope canary，再決定 `ELIGIBLE | PILOT_ONLY | INELIGIBLE`。
- 同理，舊 negative evidence 不得永久封鎖 materially different route/revision；但若 control surface 實質未變，只換 prompt wording 或 marketing/model label，不算新 capability。
- capability 文檔／官方宣稱可建立 `CAPABILITY_CANDIDATE` 與 test hypothesis；只有 exposed-now + callable-now + fresh matching-scope evidence 才能建立 production claim。

### 4.5 CONTROL-FIRST execution learning / perception-as-judge
REAL_CAR 的 execution learning 目的不是累積 prompt、route 名稱或事後 defect 清單，而是找出**哪個可控制變因會改變下一次實際出圖行為**。Visual / human-eye perception 是結果 judge；Execution 研究 control；metadata 只作 supporting diagnostic。

固定學習閉環：
`VISIBLE_RESULT / FAILURE → INTENDED_DELTA → PROTECTED_STATE → ACTUAL_CHANGED_REGIONS → CONTROLLABLE_VARIABLES → EXECUTION_FAMILY → MINIMAL_DIFFERENTIAL_TEST → NON_TARGET_REGRESSION → MATCHING_SCOPE_EVIDENCE → NEXT_EXECUTION_POLICY_UPDATE`

研究優先序：
1. `CONTROL`：route 能不能把變動限制在 intended delta；主車、非目標區、source identity 是否會被 collateral redraw。
2. `INTEGRATION`：mask/edge、接觸陰影、反射、玻璃、局部光線、背景接地與色階是否能在不破壞 protected state 下整合。
3. `AUDIT`：人眼/3D/metadata 用來判斷結果與定位 defect；不能把只能事後看見的 knowledge 冒充成可控制 production 的能力。

每個 finding 必須回答：**「下一次實際出圖因此改哪個 executable choice / control / test？」**
- 能改變 route admission、參數、output count、reference binding、delta scope、local control 或 rejection policy → 可升 `CONTROL_FINDING`。
- 只能提高事後判斷、但 current route 無法消費 → 標 `JUDGE_ONLY / CAPABILITY_BOUNDARY`，不得繼續靠更長 prompt 假裝已控制。
- 已有 matching-scope negative evidence 時，不得再用相同 route/action family 重抽來取得低資訊量樣本；除非有 materially different control hypothesis。
- 若 defect 本質是 controllability/availability，不新增背景美感、物件禁令或案例型補丁來代償。

局部控制研究至少觀察：`TARGET_LOCALITY / PROTECTED_REGION_REGRESSION / EDGE_STABILITY / GEOMETRY_IDENTITY / CONTACT_SHADOW / REFLECTION_COHERENCE / LIGHTING_COHERENCE / LITERAL_STABILITY`。

Promotion bar：
`FINDING → EXECUTABLE_CHANGE → FRESH_BEHAVIOR_TEST → REPEATABLE_IMPROVEMENT`。
沒有 fresh behavior evidence 前，只能說 learning contract / execution policy 已更新，不能宣稱底層 route 已修好。



## 11. Applied visual-control learning emphasis｜2026-08-27
REAL_CAR 的研究重心正式區分 `JUDGE FOUNDATION` 與 `APPLICATION/CONTROL FRONTIER`。已成熟的第一眼、3D、比例、真實感、halo 禁止等原理主要作驗收基礎；除非 fresh evidence 顯示 judge 缺口，不以繼續擴充理論名詞作主要 learning。

研究預設流程：
`VISIBLE NEED → WHEN_TO_APPLY → EXECUTABLE CONTROL → LOCALITY/INTENSITY → INTERACTION CONDITIONS → FRESH PILOT → HUMAN/3D JUDGE → REGRESSION COST → REPEATABILITY → POLICY UPDATE`

### 11.1 Applied photometric / 3D integration
輪廓光相關學習歸入 `APPLIED_PHOTOMETRIC_AND_3D_INTEGRATION`，不建立亮邊 recipe。所有 lighting decision 先消費 §3.5 `VEHICLE_VISUAL_PROFILE / PRODUCT_SALIENCE_TARGET / PRODUCT_EDGE_SEPARATION_TARGET`；`PHOTOMETRIC_GOAL = PRODUCT_FORM_READABILITY`，不是整張圖 cinematic grading。目標是實際運用：
- 判斷什麼場景/車色/角度真的需要 subject shaping；不需要就不加。
- 若保留原場景／原角度，以 source light direction 作主要 evidence；若背景或視角生成已改變，改以 `TARGET_SCENE_LIGHT_FIELD + target geometry/material` 重新求解，不得硬套 source rim pixels。
- 以場景光向、車身曲率、材質與背景對比決定局部提亮 / negative fill / tonal sculpting 的位置與強度。
- `NO HALO / NO OUTER GLOW / NO FAKE RIM`；輪廓分離優先在車體幾何內成立。
- 必須一起驗證接觸陰影、反射、玻璃、局部光線與 near-field coupling；不能單獨把車加亮冒充 integration。
- 背景亮度/色溫/局部光可為了商品分離做最低必要調整，但不得把 lighting budget 用在非主體戲劇效果，造成車身相對變平或存在感下降。
- rim/edge shaping 只處理需要分離的車身局部邊界；若背景對比與自然反射已足夠，`NO_EXTRA_RIM` 優於「效果更明顯」。
- 成功標準不是「效果存在」，而是 `MORE DIMENSIONAL + MORE NATURAL + SAME CAR + MATERIAL/TRUTH NONREGRESSION + MATERIAL SALES/HERO UPLIFT`。
- 研究 finding 若不能改變下一次實際的 use/no-use、位置、強度、route/locality 或 rejection policy，只算 JUDGE_ONLY。


### 11.1A Light–geometry–material coupling｜輪廓分離不是獨立亮邊效果

Applied photometric learning 進一步固定成 coupled model：
`SCENE_LIGHT_FIELD → VEHICLE_GEOMETRY/CURVATURE → MATERIAL_RESPONSE → BODY_TONAL_SHAPING → GLASS/REFLECTION → CONTACT+CAST_SHADOW → NEAR_FIELD_ENVIRONMENT_RESPONSE`。

汽車材質至少區分可見判斷類別：`CLEARCOAT/PAINT / METALLIC_FLAKE(if observable) / GLASS / CHROME_OR_BRIGHT_TRIM / BLACK_PLASTIC / RUBBER/TIRE / LIGHT_LENS`。這些是 Visual Judge 的 material model，不代表 current image route 暴露對應 PBR 參數。

硬規則：
- 輪廓光若無法和 source/scene light direction、曲率、材質反射與陰影鏈一致，只能視為 fake rim/halo。
- 車漆不能只靠 uniform brightening；應判斷 clearcoat-like specular separation、環境反射方向與 body form 是否互相支持。
- 玻璃同時看 transmission/opacity、environment reflection、interior visibility、edge highlight；單純亮或黑都不等於成立。
- Execution 只有在 current route 有可消費 control 時才把 material hypothesis 升為 CONTROL_FINDING；否則只保留 `JUDGE_ONLY / CAPABILITY_BOUNDARY`。

### 11.2 Current applied-learning priority
Judge foundation now includes `CONTEXT_AWARE_PRESERVE_MODIFY` + `SOURCE_INSTANCE_ANCHOR_SET`; these improve evidence quality but do not create new execution capability.

1. `SOURCE_INSTANCE_FIDELITY_AND_SAME_REAL_CAR_CONTROL`
2. `ADAPTIVE_VEHICLE_PRODUCT_SALIENCE_POLICY / ARCHETYPE→MODEL→SOURCE PROFILE CALIBRATION`
3. `APPLIED_PHOTOMETRIC_AND_3D_INTEGRATION / LIGHT_GEOMETRY_MATERIAL_COUPLING`
4. `CONDITION_TRACE_FIDELITY`
5. `HERO_BACKGROUND_REPLACEMENT_VALUE / SCENE_FIT + PHYSICAL_FIT`
6. `WHOLE_SCENE_LITERAL_CARRIER_CONSISTENCY + LOCAL_PHYSICAL_REALISM`

同一路徑只換說法或外觀隨機變化仍是 `OUTPUT_VARIANCE`；不能用來宣稱應用 control 已學會。


## 4.6 Learning frontier admission｜priority 不等於下一個可執行實驗
REAL_CAR 的 learning queue 必須同時看 domain importance 與 current route 可回答性。

`IMPORTANCE_PRIORITY → MATERIAL_NEW_CONTROL_AVAILABLE? / ROUTE_CAN_ANSWER_WITH_NEW_INFORMATION? → RUN | BLOCK_AND_KEEP_AS_REGRESSION_WITNESS → NEXT_EXECUTABLE_FRONTIER`

- 高 priority finding 若只有同一 non-auditable whole-frame surface 可用，且 fresh evidence 已證明 protected non-target state 無法固定，不得繼續用重抽取得假的 differential learning。
- `BLOCKED_FRONTIER` 不代表問題不重要，也不代表 PASS；它仍維持 production precedence / regression cost，只是停止低資訊量 control experimentation。
- 一旦 materially different source/reference/local control 真正 exposed + callable，可重新開啟 blocked frontier。
- Photometric/contour/negative-fill 在 current whole-frame matching scope：保留 `JUDGE_POSITIVE` 的實際運用知識，但 `CONTROL_NOT_ISOLATED`；不再用同 surface 做強度/locality A/B。
- Source-instance / condition trace 在 current whole-frame matching scope：繼續作 hard truth/identity witness；沒有新 control mechanism 前，不把 output variance 升成 control finding。
- `HERO_SCENE_REPLACEMENT_VALUE` 不再因「仍可能有決策資訊」自動取得實圖測試資格；它必須先通過 §4.8 `END_TO_END_RELEVANCE + TEST_CIRCUIT_BREAKER`。若 current whole-frame route 已有 SAME_REAL_CAR matching-scope negative evidence，或即使場景成功仍有已知不可呼叫的玻璃／反射／內裝／背景耦合能力鏈，固定 `BLOCK_REAL_IMAGE_TEST`，不得用「先看看」重開。


## 4.7 REAL_CAR test contraction contract｜降低 pilot 成本，不用少測換來假確定性

本 section 是 GLOBAL `Test contraction orchestration` 在 REAL_CAR 的 domain adapter；不建立新 owner。

固定：
`CURRENT_CHANGE_OR_FAILURE → TEST_IMPACT_MAP → T0_PRECHECK → FACTOR_SCREENING → TEST_CONTRACTION_PACKET → T1_CANARY → VISUAL_JUDGE + HARD_WITNESSES → EXPAND_TARGETED | HOLD | ROLLBACK | FULL_REGRESSION`。

`TEST_CONTRACTION_PACKET` 至少包含：
`TEST_GOAL / CHANGE_CLASS / AFFECTED_SEMANTIC_KEYS / KNOWN_GOOD_STATE / ACTIVE_FACTORS / FROZEN_FACTORS / SUSPECT_INTERACTIONS / HARD_WITNESSES / CHEAP_GATES / IMAGE_CALL_BUDGET / EXPECTED_OBSERVABLE / FAILURE_SIGNATURE / STOP_CONDITION / ROLLBACK_TARGET`。

### Impact selection
- plate cover / watermark / literal carrier 等 local rule change：只跑直接 affected visual/object checks + same-car/basic literal regression。
- composition `REFRAME/ZOOM` change：跑 intended framing delta + full-vehicle clearance + subject hierarchy + thumbnail + basic identity；若只是 deterministic frame change，不擴張成 scene/lighting research。
- composition `SUBJECT_RELATIVE_SHIFT_SCALE` change：另外跑 ground-contact / shadow / reflection / occlusion / disocclusion local-effects envelope。
- `VIEW_CHANGE/PERSPECTIVE_CHANGE`：屬高 impact；跑 SOURCE_INSTANCE_ANCHOR_SET + major identity + proportion/stance + perspective/grounding + photometric/material regression。
- scene/background change：跑 scene-fit + physical-fit + identity/condition hard witnesses；不重跑無關 Sales/plate research。
- photometric/material change：跑 light-geometry-material coupling + identity/material/non-target regression；不自動擴張成背景研究。
- execution packet/compiler/source-binding/route family 變更：屬 shared high-impact；跑 broader contract/source/identity/literal/output regression。impact 無法確定 → full regression。
- Visual Judge criteria 變更：不用為了證明 judge 自己而生成大量新圖；優先使用 held-out/nearby/adversarial existing evidence，必要時才 fresh pilot。

### Factor screening
- 預設 `KNOWN_GOOD → FREEZE`, `PRIMARY_HYPOTHESIS → ACTIVE`, `PLAUSIBLE_INTERACTION → SUSPECT`, `UNRELATED → EXCLUDE`。
- 不把 one-factor-at-a-time 當硬規則；只有 evidence 顯示 interaction 可能 material 時，才加入最少必要交互因素。
- current generative route 若無法可靠控制某 factor，該 factor 不得用少量 output variance 做統計因果估計。
- composition factor 只有在 route 真正能消費 crop/box/point/depth/viewpoint/transform 等相應 control 時，才可作 causal test；純語意「更大、更低、更有衝擊感」只能驗 visible adherence，不能宣稱精準 spatial control。

### Failure contraction
- `CONFIG/STATE/PACKET/LITERAL/OUTPUT_CONTRACT` failure 可做 deterministic shrinking / minimal failing set。
- `IDENTITY/3D/PHOTOMETRIC/BACKGROUND` stochastic failure 只能做 `VISUAL_FAILURE_NARROWING`：重複 failure signature、matching-scope evidence、candidate elimination；沒有 repeatable control evidence 不得宣稱「最小根因就是 X」。

### Canary / promotion
- 一次 visible pilot PASS = `CAN_EXPAND_VALIDATION`，不能直接升 `STABLE/PRODUCTION_PROVEN`。
- 只有 targeted regression 沒有新增 material regression，且 improvement 可重複，才可 promotion。
- 每次重大 shared change、impact unknown、或累積多次局部 change 後，安排 periodic/full regression，防止 contraction 長期漏掉跨項退化。

### Record contraction
每輪只回寫最小 reusable state：`PASS_STATE / REJECTED_CONTROL / KNOWN_INTERACTION / CAPABILITY_BOUNDARY / OPEN_UNCERTAINTY + necessary provenance`；不得把每張圖、每個 prompt、每次局部猜測升成永久規則。

## 4.8 Test circuit breaker + end-to-end relevance admission｜先證明這個測試值得做，才允許消耗使用者時間

本節修補 §4.6 / §4.7 已有 stop condition、negative evidence、image-call budget，卻仍可能在真人對話中被「下一步／繼續／再試一個方法」逐段繞開的執行缺口。目標不是少測，而是**封鎖已知低資訊量、不能推進完整成品、會把使用者拖進長時間 debugging 的測試鏈**。它只治理 REAL_CAR test admission，不新增 Owner。

### A. Test-frontier circuit breaker｜失敗不是下一輪的自動起點

每個可見／有成本的 REAL_CAR capability test 先綁：
`TEST_FRONTIER_KEY = USER_GOAL_CLASS + CURRENT_DELTA + PROTECTED_STATE_CLASS + ROUTE_FAMILY + MODEL_TOOL_REVISION + CONTROL_SURFACE + REQUIRED_END_TO_END_CAPABILITY_CHAIN`。

狀態固定：
`CLOSED(TEST_ALLOWED) | OPEN(BLOCK_TEST) | HALF_OPEN_ONE_CANARY`。

- fresh matching-scope negative evidence、capability ceiling、non-callable required capability、或同一 failure signature 已完成一次有資訊量 canary → 對該 key `OPEN`。
- `OPEN` 時，`下一步 / 繼續 / 修正 / 測試 / 再試一次 / 換個 prompt / 換 seed / 換形容詞 / 小幅參數微調` 都**不是** reopen evidence；不得產生 image/render side effect。
- `REOPEN_TRIGGER` 只接受 materially different evidence：① 新的 route/model/tool revision 且 control surface 實質改變並 `EXPOSED_NOW + CALLABLE_NOW`；② 新的 source/reference/transparent alpha/外部 artifact 實質改變 feasibility；③ current user goal/required output materially 改變；④ 新證據推翻舊 capability boundary。只有 marketing 名稱、prompt wording、隨機 output variance、同 family 的 micro-tuning 不算。
- 合法 reopen 先進 `HALF_OPEN_ONE_CANARY`，預設只允許 **1 個**最小 matching-scope canary；PASS 才能考慮 CLOSED，FAIL 立即回 OPEN，不進第二張「修一下再試」。

### B. End-to-end relevance gate｜子步驟成功但完整成品仍做不到，就不拿真人時間去測

在任何 T1 canary 前固定計算：
`USER_TRUE_GOAL → SUCCESS_IF_TEST_PASSES → WHICH_FINAL_BLOCKER_REMOVED? → REMAINING_HARD_CAPABILITY_CHAIN → CALLABLE_NOW? → MATERIAL_CHANGE_IN_FINAL_ELIGIBILITY?`。

- 若測試即使 PASS，仍有已知且獨立的 HARD blocker，使最終商品圖 production eligibility 不變，且本測試不是該 blocker 的必要且下一步可呼叫 prerequisite → `NON_CLOSING_TEST / BLOCK_REAL_IMAGE_TEST`。
- component/fallback 不得因「技術上能做」升格成主線。例：車體 cutout／透明 alpha 即使成功，若 current final goal 仍需要玻璃 transmission/reflection、內裝可見內容、背景／近場光影／接地等生成耦合，而後續 integration route 沒有 matching callable control，則 cutout 只能保留為 future prerequisite evidence，**不得再啟動長時間 cutout/mask 優化測試**。
- square framing、plate cover、literal 等局部問題只有在其 PASS 會實質改變 final deliverability，或能獨立交付可用 artifact 時才可測；不得用局部 PASS 製造「整體快完成」的錯覺。
- 一條 fallback 若只改善 identity safety、卻無法完成 current user 要求的 full visual integration，固定標 `SAFE_FALLBACK != PRIMARY_GOAL_SOLUTION`。

### C. Test entry criteria + user-cost budget｜沒有 admission receipt 就沒有測試

所有有 side effect 的測試在 effect gateway 前必須產生 task-local：
`TEST_ADMISSION_RECEIPT = TEST_FRONTIER_KEY / BREAKER_STATE / TEST_GOAL / END_TO_END_CLOSURE_IMPACT / MATERIAL_NEW_EVIDENCE / REQUIRED_CAPABILITY_CHAIN / EXPOSED_CALLABLE_STATE / EXPECTED_INFORMATION_GAIN / IMAGE_CALL_BUDGET / USER_CORRECTION_TURN_BUDGET / STOP_CONDITION / REOPEN_CONDITION / RECEIPT_STATE`。

Default deny：
- `BREAKER_STATE=OPEN`、`END_TO_END_CLOSURE_IMPACT=NONE/LOW`、沒有 materially new evidence、required downstream chain 不可呼叫、expected information gain 只是「看看會不會比較好」→ `RECEIPT_STATE=REJECT / NO_TOOL_CALL`。
- 系統主動發起的 capability test 預設 `IMAGE_CALL_BUDGET=1`、`USER_CORRECTION_TURN_BUDGET=0`。不得把使用者變成「看圖→指出問題→我修→再看圖」的 debugger。
- 若第一個 canary 已得到 terminal negative/ceiling，該輪立即 `TEST_EXIT`；分析與 status writeback 可繼續，但不得在同一語意 frontier 自動換 v2/v3/v4、mask family、outpaint family、另一個 prompt family 連鎖測試。
- 時間／互動／image-call budget 耗盡本身就是合法 exit condition：`HOLD_WITH_EXACT_BLOCKER`，不得把「還沒完全確定」當成繼續消耗的理由。

### D. Change-triggered rerun｜沒有相關能力變化，就不要重跑

`PRIOR_TERMINAL_EVIDENCE + CURRENT_CHANGESET → AFFECTED_TEST_FRONTIER_KEYS`。

- 只有 change set 觸及某 breaker key 的 route/model/control/source/goal/capability-chain 欄位，該 key 才有資格重新 admission；無關的 Canonical 文案整理、背景偏好、另一個局部物件修正、對話重開、使用者說「下一步」不得觸發。
- 已 PASS 的 unrelated checks 不重跑；已 OPEN 的 unrelated frontier 不因新一輪 task 自動清零。
- `CAPABILITY_STATUS_CURRENT` 保存 breaker state + reopen condition + evidence provenance；它是 observed state，不把單一 Sienta case 寫成 Canonical 永久內容。

### E. No autonomous frontier hopping｜研究可以找替代，實圖測試不能一路跳坑

一個 frontier 被 OPEN 後，Execution 可以做**零 side-effect**的研究、能力盤點、文件比對，尋找 materially different route；但不得自動把「下一個可能方法」直接變成下一個實圖測試。

`OPEN_FRONTIER → RESEARCH/INVENTORY(no side effect) → MATERIAL_NEW_ROUTE_FOUND? → END_TO_END_RELEVANCE → HALF_OPEN_ONE_CANARY | KEEP_OPEN`。

禁止模式：
`cutout FAIL → manual mask → active contour → Mask R-CNN candidate → outpaint → square-safe capture → generic image_gen` 這種靠每次失敗自動衍生下一條支線的長鏈。每次 materially different route 都必須重新過 A/B/C，不得沿用上一條「已經開始測了」的動量。

### F. User override boundary｜使用者有控制權，但模糊指令不解除保護

- `下一步 / 繼續 / 再試 / 修正 / 出圖` 不構成 circuit-breaker override。
- 若使用者**明確**要求「即使沒有新能力也要做一次探索性測試」，可建立一次性 `EXPLICIT_EXPLORATORY_OVERRIDE`，但仍須告知它不會解鎖 production，且固定 `IMAGE_CALL_BUDGET=1`；失敗後 breaker 立即 OPEN。
- 使用者明確要求停止某類測試時，該 current goal scope 的 breaker 至少保持 OPEN，直到使用者主動改變 goal 或 materially new capability evidence 出現；系統不得靠相似但不同名稱的 fallback 繞過。

### G. Enforcement honesty

`TEST_CIRCUIT_BREAKER_ENFORCEMENT = SOFT_GOVERNED`，除非平台/tool boundary 可證明所有 image/render side effects 都必經 `TEST_ADMISSION_RECEIPT`。在目前 chat surface，REAL_CAR 必須在自己的 committed plan/effect gateway default-deny，但不得宣稱平台層物理不可繞過。任何沒有 receipt 的實圖測試一律 `UNADMITTED_TEST_SIDE_EFFECT / NON_PRODUCTION_EVIDENCE`，不得以事後成功抵銷。

