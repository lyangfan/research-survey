# 生成 HTML 与截图验证

## 1. 构建
```bash
pip install -r requirements.txt                    # 只有截图需要 playwright；构建与检索只用标准库
python scripts/build.py <data_dir> --check         # 先校验数据（缺字段、未知方向、日期格式、重复条目）
python scripts/build.py <data_dir> -o out/survey.html
```
- 输出是**单个自包含 HTML**：ECharts（`scripts/vendor/echarts.min.js`，Apache-2.0）、世界地图 GeoJSON、全部数据都内联，离线可打开、可直接发邮件/放网盘。
- 世界地图默认在构建时从 Natural Earth（公有领域）下载并缓存到 `scripts/.cache/`，规范化为 ISO alpha-2 名称；`map.resolution: "50m"` 可显示新加坡等小国（文件约 +1.2 MB）。离线环境用 `--world 本地.geojson` 或 `--no-download`（需已有缓存）。
- 正式出版/在中国大陆公开发布时，请改用经审核的标准地图（`--world`），不要直接使用 Natural Earth 的边界。

## 2. 页面结构（template.html）
| 板块 | 交互 |
|---|---|
| 顶部统计卡 | 自动计数（工作/同行评审/团队/仓库/国家）|
| 吸顶目录（sticky TOC） | 根据存在的板块自动生成与编号，滚动高亮 |
| 执行摘要 / 范围与方法 | `narrative/*.html` 原样插入 |
| 发展路径 | 阶段卡片 + 类别标签筛选时间轴；事件点开显示描述和来源；按半年/年/季度 × 主方向的堆叠柱状图 |
| 方向分类体系 | ECharts 树图（点击方向 → 跳到代表作表并筛选）+ 方向卡片 |
| 代表性工作 | 方向标签、状态、年份筛选，关键词搜索，表头排序，同行评审/预印本徽标 |
| 团队与进展 | 地区/类型筛选，进展等级条 |
| 地区热力图 | 团队数/代表作数切换，点击国家在右侧面板列出团队、方向分布、代表作；各国柱状图（可点击）+ 主要国家方向雷达图 |
| 开源项目 | Stars 对数条形图（按活跃度着色）、“距最近提交天数 vs Stars”散点、活跃度环图；分类筛选与可展开详情的表格 |
| 挑战与趋势 / 注意事项 | `narrative/*.html` |
| 参考文献 | 自动汇总 works + timeline + extra_refs + repos 的去重链接 |

改样式：直接编辑 `scripts/template.html` 的 CSS；方向颜色来自 `meta.directions[].color`。所有用户数据在前端经过 HTML 转义，链接只允许 http(s)/mailto。

## 3. 截图验证（必须做）
```bash
python -m playwright install chromium          # 或用系统 Chrome：--chrome /usr/bin/google-chrome
python scripts/screenshot.py out/survey.html --outdir out/screens
```
脚本会：等待页面就绪 → 检查 console error / page error → 检查横向溢出 → 检查每个图表都有非空 canvas → 输出各表格行数和目录 → 截取首屏和每个板块（含点击地图后的面板）。退出码非 0 表示有问题。

**逐张查看截图**，重点确认：
- 中文正常显示（没有方块/豆腐字）。Linux 无中文字体时安装 `fonts-noto-cjk`。
- 地图有颜色、右侧面板有内容；柱状图/树图/雷达图/散点图都渲染出来。
- 表格行数与数据一致；长文本没有撑破布局；窄屏（`--width 390`）下可阅读。
