# 用 WorkBuddy 做知识动画 · 完整图文教程

> 一篇公众号文章 + 全部素材快照。把口播稿和风格参考图，变成一条能发出去的动画视频。

## 这份仓库是什么

| 文件 | 用途 |
|---|---|
| `index.html` | 文章原文（完整版，含脚本与复制按钮） |
| `wechat.html` | **公众号粘贴版** —— 样式全内联、图片走 CDN 绝对地址，可直接全选复制进公众号编辑器 |
| `make-wechat.py` | 从 `index.html` 生成 `wechat.html` 的转换器 |
| `wecom_flatten_blocks.py` | 兼容层：把所有视觉块压平成顶层 `<p>`（公众号只有 `<p>` 形成可靠段落边界） |
| `wecom_style_fallback.py` | 兼容层：flex→block、渐变→实色、阴影→边框、absolute→inline-block、font-family:inherit→具体字体栈 |
| `wecom_div_to_section.py` | 兼容层（旧，已被 `wecom_flatten_blocks.py` 取代，保留备查） |
| `tools_sandbox_verify.js` | 验收工具：模拟公众号清洗规则并渲染，量化格式保留度 |
| `tools_verify.js` | 验收工具：28 项断言，校验「公众号不认的东西清干净、该留的留住了」 |
| `WECOM_COMPAT.md` | 公众号编辑器限制清单 + 修复前后基线数据 |
| `assets/` | 21 张标注截图 + 6 个 GIF 案例 |
| `cover.html` | 封面备选 |

## 发布到公众号

```bash
# 1. 生成公众号粘贴版（图片指向 jsDelivr CDN）
python make-wechat.py \
  --base https://cdn.jsdelivr.net/gh/newbaisays-aigc/wechat-knowledge-animation@master

# 2. 浏览器打开 wechat.html → 点顶部「复制全文」→ 粘贴进公众号编辑器
```

图片走 `cdn.jsdelivr.net/gh/...` 而不是 `raw.githubusercontent.com`，因为后者在境内经常被卡断，微信抓图会失败。

### 顶部的复制工具条

`wechat.html` 顶部有一条固定工具条（`📋 公众号粘贴版`）：

| 按钮 | 行为 |
|---|---|
| **复制全文** | 一键把正文富文本写进剪贴板（含 21 张 CDN 图片地址），粘到公众号即带样式和图片 |
| **全选正文** | 只高亮选中正文，由你自己按 `Ctrl+C` / `⌘+C` |

工具条放在 `<article>` **之外**，不会混进公众号正文。即使你按了 `Ctrl+A`，复制事件也会被拦截改写为纯正文。

### 复制的是「正文」，不含标题区

文章开头的三行——品牌名（`小白姐姐工作室出品`）、大标题、署名行（`小白姐姐 · AI 实操教程 · 2026 年 11 月`）在 `wechat.html` 里被标记为 `data-wx-chrome`，**复制时整块跳过**。

原因：公众号的标题、作者、发布时间是编辑器里的独立输入框，粘进正文会重复一遍。所以正确流程是：

1. 公众号编辑器的**标题框**里手填标题
2. 回到 `wechat.html` 点「复制全文」
3. 粘贴到公众号的**正文区**（从「大家好，我是小白。」开始）

页尾的署名（「小白姐姐工作室出品」）属于正文，会正常带上。

### 粘贴后每段出现灰色色块？（已修复）

早期版本粘贴到公众号后，每段文字后面都跟一条灰色底块。根因不在公众号，而在转换脚本：

`rewrite()` 原本把 `<article>` 的背景改写成 `transparent`。浏览器复制时会把「透明底下的实际底色」= `body` 的 `#f3f5f2` 写进剪贴板，并传染给每一个透明的后代元素 —— 实测 51 个 `<p>` 里有 30 个被带上 `rgb(243,245,242)`，公众号照搬后每段就成了灰条。

现在 `<article>` 与 `<body>` 都保持白底，灰底计数 **61 → 0**。设计意图的底色全部保留：

| 元素 | 底色 |
|---|---|
| `.hl` 绿色高亮 | `#eaf6ef` + 底部渐变下划线 |
| `.note` 提示框 | `#eef7f2` |
| `.prompt` 提示词块 | `#183c30`（深绿底白字） |
| `.site` 网址卡 | `#f4faf7` |

验证方式：把剪贴板里的 `text/html` 渲染进白底容器，统计段落实际背景色 —— 51 个段落中灰底段落 0 个。

### 粘贴后块级结构塌陷？（已修复）

粘贴后流程卡片挤成一行、提示框和网址卡没底色、图注黏进正文 —— 根因是**公众号编辑器白名单比想象的窄**，而非我们页面写错了。

公众号新版编辑器底层是 ProseMirror，限制如下：

| 类别 | 内容 |
|---|---|
| 稳定依赖标签 | `p` `span` `strong` `em` `ul` `ol` `li` `a` `img` `section` `blockquote` `h1`-`h6` `table` 系列 `hr` `sup` `sub` `u` `pre` `code` `br` |
| **会降级（样式跟着丢）** | `div` `figure` `figcaption` |
| 不支持 | `script` `style` `iframe` `video` |
| 会被清除 | `class` `id` `data-*` |
| 不支持样式 | `background` 简写（只认 `background-color`）、`background-image` 渐变、`box-shadow`、`display:flex`/`grid`、`position:absolute` |

`div` 被降级成 `p` 时，**连同它身上的内联样式一起丢失** —— 所有靠容器承载样式的卡片、提示框、网址卡、图注就全塌成了连续文本。

`make-wechat.py` 因此加了一道兼容降级（`apply_wecom_compat`）：

| 问题 | 处理 |
|---|---|
| `div` / `figure` / `figcaption` 被降级 | 换成 `section` / `section` / `p`（图注因此独立成段） |
| `display:flex` 无效 | 容器降为 `block`，`gap` 转 `margin`（行内→右外边距，列/换行→下外边距，避免双倍间距） |
| `background` 简写丢失 | 完整拆解为 `background-color` / `background-image` / `background-repeat` |
| `linear-gradient` 丢失 | 实色化；`.hl` 高亮用 `border-bottom` 补出底线 |
| `box-shadow` 丢失 | `.pick` 改用 `border-bottom` |
| `position:absolute` 错位 | 按特征组合分流：24px 编号徽章保留圆形外观改 `inline-block`；7px 空圆点保留绿点色 |

### 绝对定位元素的分流规则

一刀切删掉 `position:absolute` 会连步骤编号一起弄丢。改成按**尺寸 + 是否有文字**判断用途，不依赖 class 名：

| 特征 | 判定 | 处理 |
|---|---|---|
| 20~30px 见方 + 有文字 | 步骤编号徽章 | 保留圆形外观（宽高/圆角/底色/字色/行高），改 `inline-block` + `margin-right:8px` |
| ≤10px 见方 + 无文字 | 列表绿圆点 | 保留 `#4da783` 圆点，改 `inline-block` + 右侧留白 |
| 其余 | — | 退化为普通行内元素 |

几何还原：父级 `padding-left` 让位给原本的绝对定位坐标，子元素用于抵消 padding 的负 `margin-left` 同步补偿 —— 文字既不重叠也不跑位。

### 列表的收尾

圆点和徽章都是自己画的，列表不再需要原生缩进：

| 项 | 处理 | 原因 |
|---|---|---|
| `list-style` | **保留 `none`** | 改成 `disc` 会变成双圆点 |
| 列表左内边距 | 归 0 | 原生缩进会多出一截空白 |
| 列表项 `padding` | 压成一条声明 | 避免 `padding` 与 `padding-left` 同时存在 |
| `position:relative` | 清理 | 已无绝对定位子元素，不需要定位上下文 |

降级顺序必须在 `inject_toolbar` **之后**——工具条与「复制小提示」条是运行时插入的，提前转换会漏掉；工具条本身要保留 `display:flex`（按钮横排），所以降级前先取出、处理完再放回。

修复前后（`tools_sandbox_verify.js` 实测）：

| 指标 | 修复前 | 修复后 |
|---|---|---|
| `background` 简写 | 62 | **0** |
| `display:flex` | 11 | **0** |
| 渐变 / 阴影 / absolute | 8 / 2 / 7 | **0 / 0 / 0** |
| 有底色的容器 | **0** | **22** |
| 步骤编号徽章 | **0** | **4** |
| 灰底段落 | 30 | **0** |

本地验收：

```bash
node tools_verify.js          # 28 项断言
node tools_sandbox_verify.js  # 模拟公众号渲染并截图
```

`tools_sandbox_verify.js` 会把剪贴板内容按公众号规则清洗一遍再渲染，所见即公众号里的效果。

### 第二轮塌陷：`<section>` 也不行，段落被并成一段（已修复）

第一轮修复把 `div` 换成 `section` 后，公众号里的**前半段**（流程卡片、提示框）正常了，
但**第 3 步往后的提示词块、图片、图注全糊成一片连续文字**：

```
2方法二：给它你的口播稿，和参考图如果你有设计好的文稿、音频，以及想要的风格，也可以这样和它说：
长按下方文字复制用knowledge视频skill，帮我做一个知识动画……A｜3D 据数据新闻、行业报告、财报、产品发布
```

逐字比对剪贴板载荷后，两个根因浮出来：

| 根因 | 现象 | 修复 |
|---|---|---|
| **`<section>` 不形成可靠的段落边界** | 连续的 section 被并进同一个段落；`<section>` 内直接放 `<img>` 时，img 的 alt 文字被吐进正文，与图注连成一段 | 所有视觉块压平成**顶层 `<p>`**，`<p>` 内部只留行内内容；图片独占 `<p><img></p>`，图注是独立 `<p>` |
| **`font-family: inherit` 让整条 style 失效** | 深绿底的 `.prompt` 块底色全丢、变成白底黑字（同一份 HTML 里浅绿底的 `.note` 却正常） | `inherit` / `initial` 一律换成具体字体栈 |

社区实测也印证了第一条：「section 标签的 margin/padding 被重置」「多层嵌套全部塌缩成纯文本」。

所以现在产物的规则是：

* 顶层只有 `<p>` / `<h1-h6>` / `<ul>` / `<ol>` / `<blockquote>`，**一个 `<section>` 都不留**
* `<p>` 里**不再嵌 `<p>`**（浏览器会自动拆散嵌套 p）
* 图片独占一个段落：`<p><img …></p>`
* 图注是紧跟其后的独立段落（浅灰 12px 居中）

顺带修掉的两个隐蔽 bug：

| bug | 现象 | 修复 |
|---|---|---|
| `border: 0` 排在 `border-left` 之后 | 「第 1 步」标题的绿色左边框竖线消失 | border 的 longhand 统一排到简写之后 |
| `<img loading="lazy">` | 长文里视口外的案例 GIF 根本不发起请求 | 删除 `loading` / `decoding` 属性 |

### 公众号里的「复制」是长按

公众号没有 JS，文章里的绿色标签点不动。所以 `make-wechat.py` 会自动把复制语义改成「长按」：

| 位置 | 公众号版文案 |
|---|---|
| 提示词块 | 长按下方文字复制 |
| 官网网址 | 长按下方网址复制 |
| 引语回复 | 长按复制 |
| 安装指令（两行） | 长按上面两行，分两次复制 |

第一个提示词块前还会自动插入一条「复制小提示」条。`index.html`（Web 版）不受影响，按钮照常可点。

**如果换了图片**：jsDelivr 有 CDN 缓存，改完可能要等几分钟才刷新。急用可以清缓存：

```
https://cdn.jsdelivr.net/gh/newbaisays-aigc/wechat-knowledge-animation@master/assets/xxx.png
→ 访问 jsDelivr 的 purge 接口
```

或者把 `@master` 换成 commit SHA（版本固定，不会被后续提交影响）：

```bash
python make-wechat.py --base \
  https://cdn.jsdelivr.net/gh/newbaisays-aigc/wechat-knowledge-animation@<commit-sha>
```

### ⚠️ `@master` 会被缓存 12 小时

jsDelivr 对**分支名**（`@master`）会缓存「分支 → commit SHA」的映射，**最长 12 小时**。
purge 文件路径刷不掉这个映射（实测 purge 返回 200，但文件仍是旧版）。

所以线上取 `wechat.html` 请直接用 commit SHA：

```
https://cdn.jsdelivr.net/gh/newbaisays-aigc/wechat-knowledge-animation@<commit-sha>/wechat.html
```

最新修复版本（结构降级 + 灰底修复 + 格式保留 + 图片路径修复）：

```
https://cdn.jsdelivr.net/gh/newbaisays-aigc/wechat-knowledge-animation@7c84efe0c838c5192b6588dd17a12249864a8869/wechat.html
```

本地文件 `wechat.html` 不受缓存影响，跑一次 `make-wechat.py` 就是最新版。

### ⚠️ `--base` 是「仓库根 URL」，别带 `/assets`

脚本会自动在 `--base` 后面拼上源码里自带的 `assets/`。如果 `--base` 末尾又带了 `/assets`，
路径会变成 `assets/assets/xxx.png` —— **线上 21 张图全部 404，而且肉眼看源码完全发现不了**。

```bash
# ✓ 正确
python make-wechat.py --base \
  https://cdn.jsdelivr.net/gh/newbaisays-aigc/wechat-knowledge-animation@master

# ✗ 错误（现在脚本会自动纠正，但别指望）
python make-wechat.py --base \
  https://cdn.jsdelivr.net/gh/newbaisays-aigc/wechat-knowledge-animation@master/assets
```

现在 `make-wechat.py` 有三重保护：

| 保护 | 行为 |
|---|---|
| `--base` 末尾的 `/assets` | 自动去掉并打印提示 |
| 拼接后再扫一遍 | 出现 `assets/assets/` 立即纠正 |
| 生成后自检 | 路径无重复目录段 **且** 本地 `assets/` 下文件必须真实存在，否则退出码 1 |

`tools_verify.js` 也有对应断言（㉓ ㉔），共 **24 项**。

## 关于体积

微信单图超过 2MB 会提示失败。6 个 GIF 案例原本 8.5MB 起步（最大的 `d-infographic.gif` 有 3.1MB），已用 ffmpeg 压到 **480px / 8fps / 64 色**，全部进 2MB 以内，总量 8.5MB → 8.5MB 量级不变但单图全部达标：

```bash
ffmpeg -i in.gif -vf "fps=8,scale=480:-1:flags=lanczos,split[s0][s1];\
[s0]palettegen=max_colors=64:stats_mode=diff[p];[s1][p]paletteuse=dither=sierra2_4a" \
  -loop 0 out.gif
```

## 许可

文章文字、提示词和模板结构都可自由使用、商用，注明出处欢迎，不注明也没关系。

案例里出现的名画和历史图片来自维基共享资源这类可授权渠道，署名请保留。
