"""
基于 OpenAI Python SDK 的 LLM 调用实现。

业务背景：
    与 HTTPS 直连实现相比，本模块复用 OpenAI SDK 的连接管理与请求封装能力，
    通过 base_url 支持兼容 OpenAI API 规范的第三方服务端。

安全与配置说明：
    base_url/api_key/model 等敏感或环境相关信息由 GUI 输入，不在代码中硬编码。
"""

from __future__ import annotations

import openai
from typing import Any

from auto_alg.base import LLM


class OpenAI(LLM):
    def __init__(self, base_url: str, api_key: str, model: str, timeout=60, **kwargs):
        """
        初始化 OpenAI SDK 客户端。

        参数：
            base_url: API Base URL
            api_key: API Key
            model: 模型名称
            timeout: 请求超时时间（秒）
            **kwargs: 透传给 SDK 客户端的其他参数
        """
        super().__init__()
        self._model = model
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, **kwargs)

    def draw_sample(self, prompt: str | Any, *args, **kwargs) -> str:
        """
        调用模型生成一次输出。

        参数：
            prompt:
                - str：用户输入文本
                - Any：已组装好的 messages 列表

        返回：
            模型输出的 message.content 字符串。
        """
        if isinstance(prompt, str):
            prompt = [{'role': 'user', 'content': prompt.strip()}]
        response = self._client.chat.completions.create(
            model=self._model,
            messages=prompt,
            stream=False,
        )
        return response.choices[0].message.content
