# 示例：agent-science-mini

从一份真实中文综述（Agent 驱动的自主科学发现，2024-01 至 2026-10，核查日期 2026-10-01）中抽取的精简数据集：10 篇代表作、8 个团队、8 个时间轴事件、8 个开源仓库、7 个方向。全部为真实条目；论文元数据核对自 arXiv / Semantic Scholar / Crossref，GitHub 数据为 2026-10-01 快照。仅用于演示格式与渲染，不代表完整结论。

```bash
# 在仓库根目录
python scripts/build.py examples/agent-science-mini -o out/agent-science-mini.html
python scripts/screenshot.py out/agent-science-mini.html --outdir out/screens   # 可加 --chrome /usr/bin/google-chrome
python scripts/export_bibtex.py examples/agent-science-mini --out out/references
```

`meta.json` 中 `map.resolution: "50m"`（显示新加坡），`map.merge` 把台湾、香港、澳门几何并入 `CN`，与“范围与方法”中的计数口径一致。
