# 用 WorkBuddy 做知识动画 · 完整图文教程

> 一篇公众号文章 + 全部素材快照。把口播稿和风格参考图，变成一条能发出去的动画视频。

## 这份仓库是什么

| 文件 | 用途 |
|---|---|
| `index.html` | 文章原文（完整版，含脚本与复制按钮） |
| `wechat.html` | **公众号粘贴版** —— 样式全内联、图片走 CDN 绝对地址，可直接全选复制进公众号编辑器 |
| `make-wechat.py` | 从 `index.html` 生成 `wechat.html` 的转换器 |
| `assets/` | 21 张标注截图 + 6 个 GIF 案例 |
| `cover.html` | 封面备选 |

## 发布到公众号

```bash
# 1. 生成公众号粘贴版（图片指向 jsDelivr CDN）
python make-wechat.py \
  --base https://cdn.jsdelivr.net/gh/newbaisays-aigc/wechat-knowledge-animation@master

# 2. 浏览器打开 wechat.html → 全选复制 → 粘贴进公众号编辑器
```

图片走 `cdn.jsdelivr.net/gh/...` 而不是 `raw.githubusercontent.com`，因为后者在境内经常被卡断，微信抓图会失败。

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
