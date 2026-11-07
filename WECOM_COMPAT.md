# 公众号兼容性修复 · 验收基线

> 生成时间：2026-11-07 15:37（commit `857e807`）
> 验证工具：`tools_sandbox_verify.js`（模拟公众号编辑器的清洗规则 → 渲染 → 量化）、`tools_verify.js`（24 项独立断言）

## 公众号编辑器的限制（依据）

来源：md2wechat 官方 HTML 规范 + feishu2wx 社区保守基线 + 微信公众号编辑器源码模式实测

| 类别 | 内容 |
|---|---|
| **稳定依赖标签** | `p` `span` `strong` `em` `ul` `ol` `li` `a` `img` `section` `blockquote` `h1`-`h6` `table` 系列 `hr` `sup` `sub` `u` `pre` `code` `br` |
| **会降级（样式跟着丢）** | `div` `figure` `figcaption` 及复杂布局标签 |
| **不支持** | `script` `style` `iframe` `video` |
| **会被清除** | `class` `id` `data-*` 属性 |
| **样式子集** | 只认 `background-color`（**不认 `background` 简写**）、`color`、`font-*`、`line-height`、`text-align`、`margin*`、`padding*`、`border*`、`border-radius`、`display`（**不支持 flex/grid**）、`width`/`max-width`、`height`、`vertical-align`、`opacity` 等 |
| **不支持的样式** | `background-image`（渐变）、`box-shadow`、`position:absolute`（会错位）、`transform` |

## 修复前基线（_stage1.html = 仅完成 div→section 转换）

### 剪贴板层

| 指标 | 修复前 | 目标 |
|---|---|---|
| `div` | 0（已转） | 0 |
| `section` | 56 | 56 |
| `figure` / `figcaption` | 0 / 0 | 0 / 0 |
| `background` 简写 | **62** | **0** |
| `display:flex` | **11** | **0** |
| `background-image`（渐变） | **8** | **0** |
| `box-shadow` | 2 | 0 |
| `position:absolute` | 7 | 0 |
| 灰底 `rgb(243,245,242)` | 0 | 0 |
| 图片 / CDN 地址 | 21 / 21 | 21 / 21 |

### 沙盒渲染层（= 公众号实际效果）

| 指标 | 修复前 | 修复后 | 说明 |
|---|---|---|---|
| 段落数 | 65 | 65 | 不变 |
| **有底色 section** | **0** | **22** | ⬅ 核心指标：卡片/提示框全无底色 |
| section 数 | 56 | 56 | 不变 |
| 图片数 | 21 | 21 | 不变 |
| **列表样式** | none | none | ⬅ **保持 `none`**：圆点是自己画的，改成 `disc` 会出现双圆点 |
| **徽章数（inline-block）** | **0** | **4** | ⬅ 步骤编号圆点恢复 |
| 页面错误 | 无 | 无 | — |

### 剪贴板层 · 修复后实测（线上 SHA 版本）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| `div` | 40 | **0**（正文内） |
| `figure` / `figcaption` | 19 / 14 | **0 / 0** |
| `background` 简写 | 62 | **0** |
| `display:flex` | 11 | **0** |
| `background-image`（渐变） | 8 | **0** |
| `box-shadow` | 2 | **0** |
| `position:absolute` | 7 | **0** |
| 灰底 `rgb(243,245,242)` | 30 个段落 | **0** |
| 步骤编号徽章 | 0 | **4** |
| 绿圆点 `span` | 0 | **25** |

> 注：线上整页仍能看到 1 个 `div`、1 个 `display:flex`、4 个 `background:`、2 个 `box-shadow` ——
> 全部位于 `<article>` **之外**的顶部工具条与其内联 `<script>` 里，复制时不会进入公众号正文。

## 复现的塌陷现象（与用户截图一致）

沙盒渲染出的流程导航区：

```
第 1 步基础安装下载安装并登录 | 第 2 步安装 Skill贴地址，让它帮你装 | 第 3 步上手试用先问答，再交素材
```

三张卡片被 flex 降级拍平成一行连续文字 —— 与用户提供的截图完全一致。

## 修复方案

| 问题 | 处理 | 负责 |
|---|---|---|
| `div` 被降级 → 样式全丢 | `div` → `section` | `wecom_div_to_section.py` |
| `figure` / `figcaption` 被降级 | `figure` → `section`，`figcaption` → `p`（图注独立成段） | `wecom_div_to_section.py` |
| `display:flex` 无效 | 容器降为 `block`，`gap` 转 `margin`（行内→右外边距，列/换行→下外边距） | `wecom_style_fallback.py` |
| `background` 简写丢失 | 完整拆解为 `background-color` / `background-image` / `background-repeat` | `wecom_style_fallback.py` |
| `linear-gradient` 丢失 | 实色化；`.hl` 用 `border-bottom` 补底线 | `wecom_style_fallback.py` |
| `box-shadow` 丢失 | `.pick` 改 `border-bottom` | `wecom_style_fallback.py` |
| `position:absolute` 错位 | 按特征组合分流（见下表） | `wecom_style_fallback.py` |
| 列表缩进 / 双圆点 | `list-style` 保留 `none`，左内边距归 0，`padding` 压成一条 | `wecom_style_fallback.py` + `make-wechat.py` |
| 灰底色块 | `article`/`body` 保持 `#ffffff`（上一轮已修） | `make-wechat.py` |

### 绝对定位分流规则

一刀切删掉 `position:absolute` 会连步骤编号一起弄丢。改成按**尺寸 + 是否有文字**判断用途，不依赖 class 名：

| 特征 | 判定 | 处理 |
|---|---|---|
| 20~30px 见方 + 有文字 | 步骤编号徽章 | 保留圆形外观（宽高/圆角/底色/字色/行高），改 `inline-block` + `margin-right:8px` |
| ≤10px 见方 + 无文字 | 列表绿圆点 | 保留 `#4da783` 圆点，改 `inline-block` + 右侧留白 11px |
| 其余 | — | 退化为普通行内元素 |

几何还原：父级 `padding-left` 让位给原本的绝对定位坐标，子元素用于抵消 padding 的负 `margin-left` 同步补偿 —— 文字既不重叠也不跑位。父级不再有绝对定位子元素时，其 `position:relative` 一并清理。

### 列表收尾

| 项 | 处理 | 原因 |
|---|---|---|
| `list-style` | **保留 `none`** | 圆点是自己画的，改成 `disc` 会出现双圆点 |
| 列表左内边距 | 归 0 | 原生缩进会多出一截空白 |
| 列表项 `padding` | 压成一条声明 | 避免 `padding` 与 `padding-left` 同时存在 |
| `position:relative` | 清理 | 已无绝对定位子元素，不需要定位上下文 |

## 集成顺序（关键）

```
inline_styles → rewrite → adapt_for_wechat → inject_toolbar → apply_wecom_compat
```

`apply_wecom_compat` **必须最后执行**：工具条与「复制小提示」条是运行时插入的 `div`，提前转换会漏掉。
工具条本身要保持 `display:flex`（按钮横排），所以在降级前先 `extract()` 出来，处理完再插回。
