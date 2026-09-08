# QQ 群「AI 群友」—— 绫地宁宁

一个**像群友一样参与聊天**的 QQ 机器人，而不是每条消息都回复的烦人机器人。人格是《魔女的夜宴》里的**绫地宁宁**，会主动插话、记得群友、有长期记忆和好感度，还会掷骰子、算运势、发美图。

## 特性

- **被 @ / 被回复** → 必回
- **普通群聊** → 用便宜的大模型判断「该不该插话」，再按相关性概率决定是否开口（30 秒冷却，不刷屏）
- **长期记忆** → 记住每个群友说过的事，关系/好感度逐步变化
- **人格可配置** → 改 `config.yaml` 即可换人设、语气、话痨程度
- **功能插件** → 骰子 / 今日运势 / 今日老婆（触发词见下文）
- **热重载** → 开发期改代码自动重启，改完即生效

## 架构

```
QQ群 → NapCatQQ →(反向 WebSocket)→ NoneBot2 → 插件逻辑 → DeepSeek
```

- [NapCatQQ](https://github.com/NapNeko/NapCatQQ)：把 QQ 小号接到 OneBot v11 协议
- [NoneBot2](https://github.com/nonebot/nonebot2)：Python 机器人框架
- [DeepSeek](https://platform.deepseek.com)：OpenAI 兼容 API，便宜好用

## 目录结构

```
.
├── qq-bot/               # Python 项目（NoneBot2），核心代码在这
│   ├── bot.py            # 启动入口
│   ├── run_reload.py     # 热重载启动（开发用）
│   ├── config.yaml       # 配置：群号 / 人格 / 记忆
│   ├── .env.example      # 环境变量模板（复制成 .env 填 key）
│   └── src/plugins/      # 插件：qqbot / fortune / waifu / dice
├── corpus/               # 人格蒸馏产物（persona/fewshot/eval）
├── 素材/                 # 图片池（角色图，文件名即角色名）
├── scripts/              # 数据分析小工具（与本机数据打分相关，可忽略）
└── 一键启动.bat           # 一键拉起 NapCat + bot（Windows）
```

## 快速开始

### 0. 前置要求

- Windows / Linux / macOS，Python **3.9+**（推荐 3.11 / 3.12）
- 一个 **QQ 小号**（务必用专门小号，不要用大号，有风控风险）
- 一个 **DeepSeek API key**（[platform.deepseek.com](https://platform.deepseek.com) 申请，很便宜）

### 1. 克隆仓库

```bash
git clone https://github.com/你的用户名/QQ-bot-ningning-.git
cd QQ-bot-ningning-/qq-bot
```

### 2. 安装依赖

```bash
# 建虚拟环境并激活（Windows）
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
# python -m venv .venv && source .venv/bin/activate

# 装依赖
pip install -r requirements.txt
```

### 3. 配置

复制模板并填上你的 key：

```bash
# Windows
copy .env.example .env
# Linux / macOS
# cp .env.example .env
```

打开 `.env`，填入：

```
DEEPSEEK_API_KEY=sk-你的真实key
```

打开 `config.yaml`，把群号改成你的测试群号：

```yaml
groups:
  - 123456789        # ← 改成你自己的群号
```

> `config.yaml` 里所有字段都有中文注释，人格、记忆、话痨程度都能在这里调。

### 4. 启动 bot

```bash
python bot.py
```

看到类似日志说明启动成功：

```
[INFO] nonebot | OneBot V11 适配器已注册
[INFO] uvicorn | Uvicorn running on http://127.0.0.1:8080
```

### 5. 装 NapCatQQ 并连上（QQ 侧）

NapCatQQ 负责把你的 QQ 小号接到 OneBot 协议。

1. **下载**：https://github.com/NapNeko/NapCatQQ/releases ，推荐 **NapCat.Shell**（Windows 一键包，自带 QQNT）。
2. **登录小号**：运行 NapCat.Shell → 用手机 QQ 扫码登录你的小号。
3. **配置反向 WebSocket**：登录后打开 Web 控制台（默认 http://127.0.0.1:6099/webui ），在「网络配置 / Network」里新增一条**反向 WebSocket**，地址填：

   ```
   ws://127.0.0.1:8080/onebot/v11/ws
   ```

   保存后重启 NapCat（或重新连接）。

   > 不同版本界面文案略有差异（「WebSocket 反向」「reverse websocket」等），含义一致。

4. **验证连接**：回到 `python bot.py` 的终端，会多出类似日志：

   ```
   [INFO] nonebot | Bot xxxxxxx@onebot 已连接
   ```

   同时在 QQ 群里发一句 `/echo 你好`，机器人会复读「你好」，说明整条链路通了。

   > `/echo` 是 NoneBot 自带的调试插件，测试完可在 `pyproject.toml` 里删掉 `builtin_plugins = ["echo"]`。

## 功能插件

| 功能 | 触发方式 | 效果 |
| --- | --- | --- |
| 骰子 | `r1d6`、`r2d8+1`、`r4d6kh3` | 掷骰子并回结果 |
| 今日运势 | `/运势` 或消息含「今日运势」 | 当天固定运势 + 一张角色图 + 宁宁点评 |
| 今日老婆 | `/老婆` 或消息含「今日老婆」「来点美图」 | 随机角色图 + 角色名 + 宁宁点评 |

> 图库在项目根目录的 `素材/`，**图片名即角色名**；往里塞新图，下一次触发就直接能用，无需重启。

## 调人格

打开 `qq-bot/config.yaml`，改 `persona` 即可，字段含义见文件内注释。

| 想达到的效果 | 改哪里 |
| --- | --- |
| 更话痨 | `behavior.min_reply_interval` 调小 |
| 更安静 | 调大 `min_reply_interval` |
| 换名字/人设 | `persona.identity.name` / `role` / `style` |
| 回复更长/更短 | `persona.speech.max_length` |

## 常见问题

**Q：`pip install` 报错，尤其 Python 3.14**
A：个别库还没完全适配 3.14。删掉 `.venv` 用 Python 3.11/3.12 重建：`py -3.12 -m venv .venv`。

**Q：NapCat 连不上，bot 日志没有「已连接」**
A：确认 bot 已启动且监听 8080；确认 NapCat 填的是 `ws://127.0.0.1:8080/onebot/v11/ws`（`/onebot/v11/ws` 路径不能漏）。

**Q：@机器人没反应**
A：① `config.yaml` 的 `groups` 是否含该群号；② `.env` 的 key 是否填对；③ 看终端有没有 `调用大模型失败` 的报错。

**Q：机器人从不主动说话**
A：`should_speak` 里相关性低就会沉默，这是预期行为。可以临时在群里聊它熟悉的话题，或调低概率门阈值。

## 免责声明

- NapCat/OneBot 属于**第三方 QQ 自动化接入**，不是腾讯官方机器人接口；QQ 客户端升级可能暂时失效，需等 NapCat 适配。
- 有**账号风控**风险，务必用专门的小号 + 测试群，不要用大号。
- 群成员知情与隐私：机器人会读到群消息，建议只在朋友/测试群使用，并告知成员。

## 许可证

（按需补充，例如 MIT。此处暂未指定，如需公开使用请先确认游戏素材与图片的版权。）
