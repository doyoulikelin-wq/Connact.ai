# Development Log

## 2026-01-26: Invite-only 账号体系 + 个人 Profile 持久化

### 账号体系（替换共享 APP_PASSWORD）
- 新增 Email/Password 注册与登录（invite-only）
- Email 注册需要完成邮箱验证后才能登录
- Google 登录使用更稳定的身份标识（优先从 `id_token` 解析 OIDC `sub`，失败则 fallback 到 userinfo）
- Google 新用户同样要求邀请码（通过 `/login/google?invite_code=...` 传入）

### 个人 Profile（按用户持久化）
- 新增 SQLite 存储：`{DATA_DIR}/app.db`（可通过 `DB_PATH` 覆盖）
- 持久化字段：
  - `sender_profile`（简历解析 / 问卷生成的 sender profile）
  - `preferences`（最近一次找人偏好）
- `index_v2` 会自动注入并复用已保存的 sender profile（跨会话）

### 新增接口
- Web:
  - `GET/POST /signup`
  - `GET /verify-email?token=...`
  - `POST /resend-verification`
  - `GET /login/google`（启动 Google OAuth，携带邀请码）
- API:
  - `GET /api/me`
  - `GET/POST /api/profile`

### 新增/更新环境变量
- `INVITE_ONLY`（默认 true）
- `INVITE_CODE` 或 `INVITE_CODES`（逗号分隔）
- `DB_PATH`（可选，默认 `{DATA_DIR}/app.db`）
- `EMAIL_VERIFY_TTL_HOURS`（默认 24）
- SMTP（可选，用于发送验证邮件）：`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`

Files: `app.py`, `config.py`, `src/services/auth_service.py`, `templates/login.html`, `templates/signup.html`, `templates/signup_done.html`, `templates/index_v2.html`, `tests/test_auth_service.py`, `README.md`, `devlog.md`, `note.md`

## 2026-01-25: 品牌重命名 + Google OAuth 登录

### 品牌重命名
- 将 "Cold Email Generator" 更名为 **Connact.ai**
- 移除 v3.0 版本标识
- 更新 Logo emoji 从 📧 改为 🤝

### Google OAuth 登录
新增 Gmail 账号登录功能，与原有密码登录并存。

**实现细节**：
- 使用 Flask-Dance 集成 Google OAuth 2.0
- 登录页面显示 "Continue with Google" 按钮
- 登录成功后存储用户邮箱、名称、头像到 session
- 本地开发允许 HTTP（`OAUTHLIB_INSECURE_TRANSPORT=1`）

**新增环境变量**：
- `GOOGLE_CLIENT_ID`: Google OAuth 客户端 ID
- `GOOGLE_CLIENT_SECRET`: Google OAuth 客户端密钥

**文件改动**：
- `app.py`: 添加 Google OAuth blueprint 和回调路由
- `templates/login.html`: 添加 Google 登录按钮样式和逻辑
- `requirements.txt`: 添加 Flask-Dance, google-auth, google-auth-oauthlib

### Find Contact 问卷改进
- `ib_firm_type` 问题改为多选（type: 'multi'）

Files: `app.py`, `templates/login.html`, `templates/index_v2.html`, `templates/index.html`, `requirements.txt`

---

## 2026-01-25: 修复 Generate More 后 Contact 不准确的问题

### 背景
- 用户在找到 target list 后，点击 "Generate More" 按钮会导致 contact 信息不准确
- 原因：系统使用 `name` 作为唯一标识匹配已选目标，但同名不同人的情况会导致混淆
- 当 `state.recommendations` 被新数据替换后，`selectedTargets` 中的旧选择与新列表中的同名人会产生数据冲突

### 解决方案
使用唯一 ID 代替名字匹配，基于 `name + position + linkedin_url` 生成 12 位 MD5 哈希作为稳定标识。

### 改动详情

**后端 `src/email_agent.py`**：
- 新增 `_generate_recommendation_id(name, position, linkedin_url)` 函数生成唯一 ID
- `_normalize_recommendations()` 为每个推荐对象添加 `id` 字段
- `_ai_score_and_analyze_candidates()` 返回前为 SerpAPI 结果添加 ID
- Final fallback 返回值也添加 ID

**前端 `templates/index_v2.html`**：
- `renderRecommendations()`: 使用 `rec.id` 检查已选状态，向下兼容无 ID 情况（fallback 到 name）
- `toggleRecommendation()`: 使用 ID 匹配；选择时 clone 对象避免引用问题
- `updateSelectedTargetsUI()`: 使用 ID 匹配更新 checkbox 状态，添加 `rec` 存在性检查

### 技术细节
```javascript
// 匹配逻辑（优先 ID，fallback 到 name）
const isSelected = state.selectedTargets.some(t => 
    (rec.id && t.id === rec.id) || (!rec.id && t.name === rec.name)
);

// 选择时 clone 对象
state.selectedTargets.push({ ...rec });
```

Files: `src/email_agent.py`, `templates/index_v2.html`, `devlog.md`

---

## 2026-01-18: Academic 模式锁定（Building）

### 背景
- Academic 模式尚未开发完全，需要暂时锁定
- 保留 UI 界面但禁止用户进入，提示 "Building"


### 实现方案
**CSS 样式**（~70 行新增）：
- `.mode-card.locked`：锁定卡片样式（半透明、灰度滤镜、禁用指针）
- `.lock-overlay`：遮罩层（居中显示锁图标和文字）
- `.lock-chains`：对角锁链效果（伪元素 `::before`/`::after` 实现）
- `.toast` / `.toast-container`：Toast 通知组件样式

**HTML 改动**：
- Academic 卡片添加 `locked` class
- 添加锁定覆盖层结构（锁图标 🔒 + "Building" 文字 + 锁链效果）
- 添加 Toast 容器 `#toast-container`

**JavaScript 功能**：
- `showToast(message, type, duration)` - 通用 Toast 提示函数
- Track 选择事件处理增加 `.locked` 检查，阻止选中并显示提示

### 效果
- Academic 卡片显示为半透明灰色，带有对角锁链装饰
- 中央显示 🔒 图标和 "BUILDING" 文字
- 点击时显示顶部 Toast：「🔒 Academic mode is currently under development. Coming soon!」
- Finance 卡片不受影响，可正常选择

Files: `templates/index_v2.html`, `devlog.md`

---

## 2026-01-18: 邮件版本对比放大编辑功能 & Bug 修复

### 背景
- Regenerate 后显示原始版本和重新生成版本的对比视图
- 用户需要能够放大查看并编辑每个版本
- 修复多个 UI 交互和 prompt 相关的 bug

### 新增功能：版本对比放大编辑

**CSS 样式**（~80 行新增）：
- `.email-expand-modal`：全屏模态框，深色背景遮罩
- `.email-expand-content`：编辑内容容器（最大 700px 宽度）
- `.email-expand-input` / `.email-expand-textarea`：表单输入样式
- `.email-version .expand-hint`：悬停显示 "Double-click to edit" 提示

**HTML 结构**：
- 每个版本卡片添加 `🔍 Double-click to edit` 提示
- 新增编辑模态框：标题区、Subject 输入框、Body 文本域、Cancel/Save 按钮

**JavaScript 功能**：
- `setupCompareView()` - 更新为支持单击选择、双击放大
- `openExpandModal(version)` - 打开指定版本的编辑模态框
- `closeExpandModal()` - 关闭模态框（支持 ESC 键、点击背景）
- `saveExpandModalChanges()` - 保存编辑内容并同步更新对比视图
- `setupExpandModal()` - 设置模态框事件监听器

### Bug 修复汇总

1. **OpenAI 函数参数错误** (`src/email_agent.py`)
   - `_call_openai_chat()` 调用时参数名错误：`system_prompt` → `system_content`，`user_prompt` → `user_content`

2. **Step 3 Back 按钮导航错误** (`templates/index_v2.html`)
   - Professional mode 下点击 Back 应返回 Step 2b（targets list），而非 Step 2（sender info）
   - 添加 `state.mode` 检查以区分模式

3. **Regenerate 使用错误模型** (`src/email_agent.py`)
   - `regenerate_email_with_style()` 原来固定使用 Gemini
   - 修复为根据 `USE_OPENAI_FOR_EMAIL` 配置选择 OpenAI 或 Gemini

4. **Regenerate 改变邮件内容** (`src/email_agent.py`)
   - 更新 `regenerate_email_with_style()` 的 prompt，添加 5 条严格规则：
     - 只改变语气/风格，不改变实质内容
     - 保留所有姓名、数字、事实、经历
     - 不添加新信息，不删除原有内容

5. **Subject 解析失败** (`templates/index_v2.html`)
   - `parseEmailText()` 无法解析 Markdown 格式的 Subject（如 `**Subject:**`）
   - 更新正则表达式支持多种格式

6. **输出格式问题** (`src/email_agent.py`)
   - `build_prompt()` 和 `regenerate_email_with_style()` 添加纯文本输出规则
   - 明确要求：无 Markdown（no **, ##, *）

### 按钮行为验证

| 按钮 | 行为 |
|------|------|
| **← Use Original** | 选择原始版本，关闭对比视图，更新邮件显示 |
| **Use Regenerated ✓** | 选择重新生成版本，关闭对比视图，更新邮件显示 |
| **Close Compare** | 仅关闭对比视图，保持当前选择 |
| **Style Options** | professional/friendly/concise/detailed/custom 各有明确指令 |
| **Regenerate This Email** | 发送正确的 style_instruction 到后端 |
| **Save Changes（模态框）** | 保存编辑到对应版本，同步更新视图 |

### Regenerate Style Instructions

```javascript
professional: 'Make the email more professional and formal'
friendly: 'Make the email more friendly and warm'
concise: 'Make the email shorter and more concise'
detailed: 'Add more details and elaborate on key points'
custom: [用户自定义输入]
```

Files: `src/email_agent.py`, `templates/index_v2.html`, `devlog.md`

---

## 2026-01-18: 搜索动态加载动画

### 背景
- 搜索目标人物时加载时间较长，需要给用户更好的等待体验
- 同时适用于 Quick Start 和 Professional 模式

### 实现方案

**CSS 样式**：
- `.loading-dots::after` 添加省略号动画（`...` 循环）

**JavaScript 功能**：
- `loadingMessages` 数组：包含多条动态提示信息
  - "Searching for the best matches..."
  - "Analyzing profiles and backgrounds..."
  - "Finding people who match your criteria..."
  - "Almost there, reviewing top candidates..."
  - "Preparing personalized recommendations..."
- `startLoadingAnimation()` / `stopLoadingAnimation()`：管理定时器
- 每 3 秒切换一条提示信息

**应用位置**：
- Quick Start 模式：`fetchRecommendations()` 中调用
- Professional 模式：`findProTargets()` 中调用

Files: `templates/index_v2.html`

---

## 2026-01-18: Email 模板风格指南集成

### 背景
- 新增 `template/template.txt` 文件，包含 4 个经过验证的冷邮件模板
- 需要提取这些模板的共同结构、语气和用词习惯，集成到邮件生成 prompt 中

### 模板分析总结

**结构（8 个部分）**：
1. 问候：Hi/Good morning + 名字（只用 first name）
2. 自我介绍：姓名 + 学校 + 专业 + 年级
3. 相关经历：实习/项目经验（用 **粗体** 强调公司名）
4. 联系原因：对对方职位/公司的兴趣
5. 明确请求：15-20 分钟通话 + 灵活时间
6. 附件说明：简历
7. 期待回复
8. 落款：Best regards / Many thanks / Warm regards + 名字

**语气**：
- 谦逊但自信（humble but confident）
- 尊重对方时间（"I understand your schedule must be quite full"）
- 具体且真诚（reference specific aspects）
- 温暖专业（warm professional）

**常用短语**：
- "Would love to hear more about your experience"
- "Would greatly appreciate the opportunity"
- "I'd be incredibly grateful for the chance"
- "Looking forward to hearing from you"

### 改动 (`src/email_agent.py`)
- `build_prompt()` 函数新增 `style_guide` 变量
- Style Guide 包含结构、语气、常用短语、避免事项
- 集成到 system_content 中

Files: `template/template.txt`（新增）, `src/email_agent.py`, `devlog.md`

---

## 2026-01-18: Receiver 深度搜索功能 - 丰富邮件生成 Context

### 背景
- 用户选中目标后点击 generate email，原来只用找人阶段获取的基础信息
- 需要对选中的目标再进行一次更细致的搜索，获取近期项目和主要经历
- **关键要求**：杜绝 LLM 杜撰，所有信息必须有明确来源

### 技术方案
1. **SerpAPI 搜索**：构建多个查询（近期项目/成就、职业经历/背景、新闻/报道）
2. **LLM 信息提取与验证**：
   - 严格的 prompt 约束：只提取搜索结果中明确提到的信息
   - 每条信息必须标注来源（如 `[from Result 1]`）
   - 如果搜索结果不是关于目标人物，返回空结果
3. **增强 ReceiverProfile**：将验证过的信息合并到 context 中

### 新增功能 (`src/email_agent.py`)
- `ReceiverDeepSearchResult` dataclass：存储深度搜索结果（recent_projects, key_experiences, recent_news, verified_facts, sources）
- `search_receiver_deep_context()`: 执行 SerpAPI 搜索并调用 LLM 提取信息
- `_build_deep_search_queries()`: 构建多个搜索查询
- `_format_search_results_for_llm()`: 格式化搜索结果
- `_extract_verified_info_from_search()`: 用 LLM 提取验证过的信息
- `enrich_receiver_with_deep_search()`: 增强 ReceiverProfile

### API 改动 (`app.py`)
- `/api/generate-email` 新增参数 `enable_deep_search`（默认 `true`）
- 在生成邮件前自动调用深度搜索
- 返回结果新增 `deep_search` 字段（success/failed）

### 前端改动 (`templates/index_v2.html`)
- Loading 提示更新为 "Researching {name}..."

### 防止 LLM 杜撰的措施
1. Prompt 中明确要求 `person_confirmed` 字段
2. 每条信息必须引用搜索结果编号
3. 如果搜索结果与目标人物不匹配，返回空列表
4. 不确定的信息不包含

Files: `src/email_agent.py`, `app.py`, `templates/index_v2.html`, `devlog.md`

---

## 2026-01-15: Finance 决策树简化（方向单选）

### 背景
- 原流程是 Q1（方向多选）→ Q2（Primary 单选）→ 只对 Primary 深挖
- 方向选择只需要一个明确主方向即可，减少一轮确认与问卷长度

### 改动
- `templates/index_v2.html`
  - Finance 决策树 Q1 `career_directions` 改为单选（主方向）
  - 删除 `primary_direction` 节点；所有分支依赖改为 `career_directions`
  - 将 “Not sure yet — keep it broad” 作为 Q1 选项保留
  - 移除 Optional：`contactability`（reply vs prestige）与 `contact_channels`（联系方式偏好）
  - 新增 “Back” 按钮，支持逐题回退并修改答案
  - 点击左上角 Logo 返回主页面（`/`）

Files: `templates/index_v2.html`, `README.md`, `note.md`, `devlog.md`

---

## 2026-01-15: Email 生成时保留 receiver 具体信息

### 背景
- 找人阶段（`/api/find-recommendations`）已返回候选的 `position/linkedin_url/evidence/sources` 等可核验信息
- 生成邮件阶段会调用 `/api/search-receiver` 做补全，但原逻辑会直接覆盖 receiver 对象，导致 email prompt 丢失这些关键信息，模型只能写泛化开场（例如 “you work in Finance”）

### 改动
- `templates/index_v2.html`
  - Step 5 生成邮件前：将推荐 target 与 `/api/search-receiver` 返回的 profile 做 merge（不再覆盖）
  - 将 `position/linkedin_url/evidence` 写入 `receiver.context`，并确保 `sources` 合并包含 LinkedIn URL
- `app.py`
  - `/api/generate-email` 将 `receiver.position/linkedin_url/evidence` 合并进 `ReceiverProfile.context`，并将 LinkedIn URL 补进 `sources`
- `src/web_scraper.py`
  - `extract_person_profile_from_web()` 最终兜底不再注入 `experiences=["Works in {field}"]`，避免模型引用尴尬泛化句

Files: `templates/index_v2.html`, `app.py`, `src/web_scraper.py`, `README.md`, `note.md`, `devlog.md`

---

## 2026-01-15: 找人后立即保存数据

### 背景
- 原来只有完成"生成邮件"才会保存数据
- 需要在"找人"阶段就保存，以便收集推荐算法训练数据

### 改动
1. **`src/services/prompt_collector.py`**
   - `PromptRecord` 新增 `recommendations` 字段，存储找到的人物信息
   - 新增 `save_find_target_partial()` 方法，找人后立即保存
   - 新增 `_save_find_target_record()` 方法，保存到单独目录
   - 新增便捷函数 `save_find_target_results()`

2. **`app.py`**
   - 导入 `save_find_target_results`
   - `/api/find-recommendations` 成功后立即调用保存
   - `user_info` 中增加完整的 `sender_profile` 和 `preferences`

### 存储路径
- 找人日志：`{DATA_DIR}/find_target_logs/{日期}/{时间}_{session_id}.json`

### 保存的数据
- `user_info`: purpose, field, sender_profile, preferences
- `prompt_find_target`: 搜索 prompt
- `recommendations`: 人物信息（姓名、职位、公司、LinkedIn URL、评分等）

---

## 2026-01-14: Finance Professional 决策树偏好问卷 + 结构化找人输入

### 背景问题
- Professional / Finance track 原有固定问卷偏 IB，且多数信息只落在 `preferences.extra`，SerpAPI 搜索词难以真正利用这些偏好。
- 需要把 “G/S/O/M/Seniority/Optional” 结构化收集并直连到找人阶段的检索与排序。

### 改动
1. **`templates/index_v2.html`** - Finance track 决策树问卷
   - G（Career Direction）支持多选；新增 Primary direction（单选），只对 Primary 深挖，避免问卷爆长
   - 支持 single/multi + `Other (please specify)` 自定义输入
   - 生成结构化 `state.financePreferences`（如 `bank_tier/group_type/group/sector/location/seniority/outreach_goal/target_role_titles/search_intent`）
   - `findProTargets()` 合并结构化 prefs + 可选 advanced targeting 字段传给 `/api/find-recommendations`

2. **`src/email_agent.py`** - 结构化偏好消费增强
   - `_build_preference_context()` 支持 list/dict 字段（finance 结构化字段能进入 prompt）
   - `_build_serpapi_search_query()` 消费 `bank_tier/group/sector/target_role_titles` 等字段，并支持 `;` 分隔的多值
   - `_ai_score_and_analyze_candidates()` 纳入更多偏好字段用于匹配分析

3. **`src/services/llm_service.py`** - 可选依赖
   - `google-generativeai` 改为可选导入：未安装时不会在 import 阶段炸掉（运行到 Gemini 调用才报错）

4. **`tests/test_serpapi_query.py`** - 新增测试
   - 覆盖 SerpAPI 搜索词构建与偏好 context 格式化

### 注意事项
- Finance 决策树仅在 Professional/Finance track 启用；Quick Start 与 Academic track 不受影响。
- 若需要 Gemini，请确保安装依赖：`python -m pip install -r requirements.txt`。

Files: `templates/index_v2.html`, `src/email_agent.py`, `src/services/llm_service.py`, `tests/test_serpapi_query.py`, `README.md`, `devlog.md`, `note.md`

## 2026-01-10: 支持 Render Disk 持久化存储

### 背景
- Render 部署时文件系统是临时的，每次部署会重置
- 需要使用 Persistent Disk 来保存用户数据和日志

### 改动
1. **`config.py`** - 新增统一数据目录配置
   - 新增 `DATA_DIR` 变量，从环境变量读取（默认 `./data`）
   - Render 生产环境设置 `DATA_DIR=/var/data`

2. **`src/services/user_uploads.py`** - 改用统一配置
   - `USERS_DIR` 改为从 `DATA_DIR` 派生

3. **`src/services/prompt_collector.py`** - 改用统一配置
   - `DATA_DIR_PROMPTS` 改为从 `DATA_DIR` 派生

### Render 配置步骤
1. Dashboard → 服务 → Disks → Add Disk
2. Mount Path: `/var/data`
3. 环境变量：`DATA_DIR=/var/data`

### 文件命名规则
- 用户数据：`{DATA_DIR}/users/{日期}/{时间戳}_{session_id}/`
- Prompt 日志：`{DATA_DIR}/prompt_logs/{日期}/{时间戳}_{id}.json`

---

## 2026-01-10: SerpAPI 直接搜人 - 方案 A 实现

### 背景问题
- 之前的流程：AI (Gemini) 生成人名列表 → SerpAPI 根据人名搜索 LinkedIn
- 问题：AI 会编造名字或返回太通用的名字（如 "Emily Carter"）
- SerpAPI 搜索这些名字时，找到的是完全不同的人

### 新方案：SerpAPI 直接搜索 LinkedIn 找真实的人
**不再依赖 AI 生成名字**，而是：
1. 将用户的 preferences（职位、公司、领域等）转化为搜索词
2. 直接用 SerpAPI 搜索 LinkedIn（`site:linkedin.com/in/`）
3. 从搜索结果中提取真实存在的用户信息

### 搜索词构建示例
| 用户需求 | 生成的搜索词 |
|---------|-------------|
| 找 Goldman M&A Associate | `site:linkedin.com/in/ "Associate" ("Goldman Sachs" OR "Morgan Stanley") "M&A" "New York"` |
| 找 VC Partner | `site:linkedin.com/in/ "Partner" "Venture Capital" -intern` |

### 后端改动 (`src/email_agent.py`)
- 新增 `_build_serpapi_search_query(preferences, field, purpose)` 函数
  - 将用户偏好转化为 Google 搜索词
  - 支持：职位/级别、公司、领域、地区、排除词
- 新增 `_search_linkedin_via_serpapi(preferences, field, purpose, count)` 函数
  - 直接搜索 LinkedIn 找真实用户
  - 从搜索结果标题中解析姓名和职位
  - 返回带有真实 LinkedIn URL 的用户列表
- 新增 `_parse_linkedin_title(title)` 函数
  - 解析 LinkedIn 搜索结果标题（如 "John Smith - VP at Goldman | LinkedIn"）
- 修改 `find_target_recommendations()`：
  - **首选方案**：SerpAPI 直接搜人（如果配置了 SERPAPI_KEY）
  - **回退方案**：Gemini Search（如果 SerpAPI 结果不足）

### 流程对比
**旧流程**（有问题）：
```
用户输入 → AI 生成"人名" → SerpAPI 验证 LinkedIn URL → 返回
                ↓
         问题：AI 编造名字
```

**新流程**（方案 A）：
```
用户输入 → 构建搜索词 → SerpAPI 直接搜 LinkedIn → 提取真实用户 → 返回
                                    ↓
                            ✅ 所有用户都是真实存在的
```

### 测试结果
搜索 `site:linkedin.com/in/ "Associate" ("Goldman Sachs" OR "Morgan Stanley") "M&A" "New York"` 返回：
- ✅ Zach Rudich - M&A Investment Banking Associate
- ✅ Michael Lipsky - M&A at Morgan Stanley
- ✅ Derek Vincent - Investment Banking Associate at Goldman Sachs

Files: `src/email_agent.py`, `devlog.md`

---

## 2026-01-10: SerpAPI 集成 - 真实 LinkedIn URL 查找（已被方案 A 取代）

### 背景
- 之前的方案：生成 LinkedIn 搜索链接（用户需要手动点击搜索结果）
- 用户体验不够好：多一步操作

### 新方案：SerpAPI Google Search
- 使用 SerpAPI 调用 Google Search，搜索 `site:linkedin.com/in/ "Name" "Company"`
- 从搜索结果中提取真实的 LinkedIn 个人主页 URL
- 如果 SerpAPI 不可用或查找失败，回退到搜索链接方案

### 后端改动 (`src/email_agent.py`)
- 新增 `_lookup_linkedin_via_serpapi(name, company, additional_context)` 函数
  - 使用 SerpAPI Google Search 查找真实 LinkedIn URL
  - 验证搜索结果中的 URL 格式和名字匹配度
  - 需要环境变量 `SERPAPI_KEY`（或 `SERP_API_KEY`）
- 修改 `_normalize_recommendations`：
  - 优先使用 SerpAPI 查找真实 URL
  - 如果 SerpAPI 失败或未配置，回退到搜索链接

### 配置
- 环境变量：`SERPAPI_KEY`（可选）
- 获取 API Key：https://serpapi.com/
- 免费套餐：100 次/月
- 付费套餐：$50/月 5000 次

### LinkedIn URL 查找优先级
1. AI 模型返回的 URL（如果格式验证通过）
2. SerpAPI Google Search 查找的真实 URL
3. LinkedIn 搜索链接（fallback）

Files: `src/email_agent.py`, `README.md`, `devlog.md`

---

## 2025-12-31: LinkedIn URL 生成策略优化

### 问题
- AI 模型（Gemini）会根据人名**编造** LinkedIn 个人主页 URL（如生成 `emilycartermergers`），而实际正确的是 `emilyacarter`
- 用户点击后会看到 "页面不存在" 错误
- Google Search grounding 返回的是重定向 URL（`vertexaisearch.cloud.google.com`），无法用于验证

### 解决方案
**改为生成 LinkedIn 搜索链接，而不是个人主页链接**

### 后端改动 (`src/email_agent.py`)
- 新增 `_generate_linkedin_search_url(name, company)` 函数
  - 生成格式：`https://www.linkedin.com/search/results/people/?keywords=Name%20Company`
  - 用户点击后在 LinkedIn 上搜索该人，自己选择正确的结果
- 修改 `_normalize_recommendations`：
  - 如果 AI 返回的 URL 验证失败，自动生成搜索链接
  - 从 position 字段提取公司名（如 "VP at Goldman Sachs"）
- 修改搜索提示词：
  - 明确告诉模型**不要生成 LinkedIn URL**（`linkedin_url` 留空）
  - 只需返回人名、职位、证据来源
- 简化 `_validate_linkedin_url`：
  - 移除对 grounding URLs 的依赖（因为是重定向 URL）
  - 只做格式验证和假 URL 模式过滤

### 前端改动 (`templates/index_v2.html`)
- `renderRecommendations` 中区分搜索链接和个人主页链接
  - 搜索链接：显示 🔍 图标 + "Search on LinkedIn" 提示
  - 个人主页链接：正常显示 LinkedIn 图标

### 用户体验改进
- ✅ 不再出现 "页面不存在" 错误
- ✅ 用户点击 LinkedIn 图标 → 打开搜索页面 → 自己选择正确的人
- ✅ 保证每个推荐都有可用的 LinkedIn 搜索入口

Files: `src/email_agent.py`, `templates/index_v2.html`

---

## 2025-12-30: Gemini Google Search API 升级

### 问题
- `google.generativeai` 包已废弃，`google_search_retrieval` 工具不再支持
- 报错：`400 Unable to submit request because google_search_retrieval is not supported`

### 解决方案
- 安装新的 `google-genai` 包 (v1.56.0)
- 使用新 API：`genai_new.Client` + `genai_types.Tool(google_search=genai_types.GoogleSearch())`

### 后端改动 (`src/email_agent.py`)
- 新增导入：`from google import genai as genai_new` 和 `from google.genai import types as genai_types`
- 重写 `_call_gemini_with_search` 函数使用新 API
- 新增 `_extract_json_from_text` 函数（因为 Search grounding 不支持 JSON mode）

Files: `src/email_agent.py`, `requirements.txt`（需要 `google-genai>=1.56.0`）

---

## 2025-12-30: LinkedIn Profile Search Enhancement

- **Find Targets 功能增强**：优先搜索 LinkedIn 信息
- **后端改动** (`src/email_agent.py`)：
  - 修改 `_build_recommendation_prompt`：新增 `linkedin_url` 字段要求
  - 修改 `_normalize_recommendations`：提取并处理 `linkedin_url`，自动从 sources 中识别 LinkedIn URLs
  - 修改搜索提示词：明确要求 "Search '[name] [company] LinkedIn'" 优先获取 LinkedIn 信息
  - 针对 Finance/Banking 专业人士优化搜索策略
- **前端改动** (`templates/index_v2.html`)：
  - `renderRecommendations`：每个推荐卡片显示 LinkedIn 图标链接
  - Profile Modal：新增 LinkedIn Profile 展示区域
  - 新增 `.linkedin-link` 样式（LinkedIn 品牌蓝色 #0a66c2）
- **返回数据结构**：每个推荐新增 `linkedin_url` 字段

Files: `src/email_agent.py`, `templates/index_v2.html`

## 2025-12-23: 用户上传数据存储功能

- 新增用户上传文件（简历 PDF + Target 信息）的持久化存储功能
- **存储结构**：
  - 路径：`data/users/{日期}/{时间戳}_{session_id}/`
  - 文件：`resume.pdf`（原始简历）、`resume_profile.json`（解析后数据）、`targets.json`（目标人选列表）、`metadata.json`（完整会话记录）
- **新增模块**：`src/services/user_uploads.py`
  - `UserUploadStorage` 类：单例模式管理用户上传数据
  - `save_user_resume()` / `save_user_targets()` / `add_user_target()`：便捷函数
- **API 更新**：
  - `/api/upload-sender-pdf`：上传简历时自动保存原始 PDF 和解析数据
  - `/api/save-targets`（新增）：保存用户选择的 target 列表
- **前端更新**：
  - 添加 `generateSessionId()` 生成唯一会话 ID
  - `state.sessionId` 贯穿整个用户会话
  - 在 `generateAllEmails()` 前自动保存 targets

Files: `src/services/user_uploads.py`（新增）, `app.py`, `templates/index_v2.html`

## 2025-12-23: UI 科幻梦核视觉主题更新

- 在保持 v2 全部功能和布局不变的前提下，更新视觉设计为科幻梦核风格
- **配色方案**：
  - 主背景：深空紫黑色（#0a0a12）
  - 主强调色：霓虹紫（#7b68ee → #9d8bff）
  - 次强调色：电子青（#00d4ff）、霓虹粉（#ff6b9d）
  - 成功/警告/错误：霓虹绿/金/红
- **字体**：添加 Brice Semi Expanded 字体（CDN）+ Inter 回退
- **视觉效果**：
  - 悬浮 LCD 面板效果（玻璃模糊 + 内发光边框）
  - 柔和漫射光背景（多层渐变动画）
  - 景深模糊效果（body::before 脉冲动画）
  - 优雅渐变过渡（cubic-bezier 缓动）
  - 动态环境反射（hover 时发光增强）
- **组件更新**：
  - .panel: 玻璃态 + 顶部渐变线 + hover 发光
  - .btn-primary: 渐变背景 + 霓虹投影
  - .option-card, .choice-btn: 扫光动画 + 边框发光
  - .mode-card: 全息卡片效果
  - .recommendation-item: 悬浮卡片动画
  - 滚动条: 自定义霓虹紫渐变样式
- **内联样式更新**：dropzone、notice、success 提示全部更新为深色主题

Files: `templates/index_v2.html`

## 2025-12-23: UI v3 Multi-Step Layout Refactor

- 创建 `index_v3.html` 新模板，采用组件化多步骤布局
- 四个核心组件：
  1. **TopBar**: 顶部导航栏（品牌标识 + 模式切换 + 退出）
  2. **StepNav**: 步骤导航（5 步：目的 → 个人信息 → 目标人选 → 模板 → 生成）
  3. **ModeSelector**: 模式选择卡片（快速 vs 专业）
  4. **PrivacyModal**: 隐私声明弹窗（同意后才能继续）
  5. **PurposeStep**: 目的选择步骤（4 卡片选择 + 领域选择）
- 设计风格：简洁、现代、Apple 风格设计系统
- CSS 变量：统一颜色、间距、圆角、阴影、过渡
- 状态管理：使用单一 `state` 对象管理全局状态
- 添加 `/v3` 测试路由（保持 v2 为默认）

Files: `templates/index_v3.html`, `app.py`

## 2025-12-23: Finance Track Fixed Questions (IBD Structure + Career Ladder + Bank Types)

- Professional Mode - Finance track 现在使用固定多选题而非动态生成
- 问题基于三个参考文档设计：
  - `question_fin/finance_structure.txt`: IBD 组织结构（Product Groups vs Sector Groups）
  - `question_fin/investment_banking_career_ladder.txt`: 职级阶梯（Analyst → MD）及各级职责
  - `question_fin/different_kinds_investment_banks.txt`: 银行类型分类
- **6 个固定多选题**（按逻辑顺序）：
  1. **银行类型偏好**：Bulge Bracket / Commercial Banks with IB / Middle Market / Boutiques（含具体公司示例）
  2. **Product vs Sector 偏好**：Product Groups / Sector Groups / Both
  3. **Product Group 细分**（条件显示：仅当选择 Product/Both）：M&A Advisory, DCM, Leveraged Finance, ECM
  4. **Sector Group 细分**（条件显示：仅当选择 Sector/Both）：TMT, Healthcare, FIG, Energy, Industrials, Consumer, Real Estate, Sponsors 等
  5. **目标级别偏好**：Analyst(1-3年) / Associate(4-6年) / VP/Director(7-9年) / ED/SVP(10-12年) / MD(12+年)
  6. **联系目的**：Learn about role / Career advice / Referral / Industry insight / Mentorship
- **UI 特性**：
  - 多选支持（复选框样式）
  - 条件逻辑跳转（根据 Q2 决定是否显示 Q3/Q4）
  - 完成后显示偏好摘要
  - Skip 跳过支持
- Academic track 保持动态问题生成（调用 API）

Files: `templates/index_v2.html`

## 2025-12-21: Prompt Data Collection Feature

- 新增 Prompt 数据收集功能，用于收集 `find_target` 和 `generate_email` 两个步骤的 prompt 与输出。
- 数据格式：ID、用户信息、prompt_find_target、output_find_target、prompt_generate_email、output_generate_email、时间戳。
- 新增 `src/services/prompt_collector.py` 服务模块，使用单例模式管理会话。
- 数据存储位置：`data/prompt_logs/{日期}/{时间戳}_{id}.json`。
- 环境变量 `COLLECT_PROMPTS` 控制是否启用（默认启用）。
- 支持导出为 JSONL/CSV 格式供后续分析。

Files: `src/services/prompt_collector.py`, `src/email_agent.py`, `app.py`

## 2025-12-21: Finance Benchmark v0.1 - Richer Context Fields

- Expanded the finance benchmark schema/cases to include more structured context for realistic evaluation (especially for banker workflows): role titles, seniority, bank tier, coverage/product group, sector/stage, recruiting context, contact channels, plus an optional `email_spec` for explicit ask/value/hard rules/compliance.
- Updated rubric/templates so teams can collect this info via interviews/surveys and convert real samples into reproducible benchmark cases.

Files: `benchmarks/finance/schema_v0.json`, `benchmarks/finance/finance_v0.json`, `benchmarks/finance/README.md`, `benchmarks/finance/anonymization_and_labeling_template.md`, `benchmarks/finance/rubric_v0.md`, `benchmarks/finance/survey_template.md`, `README.md`

## 2025-12-21: Finance Survey v1 (Google Forms Ready)

- Added a copy-paste-ready finance outreach survey for Google Forms/Typeform, designed to collect both benchmark-ready cases and marketing research signals without asking for sensitive information.

Files: `benchmarks/finance/survey_v1_google_forms.md`, `benchmarks/finance/survey_template.md`, `benchmarks/finance/README.md`

## 2025-12-20: Finance Benchmark Starter Pack (v0)

- Added a finance-focused benchmark starter kit: schema, 10 synthetic cases (format demo), rubric, anonymization/labeling template, and a marketing research + survey template.
- Goal: make “find people” and “generate email” evaluation more reproducible (expected constraints + evidence-aware scoring), and provide a clear path to replace synthetic cases with anonymized real samples.

Files: `benchmarks/finance/README.md`, `benchmarks/finance/schema_v0.json`, `benchmarks/finance/finance_v0.json`, `benchmarks/finance/rubric_v0.md`, `benchmarks/finance/anonymization_and_labeling_template.md`, `benchmarks/finance/survey_template.md`, `README.md`

## 2025-12-16: Context Expansion (Targeting + Email)

- Step 3: added optional structured targeting inputs (ideal target description, must-have/must-not keywords, location, reply vs prestige, examples, evidence) for both Quick and Professional, and passed them into `preferences` for `POST /api/find-recommendations`.
- Recommendations: updated prompt + normalization so each candidate can include `evidence`, `sources`, and `uncertainty` (and the UI modal now surfaces them).
- Step 4: added optional email instruction inputs (goal, ask, value, constraints, hard rules, evidence) and fed them into generation (goal/ask fields + sender free-text) to reduce hallucinations.
- Receiver enrichment: `POST /api/search-receiver` now returns `raw_text`, and `POST /api/generate-email` preserves receiver `sources` so the email prompt can cite verifiable info.
- Updated `README.md` workflow diagram to show the time order of info collection and what each core API call can use.

Files: `templates/index_v2.html`, `src/email_agent.py`, `app.py`, `README.md`

## 2025-12-13: UI Polish (Apple-like Visual Refresh)

- Updated `templates/index_v2.html` styling to a lighter, glassy “Apple-like” look (subtle gradients, soft borders/shadows, blue accent).
- Quick Start: Step 2 now asks for optional resume/profile link/notes first; only if those are empty it shows the 5-question questionnaire (generated in one request).
- Quick Start: resume upload uses the same drag & drop dropzone pattern as Professional mode.
- Quick Start: the 5-question builder is generated only after clicking “Generate Questions”.
- Step 3 target preferences: removed the static 5-field form; use the dynamic preference questions + Step 1 field as defaults.
- Hard-capped dynamic questionnaires to `max_questions` to prevent over-generation.
- Quick Start: added a small onboarding modal shown when entering Step 1 (with “Don’t show again”).
- Quick Start: clarified onboarding copy to explain what context is collected and why.
- Documented product principle that everything should serve the two core tasks (find targets + generate emails), emphasizing structured context, evidence/uncertainty, and a feedback loop (`AGENTS.md`, `note.md`).

## 2025-12-12: v3.0 - Mode Selection (Quick Start & Professional) 🚀

### New Features

- **Mode Selection Screen**
  - Added beautiful mode selection interface after login
  - Two modes: "Quick Start" and "Professional"
  - Card-based UI with icons, descriptions, and feature lists

- **Privacy Notice** 🔒 (NEW!)
  - Displayed after mode selection, before proceeding
  - Informs users that:
    - Personal info and answers are only used for target matching and email generation
    - Data is not shared with third parties
    - Uploaded resumes are processed securely, not stored permanently
    - Session data is cleared when app is closed
  - User must acknowledge to continue

- **Quick Start Mode** ⚡
  - Designed for users without a resume
  - No document upload required
  - Uses interactive questionnaire to build user profile
  - Smart target matching with recommendations
  - Streamlined 5-step workflow:
    1. Purpose & Field selection
    2. Quick Profile Builder (questionnaire)
    3. Find Targets (manual or AI-recommended)
    4. Email Template selection
    5. Generate personalized emails

- **Professional Mode** 💼 (NEW!)
  - **Track Selection**: Choose between Finance or Academic
  - **Resume Upload**: Required for profile analysis
    - Drag & drop or click to upload
    - AI-powered resume parsing
    - Shows extracted profile summary
  - **Target Choice**: 
    - "Yes, I Have Targets" → Direct to manual input
    - "Find Targets for Me" → AI recommendations
  - **Professional Preference Questions**:
    - Track-specific questions
    - Based on resume analysis
    - Generates highly relevant recommendations
  - **Finance Track Features**:
    - Investment banking connections
    - Hedge fund & asset management
    - Fintech startups & VCs
    - Quantitative research roles
  - **Academic Track Features**:
    - Professor & researcher connections
    - PhD & postdoc applications
    - Research collaborations
    - Academic conference networking

### Professional Mode Flow

```
Mode Selection → Track (Finance/Academic) → Resume Upload → Target Choice
    ↓ (Have targets)                    ↓ (Need recommendations)
    Manual Input                        Preference Questions → AI Find Targets
    ↓                                   ↓
    Step 3 (Find Targets) → Step 4 (Template) → Step 5 (Generate)
```

### Modified Files

- `templates/index_v2.html`:
  - Added Professional mode panels:
    - `pro-track-selection`: Finance/Academic choice
    - `pro-resume-upload`: Resume upload with drag & drop
    - `pro-target-choice`: Have targets vs need recommendations
    - `pro-preferences`: Professional preference questions
  - Added new state variables:
    - `proTrack`: 'finance' or 'academic'
    - `proTargetChoice`: 'have' or 'need'
    - `proPreferenceHistory`: Preference Q&A history
  - Added new functions:
    - `setupProfessionalMode()`: All professional flow logic
    - `uploadProResume()`: Handle resume upload
    - `loadProPreferenceQuestions()`: Load track-specific questions
    - `renderProPreferenceQuestion()`: Render interactive questions
    - `findProTargets()`: Find recommendations based on profile

### UI/UX Improvements

- Professional mode cards with track-specific styling
- Drag & drop resume upload area
- Resume summary display after upload
- Track-aware preference questions
- Seamless transition from professional flow to main email generation
- Enlarged the Step 5 “Custom” tone instruction textbox for easier editing
- Quick Start questionnaire now generates a full 5-question set upfront (instead of per-question generation)
- Simplified the top-right mode switcher (removed redundant status text)

---

## 2025-12-05: v2.2 - Gemini Google Search Integration 🔍

### Bug Fixes

- **Fixed OpenAI web_search Error**
  - OpenAI API does not support `web_search` tool type (only `function` and `custom`)
  - Error: `Invalid value: 'web_search'. Supported values are: 'function' and 'custom'.`
  - Solution: Disabled OpenAI recommendations by default, switched to Gemini

- **Fixed DuckDuckGo Timeout on Render.com**
  - DuckDuckGo search was blocked/timeout on cloud servers
  - Error: `Connection to html.duckduckgo.com timed out`
  - Solution: Use Gemini's built-in Google Search grounding instead

- **Fixed Step 1 Field Selection Missing**
  - Field selection (AI/ML, Software, Finance, Other) was lost during git merge
  - Restored full Step 1 with both Purpose and Field options

### New Features

- **Gemini Google Search Grounding**
  - Uses Gemini's native `google_search_retrieval` tool
  - Real-time web search for finding target recommendations
  - Finds verified, currently active professionals
  - Much faster and more reliable than external scraping

### Modified Files

- `config.py`:
  - Added `GEMINI_SEARCH_MODEL`: Model for search-enabled requests
  - Added `USE_GEMINI_SEARCH`: Toggle for Google Search grounding (default: true)
  - Changed `USE_OPENAI_WEB_SEARCH` default to `false`
  - Changed `USE_OPENAI_RECOMMENDATIONS` default to `false`

- `src/email_agent.py`:
  - Added `_call_gemini_with_search()`: Gemini API call with Google Search grounding
  - Updated `find_target_recommendations()`:
    - Primary: Gemini with Google Search (new)
    - Fallback 1: OpenAI with web_search (disabled)
    - Fallback 2: OpenAI with manual scraping (disabled)
    - Fallback 3: Gemini without search

- `templates/index_v2.html`:
  - Restored Field selection in Step 1
  - Added `field` and `fieldCustom` to state
  - Added `fieldLabels` mapping
  - Added `getFieldLabel()` function
  - Updated `checkStep1Valid()` to require both purpose and field
  - Updated `getFieldText()` to prioritize Step 1 field

- `README.md`: Updated to v2.2 with new features and bug fixes

### Technical Details

```python
# Gemini Google Search grounding usage
gemini_model = genai.GenerativeModel(
    model,
    generation_config=generation_config,
    tools="google_search_retrieval"  # Enable Google Search
)
response = gemini_model.generate_content(prompt)
```

### Recommendation Flow (v2.2)

1. **Gemini + Google Search** (Primary) - Real-time web search
2. OpenAI + web_search (Disabled) - API doesn't support this
3. OpenAI + manual scraping (Disabled) - Timeout issues
4. **Gemini without search** (Fallback) - Uses model knowledge

---

## 2025-12-02: v2.1 - Enhanced Target Management 🆕

### New Features

- **Manual Target Document Upload**
  - Support for PDF, TXT, and MD file uploads when manually adding targets
  - AI-powered profile extraction from uploaded documents
  - Auto-fills name and field from extracted data
  - Skips web search for targets with uploaded documents (uses local data)

- **Target Profile Preview Modal**
  - "📋 View" button on each recommended target
  - Modal shows: name, position, match score, education, experience, skills, projects, match reason
  - "Select This Target" button to add directly from modal
  - Click outside modal to close

### Modified Files

- `app.py`:
  - Added `/api/upload-receiver-doc` endpoint for target document upload
  - Supports PDF (using existing PDF parser) and TXT/MD (using Gemini)

- `src/email_agent.py`:
  - Added `parse_text_to_profile()`: Parse text content into structured profile

- `templates/index_v2.html`:
  - Version badge updated to v2.1
  - Added file upload input in manual target section
  - Added profile modal HTML and styles
  - Updated JavaScript:
    - `setupTargetDocUpload()`: Handle target document uploads
    - `uploadTargetDoc()`: Upload and process target documents
    - `openProfileModal()`: Display target profile in modal
    - `closeProfileModal()`: Close the modal
    - `selectFromModal()`: Select target from modal view
    - `renderRecommendations()`: Added "View" button to each recommendation
    - Updated `generateAllEmails()`: Skip web search if profile data exists

### UI Improvements
- Modal overlay with smooth animations
- Profile sections with icons (🎯 Position, 📊 Match Score, 🎓 Education, etc.)
- Loading state for document analysis
- Success message after document upload

---

## 2025-11-29: v2.0 - Web Interface with Smart Wizard 🎉

### New Features

- **Multi-Step Wizard Interface**
  - Step 1: Purpose & Field Selection
    - 4 purpose options: Academic, Job Seeking, Coffee Chat, Other
    - 4 field options: AI/ML, Software Engineering, Finance/Fintech, Other
    - Custom input support for both
  
  - Step 2: Profile Building
    - Resume upload option (PDF)
    - Quick questionnaire (5 questions) for users without resume
    - Each question has 4 options with custom input
  
  - Step 3: Target Discovery
    - Manual target input
    - AI-powered recommendation system (top 10 matches)
    - Match analysis with compatibility score
    - "Generate More" and "Add Manually" options
  
  - Step 4: Email Generation & Customization
    - Regenerate with style options:
      - More Professional
      - More Friendly  
      - More Concise
      - More Detailed
      - Custom instructions
    - Copy to clipboard functionality

- **Password Protection (legacy)**
  - Session-based authentication (removed in 2026-01-26, replaced by per-user accounts)

- **Render Deployment**
  - Live at https://coldemail-agent.onrender.com/
  - Gunicorn production server
  - Environment variable configuration

### New Files
- `templates/index_v2.html`: New wizard-style web interface
- `templates/login.html`: Login page
- `app.py`: Flask web application
- `Procfile`: Render deployment config
- `runtime.txt`: Python version specification

### Modified Files
- `src/email_agent.py`:
  - Added `generate_questionnaire()`: Generate profile questions
  - Added `build_profile_from_answers()`: Build profile from questionnaire
  - Added `find_target_recommendations()`: AI-powered target suggestions
  - Added `regenerate_email_with_style()`: Style-based email regeneration

- `src/web_scraper.py`:
  - Now uses Gemini's knowledge base first (fixes cloud server blocking)
  - Web scraping as fallback
  - Returns basic profile even if all methods fail

### New Dependencies
- `flask>=3.0.0`
- `gunicorn>=21.0.0`

---

## 2025-11-29: v1.2 - Switch to Gemini API

### Changes
- **API Migration**: Switched from OpenAI GPT-4o-mini to Google Gemini API
  - Default model changed to `gemini-2.0-flash`
  - Environment variable changed to `GEMINI_API_KEY` or `GOOGLE_API_KEY`
  - Removed `openai` dependency, added `google-generativeai` dependency

### Modified Files
- `src/email_agent.py`: Replaced OpenAI SDK with Gemini SDK
- `src/web_scraper.py`: Replaced OpenAI SDK with Gemini SDK
- `src/cli.py`: Updated default model name
- `requirements.txt`: Replaced dependency packages
- `README.md`: Updated API Key setup instructions

---

## 2025-11-29: v1.1 - Web Search Feature

### New Features
- **Web Search for Receiver Info**: Users only need to provide the receiver's name and field, and the system will automatically search and scrape relevant information from the web
  - Supports DuckDuckGo and Bing search engines
  - Automatically scrapes and parses web page content
  - Uses LLM to extract structured information (education, experience, skills, projects, etc.)

### New Files
- `src/web_scraper.py`: Web search and scraping module
  - `WebScraper` class: Search engine queries and web page scraping
  - `extract_person_profile_from_web()`: Extract person information from the web

### Modified Files
- `src/email_agent.py`: 
  - Added `from_web()` class method to `ReceiverProfile`
  - Added `sources` field to record information sources
- `src/cli.py`:
  - Added `--receiver-name` parameter
  - Added `--receiver-field` parameter
  - Added `--max-pages` parameter

### New Dependencies
- `requests>=2.31.0`
- `beautifulsoup4>=4.12.0`
