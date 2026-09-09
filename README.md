# QQ 群「AI 群友」—— 韩萧（黑星）

一个**像群友一样参与聊天**的 QQ 机器人，而不是每条消息都回复的烦人机器人。人格是《超神机械师》里的主角**韩萧**——冷静理性、毒舌吐槽、精于算计的机械师。

它不只是会聊天：**记得群友和长期记忆**、**懂原著世界观**（内置《超神机械师》核心设定知识库）、**能察觉话题转移**、会主动插话不刷屏，还带一个**抽奖插件「黑幽灵的机械箱子」**。

## 特性

- **被 @ / 被回复** → 必回
- **普通群聊** → 用便宜的大模型判断「该不该插话」，再按相关性决定是否开口（30 秒冷却，不刷屏）
- **话题转移意识** → 能察觉群里话题已经切换，不纠缠已结束的话题（上下文带话题分界标记）
- **长期记忆** → 记住每个群友说过的事，关系/好感度逐步变化
- **人格可配置** → 改 `config.yaml` 即可换人设、语气、话痨程度
- **原著背景 + 人物关系** → 问起韩萧的来历会回应；群聊提到海拉、异神等原著人物时，韩萧有对应情绪反应
- **世界观知识库** → 内置《超神机械师》核心设定知识库（地点与势力/人物/装备/事件/技能/知识，各带详细设定描述），群聊提到相关概念时自动带入，让韩萧"认识"他的世界
- **功能插件** → 骰子 / 黑幽灵的机械箱子（抽奖，纯随机无保底）
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
│   ├── config.example.yaml  # 配置模板（群号 / 人格 / 记忆），复制成 config.yaml 填值
│   ├── .env.example      # 环境变量模板（复制成 .env 填 key）
│   ├── src/plugins/      # 插件：qqbot（核心对话）/ mechbox（开箱抽奖）/ dice（骰子）
│   ├── scripts/          # 人格蒸馏 + 知识库提取/清洗流水线
│   └── docs/             # 插件开发指南、知识库与人格扩展指南
├── corpus/               # 只读数据层
│   ├── persona/          # 韩萧人格蒸馏产物（personality/speech/behavior/social/qq_adaptation）
│   ├── fewshot.jsonl     # few-shot 范例库
│   └── knowledge.yaml    # 世界观知识库（分类 -> {名词: 描述}）
├── 素材/                 # 图片池（角色图，文件名即角色名）
├── scripts/              # 数据分析小工具（与本机数据打分相关，可忽略）
├── 一键启动.bat           # 一键拉起 NapCat + bot（Windows，自动查找 NapCat 目录）
└── README.md
```

## 快速开始

### 0. 前置要求

- Windows / Linux / macOS，Python **3.9+**（推荐 3.11 / 3.12）
- 一个 **QQ 小号**（务必用专门小号，不要用大号，有风控风险）
- 一个 **DeepSeek API key**（[platform.deepseek.com](https://platform.deepseek.com) 申请，很便宜）

### 1. 克隆仓库

```bash
git clone https://github.com/你的用户名/QQ-bot-ningning.git
cd QQ-bot-ningning/qq-bot
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
copy config.example.yaml config.yaml
# Linux / macOS
# cp .env.example .env && cp config.example.yaml config.yaml
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
> 该文件已被 `.gitignore` 忽略（含群号等本地配置，不会误提交到仓库）。

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

1. **下载**：https://github.com/NapNeko/NapCatQQ/releases ，下载 **NapCat.Shell.zip** 并解压（推荐解压到项目同级目录，如 `..\napcat-shell\`，或项目内 `napcat\` 子目录）。
2. **安装 QQ**：安装与 NapCat 版本匹配的 QQ NT（参考 NapCat 发布说明里推荐的 QQ 版本）。
3. **登录小号**：运行 NapCat 目录下的 `launcher.bat`（管理员）或 `launcher-user.bat`（免管理员）→ 用手机 QQ 扫码登录你的小号。
4. **配置反向 WebSocket**：登录后打开 Web 控制台（默认 http://127.0.0.1:6099/webui ），在「网络配置 / Network」里新建一条 **WebSocket 客户端**，URL 填：

   ```
   ws://127.0.0.1:8080/onebot/v11/ws
   ```

   保存后重启 NapCat（或重新连接）。

   > 反向 WebSocket 里 NapCat 是「客户端」，NoneBot 是「服务器」，所以选 **WebSocket 客户端**。

5. **验证连接**：回到 `python bot.py` 的终端，会多出类似日志：

   ```
   [INFO] nonebot | Bot xxxxxxx@onebot 已连接
   ```

   同时在 QQ 群里发一句 `/echo 你好`，机器人会复读「你好」，说明整条链路通了。

   > `/echo` 是 NoneBot 自带的调试插件，测试完可在 `pyproject.toml` 里删掉 `builtin_plugins = ["echo"]`。

### 6. 一键启动（可选）

Windows 下配好环境后，双击项目根目录的 `一键启动.bat`，会自动拉起 NapCat + bot。
脚本会按顺序自动查找 NapCat 目录（`napcat\` → 上级 `napcat-shell\` → 上级 `napcat\`），
找不到时会给出提示。

## 功能插件

| 功能 | 触发方式 | 效果 |
| --- | --- | --- |
| 骰子 | `r1d6`、`r2d8+1`、`r4d6kh3` | 掷骰子并回结果 |
| 黑幽灵的机械箱子 | `/开箱` 或消息含「开箱子」「机械箱子」 | 开箱抽奖：垃圾/材料/绿装/蓝装/紫装，纯随机无保底，附韩萧毒舌点评 |

> 机械箱子玩法的出处是《超神机械师》276-278 章：韩萧在避难所广场卖「机械箱子」，大部分是废零件，极少数紫装，出货全凭运气。本插件的抽奖也是**完全随机、无保底、无补偿**。

## 世界观知识库

`corpus/knowledge.yaml` 内置了《超神机械师》的**核心设定知识库**——精选约 100 个世界观名词，每个都带**详细的设定描述**（含背景、关系、情节），按六类组织：

| 分类 | 数量 | 示例 |
| --- | --- | --- |
| 地点与势力 | 32 | 海蓝星、破碎星环、龙坦、黯星、圣约 |
| 人物 | 22 | 韩萧、海拉、艾默丝、异神、麦尼逊 |
| 装备 | 26 | 折叠战刀、机械动力臂、黑王序列、虚龙 |
| 事件 | 4 | 异化之灾、萌芽组织覆灭、海蓝星事件、异神之战 |
| 技能 | 14 | 机械制造、磁力掌控、枪斗术、召唤术 |
| 知识 | 8 | 超A级、能级理论、信用点、技能书 |

**运行时按需检索**：群聊消息里命中哪个名词，就把对应的「名词 + 分类 + 详细描述」注入提示，让韩萧"认识"自己的世界，自然地接话。不命中的名词不会占用 prompt。

### 扩展知识库

想加新的名词或新分类，**直接编辑 `corpus/knowledge.yaml` 即可，无需改代码**，格式为 `名词: 描述`：

```yaml
组织:
  神族公会: 收购紫装的大公会
  天空领域: 与神族竞争的收购公会
```

> 注意：① 改完要**重启 bot**（知识库有缓存）；② 名词建议 **≥2 字**；③ 不要重跑 `clean_and_describe.py`（它会重写成固定的六类，覆盖你手动加的栏目）。

## 调人格

打开 `qq-bot/config.yaml`，改 `persona` 即可，字段含义见文件内注释。

| 想达到的效果 | 改哪里 |
| --- | --- |
| 更话痨 | `behavior.min_reply_interval` 调小 |
| 更安静 | 调大 `min_reply_interval` |
| 换名字/人设 | `persona.identity.name` / `role` / `style` |
| 回复更长/更短 | `persona.speech.max_length` |
| 调毒舌度/理性程度 | `persona.personality.sarcasm` / `seriousness` |

**韩萧的背景记忆与人物关系**在 `corpus/persona/qq_adaptation.yaml`：
- `lore_background`：韩萧的来历（被问起时回答）
- `character_relations`：海拉、艾默丝、异神等人的关系与「群聊提到时的反应」，加条目即生效，无需改代码

## 扩展知识库 / 蒸馏新人格

- **加背景知识、加人物关系、加世界观名词**：见上文「世界观知识库」和「调人格」。
- **蒸馏一个全新角色（换人设）**：见 [`qq-bot/docs/知识库与人格扩展指南.md`](qq-bot/docs/知识库与人格扩展指南.md)。
- **开发新插件**：见 [`qq-bot/docs/插件开发指南.md`](qq-bot/docs/插件开发指南.md)。

## 常见问题

**Q：`pip install` 报错，尤其 Python 3.14**
A：个别库还没完全适配 3.14。删掉 `.venv` 用 Python 3.11/3.12 重建：`py -3.12 -m venv .venv`。

**Q：NapCat 连不上，bot 日志没有「已连接」**
A：确认 bot 已启动且监听 8080；确认 NapCat 填的是 `ws://127.0.0.1:8080/onebot/v11/ws`（`/onebot/v11/ws` 路径不能漏），且选的是「WebSocket 客户端」。

**Q：NapCat 不弹二维码 / 启动失败**
A：多半是 QQ 版本与 NapCat 不匹配。看 NapCat 发布说明里推荐的 QQ 版本，安装对应版本再试；同时关闭 QQ 自动更新。

**Q：@机器人没反应**
A：① `config.yaml` 的 `groups` 是否含该群号；② `.env` 的 key 是否填对；③ 看终端有没有 `调用大模型失败` 的报错。

**Q：机器人从不主动说话**
A：`should_speak` 里相关性低就会沉默，这是预期行为。可以临时在群里聊它熟悉的话题（机械、游戏、科幻），或调低概率门阈值。

**Q：改了 knowledge.yaml 为什么不生效**
A：知识库有 `lru_cache` 缓存，改完需要**重启 bot**（或触发热重载）才会重新加载。

## 免责声明

- NapCat/OneBot 属于**第三方 QQ 自动化接入**，不是腾讯官方机器人接口；QQ 客户端升级可能暂时失效，需等 NapCat 适配。
- 有**账号风控**风险，务必用专门的小号 + 测试群，不要用大号。
- 群成员知情与隐私：机器人会读到群消息，建议只在朋友/测试群使用，并告知成员。

## 许可证

（按需补充，例如 MIT。此处暂未指定，如需公开使用请先确认游戏素材与图片的版权。）
