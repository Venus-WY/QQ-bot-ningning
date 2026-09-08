# QQ 群「AI 群友」机器人（MVP）

一个「像群友一样参与聊天」的 QQ 机器人，而不是每条消息都回复的烦人机器人。

- **被 @ / 被回复** → 100% 回复
- **普通群聊** → 用便宜的大模型判断「该不该插话」，再按相关性概率决定是否开口
- **人格可配置** → 改 `config.yaml` 即可换人设、语气、话痨程度
- **功能插件** → 骰子 / 今日运势 / 今日老婆 / 长期记忆（触发词见「四、测试效果」）

架构：

```
QQ群 → NapCatQQ →(反向 WebSocket)→ NoneBot2 → 插件逻辑 → DeepSeek
```

---

## 一、前置要求

- Windows / Linux / macOS，Python **3.9+**（推荐 3.11 或 3.12；3.14 装依赖若报错见「常见问题」）
- 一个 **QQ 小号**（不要用大号，避免风控）
- 一个 **DeepSeek API key**（[platform.deepseek.com](https://platform.deepseek.com) 申请，很便宜）

---

## 二、快速开始（Python 侧）

```bash
# 1. 进入项目目录
cd qq-bot

# 2. 建虚拟环境并激活（Windows）
python -m venv .venv
.venv\Scripts\activate

# 3. 装依赖
pip install -r requirements.txt

# 4. 配置
#    把 .env 里的 DEEPSEEK_API_KEY 填上
#    把 config.yaml 里的 groups 改成你的测试群号
```

`.env` 关键项：

```
DEEPSEEK_API_KEY=sk-xxxx        # 必填
DEEPSEEK_MODEL=deepseek-chat    # 默认即可
```

`config.yaml` 关键项：

```yaml
groups:
  - 123456789        # ← 改成你的群号
```

启动：

```bash
python bot.py
```

看到类似日志说明启动成功：

```
[INFO] nonebot | OneBot V11 适配器已注册
[INFO] nonebot | Running NoneBot...
[INFO] uvicorn | Uvicorn running on http://127.0.0.1:8080
```

---

## 三、装 NapCatQQ 并连上（QQ 侧）

NapCatQQ 负责把你的 QQ 小号接到 OneBot 协议。

### 1. 下载 NapCatQQ

- 推荐 **NapCat.Shell**（Windows 一键包，自带 QQNT，不用自己折腾环境）
- 下载地址：https://github.com/NapNeko/NapCatQQ/releases

### 2. 登录小号

运行 NapCat.Shell → 登录 → 用手机 QQ 扫码登录你的**小号**。

### 3. 配置反向 WebSocket

登录成功后打开 NapCat 的 Web 控制台，默认地址：

```
http://127.0.0.1:6099/webui
```

在「网络配置 / Network」里**新增一条「反向 WebSocket」**，地址填：

```
ws://127.0.0.1:8080/onebot/v11/ws
```

保存后重启 NapCat（或重新连接）。

> 不同版本界面文案略有差异（可能是「WebSocket 反向」「reverse websocket」等），位置和含义一致。

### 4. 验证连接

连上后，回到 `python bot.py` 的终端，会多出类似日志：

```
[INFO] nonebot | Bot xxxxxxx@onebot 已连接
```

同时 QQ 群里发一句 `/echo 你好`，机器人会复读「你好」，说明整条链路通了。

> `/echo` 是 NoneBot 自带的调试插件，测试完可在 `pyproject.toml` 里删掉 `builtin_plugins = ["echo"]`。

---

## 四、测试效果

1. **@机器人** 说句话 → 必回。
2. **普通闲聊** → 观察终端日志里的 `插话决策 speak=True/False relevance=0.22`，偶尔会主动插一句。
3. 30 秒冷却期内不会主动刷屏（@可绕过）。

### 内置功能插件

| 功能 | 触发方式 | 效果 |
| --- | --- | --- |
| 骰子 | `r1d6`、`r2d8+1`、`r4d6kh3` | 掷骰子并回结果 |
| 今日运势 | `/运势` 或消息含「今日运势」 | 当天固定运势 + 一张角色图 + 宁宁点评 |
| 今日老婆 | `/老婆` 或消息含「今日老婆」「来点美图」 | 随机角色图 + 角色名 + 宁宁点评 |

> 图库在项目根目录的 `素材/`，图片名即角色名；往里塞新图，下一次触发就直接能用（无需重启）。

### 热重载

开发期用 `run_reload.py` 跑，改 `src/`、`corpus/`、`config.yaml`、`.env`、`bot.py` 会自动重启，无需手动。双击 `启动.bat` 即可（项目根目录的 `一键启动.bat` 会连 NapCat 一起拉起）。

---

## 五、调人格

打开 `config.yaml`，改 `persona` 即可，字段含义见文件内注释。

| 想达到的效果 | 改哪里 |
| --- | --- |
| 更话痨 | `behavior.min_reply_interval` 调小 |
| 更安静 | 调大 `min_reply_interval` |
| 换名字/人设 | `persona.identity.name` / `role` / `style` |
| 回复更长/更短 | `persona.speech.max_length` |

---

## 六、常见问题

**Q：`pip install` 报错，尤其 Python 3.14**
A：个别库还没完全适配 3.14。删掉 `.venv` 用 Python 3.11/3.12 重建即可：
`py -3.12 -m venv .venv`（需先装 3.12）。

**Q：NapCat 连不上，bot 日志没有「已连接」**
A：确认 bot 已启动且监听 8080；确认 NapCat 填的是 `ws://127.0.0.1:8080/onebot/v11/ws`（`/onebot/v11/ws` 路径不能漏）。

**Q：@机器人没反应**
A：① `config.yaml` 的 `groups` 是否含该群号；② `.env` 的 `DEEPSEEK_API_KEY` 是否填对；③ 看终端有没有 `调用大模型失败` 的报错。

**Q：机器人从不主动说话**
A：`should_speak` 里相关性低就会沉默，这是预期行为。可以临时在群里聊它熟悉的话题，或调低概率门阈值。

---

## 七、重要提醒

- NapCat/OneBot 属于**第三方 QQ 自动化接入**，不是腾讯官方机器人接口；QQ 客户端升级可能暂时失效，需等 NapCat 适配。
- 有**账号风控**风险，务必用专门的小号 + 测试群，不要用大号。
- 群成员知情与隐私：机器人会读到群消息，建议只在朋友/测试群使用，并告知成员。

---

## 八、已实现与可继续做

**已实现**（详见 `工作总结.md`）：SQLite 长期记忆、绫地宁宁人格蒸馏、主动冒泡、骰子/运势/老婆插件、热重载。

**可继续做**：
- 更细的社交限流（如 5 分钟发言次数上限）
- 连续对话窗口（120 秒内对方继续说话无需 @）
- 按情绪挑图（用 `素材/metadata.yaml` 里的 mood/tags）
- 更多功能插件：照 `src/plugins/fortune/` 或 `waifu/` 抄即可，见 `docs/插件开发指南.md`
