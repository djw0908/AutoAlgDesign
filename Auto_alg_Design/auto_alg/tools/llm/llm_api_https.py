"""
基于 HTTPS 的 LLM 调用实现。

业务背景：
    平台需要一个统一的 LLM 接口来生成候选算法代码。本实现通过 HTTPS 请求兼容的
    Chat Completions 接口获取模型输出，用于在不依赖特定 SDK 的情况下对接不同服务端。

安全与配置说明：
    - host/key/model 由 GUI 输入，不在代码中硬编码
    - 网络异常会重试；在 debug_mode 下累计错误达到阈值会抛出异常便于定位
"""

from __future__ import annotations

import http.client
import json
import time
from typing import Any
import traceback
from ...base import LLM


class HttpsApi(LLM):
    def __init__(self, host, key, model, timeout=60, **kwargs):
        """
        初始化 HTTPS LLM 客户端。

        参数：
            host: 服务器域名或 IP（不包含协议前缀）
            key: API Key（Bearer Token）
            model: 模型名称
            timeout: 单次请求超时（秒）
            **kwargs: 透传的生成参数（例如 max_tokens/top_p/temperature）
        """
        super().__init__(**kwargs)
        self._host = host
        self._key = key
        self._model = model
        self._timeout = timeout
        self._kwargs = kwargs
        self._cumulative_error = 0

    def draw_sample(self, prompt: str | Any, *args, **kwargs) -> str:
        """
        调用远端模型生成一次输出。

        参数：
            prompt:
                - str：用户输入文本
                - Any：已组装好的 messages 列表（role/content 结构）

        返回：
            模型输出文本内容。

        异常处理：
            - debug_mode=True：累计错误达到阈值抛出 RuntimeError
            - debug_mode=False：打印异常并 sleep 后重试
        """
        if isinstance(prompt, str):
            prompt = [{'role': 'user', 'content': prompt.strip()}]

        while True:
            try:
                conn = http.client.HTTPSConnection(self._host, timeout=self._timeout)
                payload = json.dumps({
                    'max_tokens': self._kwargs.get('max_tokens', 4096),
                    'top_p': self._kwargs.get('top_p', None),
                    'temperature': self._kwargs.get('temperature', 1.0),
                    'model': self._model,
                    'messages': prompt
                })
                headers = {
                    'Authorization': f'Bearer {self._key}',
                    'User-Agent': 'Apifox/1.0.0',
                    'Content-Type': 'application/json'
                }
                conn.request('POST', '/v1/chat/completions', payload, headers)
                res = conn.getresponse()
                data = res.read().decode('utf-8')
                data = json.loads(data)
                             
                response = data['choices'][0]['message']['content']
                if self.debug_mode:
                    self._cumulative_error = 0
                return response
            except Exception as e:
                self._cumulative_error += 1
                if self.debug_mode:
                    if self._cumulative_error == 10:
                        raise RuntimeError(f'{self.__class__.__name__} error: {traceback.format_exc()}.'
                                           f'You may check your API host and API key.')
                else:
                    print(f'{self.__class__.__name__} error: {traceback.format_exc()}.'
                          f'You may check your API host and API key.')
                    time.sleep(2)
                continue
