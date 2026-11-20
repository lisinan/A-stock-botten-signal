# A股见底信号仪表盘 · A-stock Bottom Signal Dashboard

> 用 [Tushare Pro](https://tushare.pro) 公开数据，把「A股到底有没有见底」做成一套**可量化、可复现、可视化**的信号仪表盘。

用一条命令抓取数据 → 计算 8 项底部信号 → 生成一个自包含的 HTML 看板（暗色主题、ECharts 图表、手机可看）。

![signals](https://img.shields.io/badge/信号-8维度-blue) ![python](https://img.shields.io/badge/python-3.8%2B-green) ![license](https://img.shields.io/badge/data-Tushare-orange)

---

## ✨ 功能

- **8 项底部信号打分卡**：估值 / 价格 / 量能 / 市场宽度 / 杠杆
- **趋势图表**（ECharts）：
  - 沪深300 收盘价 + 年线 MA250
  - 估值走势（PE_TTM / PB 双轴）
  - 市场宽度：**破净股占比**走势（带 8% / 10% 阈值线）
  - 成交额 20 日均（地量判断）
  - 融资余额（杠杆出清）
  - 流动性补充：**Shibor 短端利率**、**M1-M2 剪刀差**、**社融增量**
- **数据驱动的「最终结论」**：自动汇总命中信号，给出「底部区域 / 待确认 / 未见底」判断与行动框架
- **一键自启动**：`run.sh` 支持开机刷新数据并弹出浏览器

## 🧭 检查的 8 项信号

| 维度 | 信号 | 「见底」含义 | 经验阈值 |
|---|---|---|---|
| 估值 | 沪深300 PE_TTM / PB 历史分位 | 越便宜越接近底 | 分位 < 20% |
| 价格 | 距 5 年高点回撤 | 深度调整 | ≤ -30% |
| 价格 | 相对年线 MA250 | 右侧确认（站上年线） | — |
| 量能 | 成交额 20 日均历史分位 | 缩量=地量出清 | 分位 < 20% |
| 宽度 | **破净股占比** | 整体跌破净资产 | > 8~10% |
| 杠杆 | 融资余额较高点回落 | 杠杆出清 | ≤ -15% |

> 核心思路：**左侧信号（估值/破净/杠杆）先到，右侧信号（站上年线/量能）后到确认。只有右侧出现才算真正确认见底。**

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 Tushare Token

到 [tushare.pro/register](https://tushare.pro/register) 注册并获取 token：

```bash
export TUSHARE_TOKEN="你的token"
```

（也可以一次性写入 `~/tk.csv`：`python -c "import tushare as ts; ts.set_token('你的token')"`）

### 3. 生成看板

```bash
python build_dashboard.py
```

运行后会生成：
- `index.html` —— 可直接用浏览器打开的自包含看板
- `data.json` —— 图表与信号的原始数据

## ⏰ 开机自动刷新（可选）

`run.sh` 会：加锁防重 → 等网络 → 刷新数据(重试) → 通知 → 用 Chrome 打开。

```bash
export PYTHON=python3        # 指定解释器
export CHROME=google-chrome-stable
./run.sh
```

**Hyprland 自启动**（Omarchy 等）：在 `~/.config/hypr/autostart.lua` 加一行

```lua
o.exec_on_start("bash /path/to/A-stock-botten-signal/run.sh")
```

其他方式：`cron`、systemd user timer 均可直接调用 `run.sh`。

## 📁 项目结构

```
.
├── build_dashboard.py   # 抓数 + 计算信号 + 生成 HTML 看板
├── run.sh               # 一键刷新 + 打开浏览器（可开机自启）
├── requirements.txt
├── index.html           # 生成的看板（快照）
├── data.json            # 生成的数据（快照）
└── README.md
```

## ⚠️ 免责声明

本项目仅用于**研究与学习**：
- 所有数据来自 Tushare Pro 公开接口；
- 信号阈值（分位 < 20%、破净 > 8%、回撤 < -30% 等）为**经验参考值，非普适规律**；
- **不构成任何投资建议**，据此操作风险自负。

## 📄 License

仅限学习研究使用；请遵守 [Tushare 使用条款](https://tushare.pro/document/1?doc_id=290)。
