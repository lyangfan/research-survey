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
| 顶部标签 | `meta.kicker`；缺省时为 `RESEARCH SURVEY`，仅当 `meta.time_range`（用户指定）存在时追加时间段 |
| 顶部统计卡 | 自动计数（工作/同行评审/团队/仓库/国家）|
| 吸顶目录（sticky TOC） | 根据存在的板块自动生成与编号，滚动高亮 |
| 执行摘要 / 范围与方法 | `narrative/*.html` 原样插入（范围与方法需写明用户指定的时间范围或“未设时间限制”）|
| 发展路径 | 阶段卡片 + 类别标签筛选时间轴；事件点开显示描述和来源；按半年/年/季度 × 主方向的堆叠柱状图（横轴取 `meta.time_range`；未设时按数据中最早到最晚年份；未写 `meta.period` 时按跨度自动选粒度）|
| 方向分类体系 | ECharts 树图（点击方向 → 跳到代表作表并筛选；边距按标签实测宽度计算，窄屏时叶子标签以 … 截断、方向名换行，完整名在悬停提示里）+ 方向卡片（无代码方向带“无代码仓库”说明）；每个方向的叶子：主方向里程碑（★）全部显示 → 本方向其他工作按 `meta.tree_sort` 补位 → 交叉标注的工作只填剩余空位（虚线灰色）→ “+N 篇 → 代表作表”（点击筛选）。方向名换行时括号/标点不会单独落到下一行；图高按叶子数和换行后的方向名行数计算，窗口宽度 <520px 时隐藏根节点标签（悬停可见）给方向名让位；只在宽度变化时重新布局（整页截图不会把节点截在动画中途） |
| 代表性工作 | 方向标签、状态（含“★ 仅里程碑”）、年份筛选，关键词搜索，表头排序，同行评审/预印本徽标（长文本换行时为圆角矩形），已发表工作附“[预印本]”链接。日期列宽按字体的数字宽度（`ch`）计算，必要时在连字符处换行，不会压到标题；容器宽度 ≤760px 时每条工作变为卡片（日期+状态在上，标题、方向、机构、贡献依次排列）|
| 团队与进展 | 地区/类型筛选，进展等级条 |
| 地区热力图 | 团队数/代表作数切换，点击国家在右侧面板列出团队、方向分布、代表作；各国柱状图（可点击）+ 主要国家方向雷达图 |
| 数据门户与资源 | `portals.json`：类型筛选、机构、覆盖范围、访问方式、链接状态（✓/?/✗ + 检查日期，来自 `check_urls.py`）|
| 开源项目 | 各方向开源情况卡片（仓库带 `dirs` 时显示每个方向的仓库数、点击筛选；`repo_expected: false` 的方向显示说明和非代码资源）；Stars 对数条形图（按活跃度着色；长仓库名中间省略、完整名在悬停提示里，标签区自动适应宽度）、“距最近提交天数 vs Stars”散点、活跃度环图；分类筛选与可展开详情的表格（`stable: true` 显示“成熟稳定”）|
| 挑战与趋势 / 注意事项 | `narrative/*.html` |
| 参考文献 | 自动汇总 works + timeline + extra_refs + repos 的去重链接 |

改样式：直接编辑 `scripts/template.html` 的 CSS；方向颜色来自 `meta.directions[].color`。所有用户数据在前端经过 HTML 转义，链接只允许 http(s)/mailto。

## 3. 链接检查
```bash
python scripts/check_urls.py <data_dir> --only portals --write   # 门户链接状态写回 portals.json，页面显示
python scripts/check_urls.py <data_dir> --out url_report.tsv     # 检查全部链接（works/门户/时间轴/团队/extra_refs/仓库）
```
HEAD（失败或被拒再 GET）、默认 12 秒超时、跟随跳转；`dead`（404/410/DNS 失败/超时等）让退出码为 1，`blocked`（401/403/429，常见于出版社反爬）需人工打开确认。出版商的 cookie 重定向循环（如 Genome Research 的 implicit-login）会带 cookie 重试：成功记为 ok（“ok only with cookies”），仍循环记为 blocked（浏览器能打开），不会误报 dead。失效链接写进“注意事项”。

## 4. 截图验证（必须做）
```bash
python -m playwright install chromium          # 可选：脚本找不到浏览器时会自动执行这一步（--no-install 关闭）
python scripts/screenshot.py out/survey.html --outdir out/screens
```
浏览器查找顺序：Playwright 自带 Chromium → Playwright 缓存目录（`$PLAYWRIGHT_BROWSERS_PATH`、`~/.cache/ms-playwright` 等）里其他版本的 Chromium / headless shell（Playwright 升级后版本号对不上时常见）→ 系统 Chrome/Chromium（或 `--chrome PATH`）→ 自动 `python -m playwright install chromium` 后再试。

脚本会：等待页面就绪 → 检查 console error / page error → 检查横向溢出 → 检查每个图表都有非空 canvas → 输出各表格行数和目录 → 截取首屏和**所有可见板块**（摘要、范围、时间轴、树图、代表作、团队、地图、门户、仓库、趋势、注意事项、参考文献，含点击地图后的面板）；高度超过视口 1.3 倍的板块另按视口切片（`NN_<id>_p1.png`…，`--max-slices` 控制数量），避免整页长图缩小后看不清。带内部滚动条的表格（代表作表）另在容器内滚动截取 `NN_works_table_s2.png`、`_s3`…（`--table-slices`，默认 3），不再只看到第一屏的行。退出码非 0 表示有问题。

**逐张查看截图**，重点确认：
- 中文正常显示（没有方块/豆腐字）。Linux 无中文字体时安装 `fonts-noto-cjk`。
- 地图有颜色、右侧面板有内容；柱状图/树图/雷达图/散点图都渲染出来。
- 代表作表日期与标题之间有空隙、不重叠（桌面宽度和 `--width 800` 各看一次；窄屏为卡片布局）。
- 表格行数与数据一致；长文本没有撑破布局；状态标签、Stars 图的仓库名没有被截掉；树图每个方向的里程碑（★）在自己的方向下，交叉标注叶子为虚线灰色，“+N 篇”叶子可点击；窄屏（`--width 390`）下可阅读。
