---
name: wechat-article-builder
description: 将口播稿/草稿改写为微信公众号图文格式（单文件 HTML），并内置「复制全文到公众号」按钮，保证粘贴到公众号编辑器后样式不丢失（背景色、边框、卡片、表格等）。当用户要求"改为公众号图文格式"、"做成公众号文章"、"加复制按钮"、"复制到公众号"时使用。核心踩坑知识：公众号只认内联样式；div 会被剥离样式、section 也不形成可靠段落边界 → 最终必须把视觉块压平成顶层 <p>；background 简写与 border 三件套会被丢弃 → 边框必须是 border-left 这类简写、底色必须是 background-color。启动口令：「用 wechat-article-builder 做公众号图文」；自检口令：「跑一遍 wechat-article-builder 的自检」。
agent_created: true
allowed-tools: Bash,Read,Write,Edit
---

# 微信公众号图文制作 Skill

## Overview

把用户的口播稿 / 资讯草稿改写为适合微信公众号发布的单文件 HTML 图文，并提供一个复制按钮。点击按钮后自动：内联化所有计算样式 → 把所有视觉块**压平成顶层 `<p>`** → 自己序列化 HTML 写入剪贴板，用户可直接粘贴到公众号编辑器，格式（背景色、圆角、边框、表格、强调色）完整保留。

> ⚠️ 下方「文章 HTML 结构 / 复制按钮实现（踩坑点 1–3）」是 2026-08 的第一轮方案，
> 其中「所有 `div` → `section`」已被 2026-11 的真实粘贴反馈**推翻**（section 不形成可靠段落边界）。
> **一律以「2026-11 实战更新」章节为准**，不要按第一轮的 `div → section` 生成新稿。

## 触发场景

- "把这篇改成微信公众号图文格式"
- "做一篇公众号文章"
- "加一个复制按钮，能粘贴到公众号"
- "粘贴到公众号后样式丢了/灰色块没了/绿色标题线没了"

### 启动口令（重启 WorkBuddy 后直接说这一句）

> **用 wechat-article-builder 做公众号图文**

WorkBuddy 只在**启动时**扫描 `C:\Users\MSI\.workbuddy\skills\`。C 盘这个目录是目录联接，
新建或改动 skill 后**必须重启 WorkBuddy** 才会出现在可用列表。

自检口令：**跑一遍 wechat-article-builder 的自检** —— 执行
`node D:\00WorkBuddy\.workbuddy\skills\wechat-article-builder\references\test_copy.js`，
16 项全绿即说明 skill 已加载、复制脚本可用。做新稿子前建议先跑一次。

### 文件位置

| 用途 | 路径 |
|------|------|
| skill 本体（改这里） | `D:\00WorkBuddy\.workbuddy\skills\wechat-article-builder\` |
| WorkBuddy 加载点（目录联接，勿直接编辑） | `C:\Users\MSI\.workbuddy\skills\wechat-article-builder\` |
| 工程快照（随 git 走） | `D:\WorkBuddy\Claw\wechat-knowledge-animation\skills\wechat-article-builder\` |
| 线上仓库 | `https://github.com/newbaisays-aigc/wechat-knowledge-animation` |

**改完本体必须把 `SKILL.md` 同步到工程快照并提交**，否则 git 里的版本会落后；
`references/copy-script.js` 同步改了也要一并复制过去。

## 语气规范（用户已确认的偏好）

- 微信图文稿语气 = **专业 6 分 : 口语 4 分**（与口播稿相反）
- 去掉：波浪号（~）、语气词（阿、哦、呀）、"糊弄事"等重口语特征
- 保留：第一人称叙事（带孩子丢身份证这类个人故事）、少量生动比喻（"亲儿子"、"看奏折的感觉"、"搭把手"）、温和收束语（"可以等一等"）
- 技术部分用"博主做功课"的方式讲（"实际用下来体验不错，顺手查了一些技术资料"），不写成百科搬运腔
- 小标题书面化（如"思考在后台，答案即时到"），数据表述规范化（128K tokens 约 9-10 万字）

## 文章 HTML 结构

单文件 HTML，`max-width: 680px` 居中容器，微信绿 `#07c160` 主题。常用板块：

| 板块 | class | 关键样式 |
|------|-------|---------|
| 标题区 | `.header` | 居中、下边框分隔 |
| 引导语 | `.lead` | 绿色渐变底、白字、圆角卡片 |
| 小标题 | `.section-title` | **border-left: 4px solid #07c160** + padding-left |
| 能力卡片 | `.ability-card` | 浅灰底 #f9f9f9、圆角、带数字圆标 |
| 场景示例 | `.scene-box` | 白底 + 绿色虚线边框 |
| 技术解读 | `.tech-section` | 浅蓝渐变底 + 蓝色 tech-badge |
| 参数表格 | `.tech-table` | 绿表头白字、隔行浅灰 |
| 架构图 | `.arch-diagram` | 四层彩色横条 + 箭头 |
| 引用块 | `blockquote` | 左侧绿色竖线 + 浅灰底 |
| 结语 | `.conclusion` | **灰色底 #f5f5f5**、居中、绿色胶囊标签 |
| 信息来源 | `.source-section` | 浅灰块 + 细边框 + **黄色 badge**，下方 `<ol>` 列来源，末尾 `.source-note` 放免责声明 |
| 底部 | `.footer` | 灰色小字、上边框 |

## 复制按钮实现（核心知识）

### 踩坑点 1：公众号编辑器只认内联样式

编辑器粘贴时忽略 CSS class，只认 `style="..."` 内联样式。必须在复制时用 `getComputedStyle` 把关键样式属性全部转为内联。

### 踩坑点 2（关键）：div 的背景色和边框会被剥离

**公众号编辑器会丢弃 `div` 元素上的 `background-color` 和 `border`，但 `section` 元素的样式会被保留。** 这是本次任务中"底部灰色块丢了、绿色标题线丢了"的根因。当时的解决方案：样式内联完成后，把所有 `div` 递归转为 `section`。

> ⚠️ **此结论只解决了「样式保不保留」，没解决「段落边界」**，已被第二轮推翻。
> 现在 `section` 只作为中间态，最终必须压平成顶层 `<p>`。见「规则 1」。

### 踩坑点 3：border 简写属性可能取不到值

`getComputedStyle().getPropertyValue('border-left')`（简写）在部分浏览器返回空。必须同时采集 longhand 属性：`border-left-width` / `border-left-style` / `border-left-color`（四条边各三个）。

### 完整脚本

见 `references/copy-script.js`。核心逻辑分五步：

1. **内联样式**：克隆源容器，遍历元素对，把 computed 值写入 `el.style`（属性清单见脚本内 `props`）
2. **保底转换**：`div` / `figure` → `section`，`figcaption` → `p`
3. **压平成顶层 `<p>`**：把一切视觉块摊平成兄弟段落，容器样式迁移到第一个块级子节点
4. **图片处理**：去掉 `loading` / `decoding`，让每张图独占一个 `<p>`
5. **自己序列化 HTML 写进剪贴板**：`ClipboardItem` 写 `text/html`；不可用时回退 `execCommand('copy')`

## 2026-11 实战更新（第二轮，这轮推翻了第一轮的一部分）

> 来源：`wechat-knowledge-animation` 公众号工程的真实粘贴反馈 + 沙盒模拟截图验收。
> 验证脚本：`D:\WorkBuddy\Claw\wechat-knowledge-animation\tools_skill_copy_test.js`（fixture，15 项断言）
> 与 `tools_skill_real_test.js`（真实文章跑一遍，15 项断言）。改完脚本必须跑这两个，全绿才算能用。

### 规则 1：section 也不形成可靠段落边界 → 必须压平成顶层 `<p>`

第一轮只做到「div → section」是不够的。实测：连续 `section` 会被公众号**并进同一段**；
`section` 里直接放 `<img>` 时，公众号会把 img 的 **alt 文本吐进正文**，和后面的图注连成一段。

**`<p>` 是公众号唯一可靠形成段落边界的块级元素。** 所以最终形态是：

- 顶层只允许 `<p>` / `<h1-h6>` / `<ul>` / `<ol>` / `<blockquote>` / `<table>` / `<hr>`
- 容器（div/section/figure）的样式迁移到它的第一个块级子节点，再把容器拆掉
- `<p>` 里不能嵌 `<p>`（浏览器会自动拆散嵌套 p）→ 图片独占 `<p><img></p>`，图注是紧跟其后的独立 `<p>`

### 规则 2：`font-family: inherit` 会让整条 style 失效

一旦某个元素出现 `font-family: inherit`，公众号会丢弃**整条** style（连底色一起丢）。
内联化时遇到 `inherit` / `initial` 一律不写，改用具体字体栈。

### 规则 3：`background` 简写会被丢弃 → 只用 `background-color`

采集 computed 样式时**不要采集 `background` 简写**：它会把 `background-color` 覆盖成透明，
且公众号不认这个简写。只采 `background-color`（`background-image` 也不要——公众号同样不认）。

### 规则 4：`border` 简写会覆盖 `border-left` → 边框必须输出方向简写

采集 computed 样式时不要采 `border` 简写（`border: 0` 会把 `border-left` 一起清掉）。
但 Chrome 的 `style.cssText` 会把四方向相同的边框**折叠回** `border-width/style/color` 三件套，
公众号同样不认 → 所以要在序列化层把三件套还原成 `border-top/right/bottom/left` 四个简写。

> CSSOM 陷阱：`removeProperty('border-width')` 会连带清掉 `border-left-width`。
> 必须**先取值 → 再 remove 三件套 → 最后 setProperty 方向简写**，顺序反了刚设的简写也被干掉。

### 规则 5：图片不能带 `loading="lazy"`

视口外的图根本不发起请求（实测裂图 5 张）。复制前删掉 `loading` 和 `decoding`。

### 规则 6：灰底传染

正文容器固定 `#ffffff`。容器用 `transparent` 会把 body 灰底一起复制进剪贴板，
粘贴后每段底部都是灰块。

### 规则 7：不要用 `execCommand('copy')` 的自动序列化

Chrome 复制富文本时会把 `background-color` **折叠成 `background` 简写**（浏览器行为，控制不了），
公众号不认 → 底色整块丢。
正确做法是**自己序列化 HTML 字符串**，用 `style.cssText`（保留 `background-color` longhand），
再通过 `navigator.clipboard.write(new ClipboardItem({'text/html': blob, 'text/plain': blob}))` 写入。

### 复制完成后的自检清单

- [ ] 顶层无 `section` / `div` / `figure` / `figcaption`
- [ ] 无嵌套 `<p>`
- [ ] 每张图独占一个 `<p>`，图注是紧跟的独立 `<p>`
- [ ] 底色是 `background-color`，不是 `background`
- [ ] 边框是 `border-left: 6px solid ...`，不是 `border-width/style/color` 三件套
- [ ] `font-family` 不是 `inherit`
- [ ] 图片没有 `loading` 属性

## 信息来源标注规范（必做）

文章底部必须加「信息来源」区块（`.source-section`），规则：

1. **写作时先 WebSearch 核实**每个技术参数，记录出处，写完后整理成 `<ol>` 列表放在页脚前
2. **列表条目格式**：`出处 + 发布时间/平台 —— 支撑了哪些参数`，例如：
   - "微信AI团队技术论文《Hidden Decoding》（2026年7月）—— WeLM MoE 架构细节、128K 上下文、隐式解码原理"
3. **优先级排序**：一手来源（官方论文、官方海报、官方客服回应）在前，媒体转述（腾讯新闻、凤凰科技、IT之家、新浪科技、搜狐等）居中，汇编类（百度百科词条）垫底
4. **区分官方与媒体归纳**：官方口径（参数、协议）直接引用；媒体归纳（如"四层能力架构"这种灰测观察总结）标注"媒体灰度测试观察"，不要在文中写死成官方说法
5. **不放超链接**：公众号正文中的链接复制后会丢失且影响排版，只写来源名称；链接可保留在交付说明里给用户
6. 免责声明放 `.source-note`（如"小微仍在灰度测试中，功能以实际体验为准"），`.footer` 只留一句"本文由博主整理发布 · 技术资料来自公开论文及媒体报道"

## 公众号文章编辑器（可交互工具）

> ⚠️ **状态：文件已丢失（2026-11-14 核实）**。`wechat-article-editor.html` 在本机全盘找不到，
> 本 skill 目录里只剩 `SKILL.md` + `references/`。下面这段是当初的设计记录，
> **照着做等于要从零重建**。不重建的话，做新文章走「纯 HTML + 复制按钮」这条轻量路线即可，
> 本 skill 现在完全支持（`references/copy-script.js` 已自带完整公众号兼容规则）。
> 设计里有两条值得保留：左侧输入极简（用户只给一段内容描述，拆分交给 AI）、
> AI 返回结构化 JSON（title/blocks/conclusion/sources）再渲染。

基于本 skill 构建的可交互编辑器页面 `wechat-article-editor.html`，Notion 风格 UI。

### 编辑器工作流（简化版 —— 用户明确要求左侧极简）

1. **输入内容**：一个大文本框（原始文稿/口播稿/要点）+ 可选润色需求输入框
2. **AI 润色**：点击「开始润色」→ 页面生成带 skill 规范的提示词 → 自动复制到剪贴板 → 粘贴到 WorkBuddy
3. **粘贴结果**：WorkBuddy 返回 JSON → 粘贴回页面结果区 → 600ms 防抖自动解析 → 渲染预览
4. **复制发布**：点击「复制到公众号」→ 复用三步复制脚本

**关键原则：左侧输入要极简，不要堆砌结构化表单。** 用户只给一段内容描述，AI 完成拆分和润色。

### 提示词设计

页面内置提示词要求 AI 返回严格 JSON 格式：
- `title / author / date / intro` —— 文章信息
- `blocks[]` —— 正文区块，含 `type / title / content`，type 支持 10 种（text/heading/card/highlight/scene/tech/list/table/divider/blockquote）
- `conclusion / endTag` —— 结语
- `sources[]` —— 信息来源，含 `text / type`（official/media/wiki）
- `disclaimer / footer` —— 页脚

### JSON 解析容错

- 自动剥离 markdown 代码块标记（```json）
- 从文本中提取第一个 `{` 到最后一个 `}`
- 粘贴后 600ms 防抖自动解析，失败显示错误提示
- 结果区可手动编辑 JSON 微调内容

### API 直连（已预配置 DeepSeek）

页面已预填 DeepSeek API（端点 `https://api.deepseek.com/chat/completions`，模型 `deepseek-chat`），Key 来自本地 `models.json` 配置。「开始润色」默认走 API 直连模式，一键调用无需手动粘贴。如需切换其他模型，展开「API 直连」面板修改即可，配置保存在 localStorage。

### 页面结构

- 左 42% 编辑区：4 步引导条 + 状态指示栏 + 输入卡片 + 结果卡片 + API 配置（折叠）
- 右 58% 预览区：实时渲染 Notion 黑黄风格文章
- localStorage 持久化，刷新不丢内容

## 交付物

- 单文件 `wechat-article-<name>.html`（单次生成，含复制按钮）
- ~~`wechat-article-editor.html`（可交互编辑器）~~ **文件已丢失**（2026-11-14 全盘核实），见上文；需要时从零重建
- 修改后用 present_files 打开预览，告知用户按钮用法

## 依赖

- `node`：跑 `references/test_copy.js` 及工程内的 `tools_skill_copy_test.js` / `tools_skill_real_test.js`
- 共享无头浏览器 `D:\tools\remotion\browser\chrome-headless-shell\win64\chrome-headless-shell-win64\chrome-headless-shell.exe`
- 改完 `copy-script.js` 必须两套测试全绿才算能用；测试要把 fixture 落成文件再 `goto file://`，`page.setContent` 的 about:blank 没有 clipboard API

## 借鉴自 marketplace 同类 skill 的工程约定（2026-11-14 评估）

对比 `wechat-article-pro`（纯文档、零代码）与 `wechat-article-search`（搜狗微信爬虫，730 行 JS）后，**只吸收这三条**：

1. **声明能力边界**：frontmatter 写 `allowed-tools`，正文写清依赖。**不写运行时不认的 metadata 字段**——声明了却不生效，比不声明更误导。
2. **失败必须显式，不能伪装成空结果**：`wechat-article-search` 在 TLS 握手失败时 stdout 仍输出 `{"total":0,"articles":[]}`，只看结果会误判成"没有这类文章"。我们的验证脚本坚持「断言全绿才交付」，失败要打印具体原因。
3. **不可靠字段要显式标记**：对方用 `url_resolved: false` 标明解析失败。对应我们已有的做法：图片必须逐个 HTTP 探测可达性，**断言全绿 ≠ 线上能看**，CDN 地址"形式对"不等于"路径对"。

**明确不吸收**：

- `wechat-article-pro` 的"在公众号后台点按钮逐段录入"路线：绕开了粘贴兼容问题，与一键复制互斥；其 3000–5000 字刘润风格商业长文也不符合「小白姐姐」人设。可借鉴的只有「开篇现象 → 洞察 → 案例 → 结论」的内容骨架和「末尾不加话题标签 / 不用大量 emoji」这类发布禁止项，且我们已有语气规范，不重复堆。
- `wechat-article-search` 的搜狗爬虫：本机出口为美国 IP，实测 `weixin.sogou.com`、`v.sogou.com` 均 0.6 秒秒断（HTTP 000），而 `www.baidu.com`、`mp.weixin.qq.com` 均 200，属**域名级封锁，装了也跑不通**。
- 它的硬编码 cookie（`ABTEST=7|1716888919|v1` 是 2024 年时间戳、`IPLOC=CN5101` 与实际出口矛盾）、以及 `parseRelativeTime` 按 UTC、`formatChinaDateTime` 按 UTC+8 的**时区口径不一致**，都是反面教材。

## 注意

- 技术内容（大模型、协议等）先 WebSearch 核实再写，并按「信息来源标注规范」在文末列出来源（见上文）
- 用户可能多轮迭代语气（媒体腔→博主腔→专业:口语比例），每轮直接改写文件并刷新预览
- 语气规范与结构模板以本文件为准；编辑器页面已丢失，不要假设它存在
