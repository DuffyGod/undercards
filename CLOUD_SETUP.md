# 云端运行配置

目标仓库：`DuffyGod/undercards`。在Codex Cloud创建或选择使用本仓库的环境，确认Python 3.11+。环境配置/安装脚本先运行：

```sh
python tools/restore_stage_evidence.py
python tools/verify_stage.py
```

不需要pip安装外部包；数值计算和测试不需要API凭据。当前本地线程不能由提供的工具直接搬成云端线程，请新建云端任务并让它读取`CONTINUATION.md`。

## 腾讯 Token Plan / DeepSeek

接口读取名为`TENCENT_API_KEY`的环境值，目标为`https://tokenhub.tencentmaas.com/plan/v3/chat/completions`。默认模型是用户现有接口的`deepseek/deepseek-flash`，不是OpenAI API，不需要`OPENAI_API_KEY`。

建议在环境配置`Network secrets → Manage`创建：

| 字段 | 值 |
|---|---|
| Key | `TENCENT_API_KEY` |
| Value | 用户自己的腾讯 Token Plan API key |
| Allowed domains | `tokenhub.tencentmaas.com` |

官方机制是向进程提供占位值，再由HTTPS代理向许可目标替换真实凭据。本接口只使用Bearer头，不做本地签名，因此设计上适配这种方式，仍需云端首次烟测确认。不要同时创建同名直接环境变量。若需采用直接环境变量，使用同名`TENCENT_API_KEY`并单独允许目标域名；程序会直接读到该值。

个人凭据可从`Settings → Codex Cloud → Personal vault`配置，选本环境。环境须请求对应Key才会向任务交付。旧版Cloud（Legacy）的配置不同，不要把只在setup阶段存在的旧版secret误认为任务期间可用。

云端优先使用仓库接口脚本，可设置`UNDERCARDS_API_HELPER`为`tools/test_llm_api.py`；支持相对路径时从仓库根运行。旧Windows路径不应成为云端依赖。

首次验证只报告调用是否成功、用量、缓存和状态，不能打印环境值或Authorization。密钥不得写入源码、README、Git提交或对话。

## 云端新任务的起始消息

> 请读取CONTINUATION.md、当前方法报告和Undercards Skill，恢复阶段证据并运行离线验证，继续通用启发式Value建模。保持共同数值标准，增加DeepSeek并发辅助任务；机制提取不能直接决定Gold价格。当前17/404的局部覆盖远未完成长期目标，请优先扩通用机制并验证跨机制等价、风险与构筑适配，不为讨论卡专门拟合。

官方说明：[Codex Cloud](https://learn.chatgpt.com/docs/cloud)、[环境变量与网络密钥](https://learn.chatgpt.com/docs/environments/cloud-environments#configure-environment-variables-and-network-secrets)。
