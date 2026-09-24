#!/usr/bin/env python3
"""Generate docs/HORIZON_V4_UI_SPEC.md from the layout and tokens.

The document is derived, not written by hand: every coordinate, opacity, line
width, binding and visibility rule in it comes from
assets/ui/horizon_v4_layout.json, so the spec cannot describe a screen the
generator does not draw.

Usage:
    python3 tools/preview/build_horizon_v4_spec.py
"""
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LAYOUT = os.path.join(REPO, "assets", "ui", "horizon_v4_layout.json")
TOKENS = os.path.join(REPO, "assets", "ui", "horizon_v4_tokens.json")
OUT = os.path.join(REPO, "docs", "HORIZON_V4_UI_SPEC.md")


def main():
    layout = json.load(open(LAYOUT))
    tokens = json.load(open(TOKENS))
    lines = [
        "# HORIZON V4 — SPATIAL GLASS COCKPIT", "",
        "状态：**等待人工视觉验收** "
        "（`HORIZON_V4_SPATIAL_GLASS = AWAITING HUMAN VISUAL APPROVAL`）。", "",
        "V3 被否决的原因：三个候选是同一套构图换装饰线，那条粗青色斜线没有语义。",
        "V4 不复用那套语言，改为四层空间结构。本文与",
        "`assets/ui/horizon_v4_layout.json`、`assets/ui/horizon_v4_tokens.json`",
        "由同一份数据生成，文档不可能与场景不一致。", "",
        "## 1. 四层空间结构", "",
        "```text",
        "LAYER 0  deep environment",
        "LAYER 1  spatial road / vehicle stage",
        "LAYER 2  information glass (navigation, speed limit, warning)",
        "LAYER 3  state feedback",
        "```", "",
        "| 层 | 元素数 | 元素 |", "|---|---|---|",
    ]
    for name, ids in layout["layers"].items():
        lines.append(f"| {name} | {len(ids)} | {', '.join('`%s`' % i for i in ids)} |")
    lines += ["", "## 2. 调色板（唯一来源）", "", "| 用途 | 值 |", "|---|---|"]
    for key, value in tokens["colors"].items():
        lines.append(f"| {key} | `{value}` |")
    lines += ["", "## 3. 字体层级", "", "| 层级 | 字号 | 字距 |", "|---|---|---|"]
    for name, spec in tokens["typography"]["tiers"].items():
        lines.append(f"| {name} | {spec['size']} | {spec['tracking']} |")
    lines += ["", "## 4. 元素表（全部 65 项由 layout 生成，此处为可读摘要）", "",
              "| id | 类型 | x | y | w | h | z | 层 | 可见性 |", "|---|---|---|---|---|---|---|---|---|"]
    for c in layout["components"]:
        b = c.get("bounds", {})
        vis = c.get("visibility") or {}
        visible = ("、".join(f"{k}={v}" for k, v in vis.items())) or "总是"
        lines.append(
            f"| `{c['id']}` | {c['kind']}/{c.get('shape', '')} | {b.get('x')} | "
            f"{b.get('y')} | {b.get('w')} | {b.get('h')} | {c.get('z')} | "
            f"{c.get('layer')} | {visible} |")
    lines += ["", "## 5. 状态反应", "", "| 层 | id | 绑定 | 触发 | 透明度 |",
              "|---|---|---|---|---|"]
    for c in layout["components"]:
        vis = c.get("visibility") or {}
        if not vis:
            continue
        lines.append(f"| {c.get('layer')} | `{c['id']}` | {vis.get('binding')} | "
                     f"{'、'.join(f'{k}={v}' for k, v in vis.items() if k != 'binding')} | "
                     f"{c.get('visible_opacity', c.get('opacity'))} |")
    lines += ["", "## 6. 动画令牌（本轮只声明）", "", "| 令牌 | 值 |", "|---|---|"]
    for key, value in tokens["animation"].items():
        if key != "why":
            lines.append(f"| {key} | {value} |")
    lines += ["", "## 7. T113 成本", "", "| 项 | 值 |", "|---|---|",
              "| 静态背景 | 3 层，可烘焙为 1 张 `assets/ui/horizon_v4_background.png` |",
              "| 玻璃材质 | 9-slice 位图，无运行时模糊 |",
              "| 常驻解码资产 | 5（背景位图 + 车辆底图 + 面板 delta 层）≈ 4.6 MB |",
              "| 每帧工作 | 文本 + 透明度 + 少量状态矢量；车辆是唯一每帧位图 |",
              "| 同时状态叠加 | ≤ 4 |", "| 同时动画序列 | ≤ 2 |", "",
              "## 8. 自动验收", "",
              "- 与 v2.1 同一套几何 QA（画布 / 梯形遮罩 / 区域 / 文本碰撞 /",
              "  速度 0–288 十档间距 / UNKNOWN / 无调试文本 / 装饰线不穿文字）",
              "- 导航隐藏 = 0 像素（探针渲染）",
              "- 与 V3 B 的像素差异（排除车辆位图）见 `horizon_v4_report.json`", "",
              "## 9. 证据", "",
              "`assets/checkpoints/horizon_v4/` 下：14 张状态图、`horizon_v4_contact_sheet.png`、",
              "`horizon_v4_key_states.png`、`horizon_v4_physical_scale.png`、",
              "`horizon_v3_vs_v4.png`、`horizon_v4_report.json`。", ""]
    with open(OUT, "w") as fh:
        fh.write("\n".join(lines))
    print(f"[v4-spec] {len(lines)} lines -> {os.path.relpath(OUT, REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
