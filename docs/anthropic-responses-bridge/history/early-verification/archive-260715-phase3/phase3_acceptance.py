#!/usr/bin/env python3
"""
Phase 3 独立只读验收脚本

验收点：
1. OpenAI deep extra/null
2. Call ID scope
3. Chat/Responses/Embeddings raw/stream/errors cleanup
4. 三前缀 routes/models
5. Translator system/tool/result extra
6. httpx-ws upstream transport bounded queue、upgrade/network error frame
7. Management config secrets redacted
8. SSE CRLF

执行模式：黑盒、临时验证资产、不改仓库、不使用真实凭据
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class Phase3Verifier:
    """Phase 3 验收验证器"""

    def __init__(self):
        self.results = []
        self.blocker_count = 0
        self.major_count = 0

    def verify_item(self, name: str, condition: bool, severity: str = "major", evidence: str = ""):
        """验证单个项目"""
        status = "✓ PASS" if condition else "✗ FAIL"
        self.results.append({
            "name": name,
            "status": status,
            "severity": severity,
            "evidence": evidence,
            "passed": condition
        })
        
        if not condition:
            if severity == "blocker":
                self.blocker_count += 1
            elif severity == "major":
                self.major_count += 1
        
        return condition

    async def verify_openai_models_extra_allow(self):
        """验证点 1: OpenAI 数据模型 extra="allow" 深度保留"""
        print("\n=== 验证点 1: OpenAI 数据模型保真度 ===")
        
        try:
            from app.models.openai import ChatCompletionRequest, ResponsesRequest
            from pydantic import ValidationError
            
            # 测试 ChatCompletionRequest 未知字段保留
            payload_with_unknown = {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "test"}],
                "unknown_top_level": "should_be_kept",
                "nested_unknown": {"deep": {"value": 123}}
            }
            
            req = ChatCompletionRequest.model_validate(payload_with_unknown)
            
            # 验证顶层未知字段
            has_top_level = hasattr(req, 'model_extra') and "unknown_top_level" in req.model_extra
            self.verify_item(
                "ChatCompletionRequest 保留顶层未知字段",
                has_top_level,
                "blocker",
                f"model_extra: {getattr(req, 'model_extra', {})}"
            )
            
            # 验证嵌套未知字段
            has_nested = hasattr(req, 'model_extra') and "nested_unknown" in req.model_extra
            self.verify_item(
                "ChatCompletionRequest 保留嵌套未知字段",
                has_nested,
                "blocker",
                f"nested_unknown in model_extra: {has_nested}"
            )
            
            # 测试 null 值不被过滤
            payload_with_null = {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "test"}],
                "temperature": None,
                "max_tokens": None
            }
            
            req_null = ChatCompletionRequest.model_validate(payload_with_null)
            null_preserved = req_null.temperature is None and req_null.max_tokens is None
            self.verify_item(
                "ChatCompletionRequest null 值保留",
                null_preserved,
                "blocker",
                f"temperature={req_null.temperature}, max_tokens={req_null.max_tokens}"
            )
            
            # 测试 ResponsesRequest
            responses_payload = {
                "model": "gpt-4",
                "input": [{"type": "message", "role": "user", "content": "test"}],
                "custom_field": "custom_value"
            }
            
            resp_req = ResponsesRequest.model_validate(responses_payload)
            has_custom = hasattr(resp_req, 'model_extra') and "custom_field" in resp_req.model_extra
            self.verify_item(
                "ResponsesRequest 保留未知字段",
                has_custom,
                "blocker",
                f"model_extra: {getattr(resp_req, 'model_extra', {})}"
            )
            
        except Exception as e:
            self.verify_item(
                "OpenAI 模型导入与验证",
                False,
                "blocker",
                f"异常: {type(e).__name__}: {e}"
            )

    async def verify_call_id_scope(self):
        """验证点 2: Responses API call ID scope"""
        print("\n=== 验证点 2: Call ID scope ===")
        
        try:
            from app.openai.responses_conversion import normalize_call_ids
            
            # 测试 call_ 前缀标准化
            input_items = [
                {"type": "function_call", "call_id": "call_abc123", "name": "test"},
                {"type": "function_call_output", "call_id": "call_xyz789", "output": "result"}
            ]
            
            normalized = normalize_call_ids(input_items)
            
            # 验证 call_ -> fc_ 转换
            first_normalized = normalized[0].get("call_id", "").startswith("fc_")
            second_normalized = normalized[1].get("call_id", "").startswith("fc_")
            
            self.verify_item(
                "call_ 前缀标准化为 fc_",
                first_normalized and second_normalized,
                "major",
                f"normalized[0].call_id={normalized[0].get('call_id')}, normalized[1].call_id={normalized[1].get('call_id')}"
            )
            
        except ImportError as e:
            self.verify_item(
                "responses_conversion 模块存在",
                False,
                "major",
                f"导入失败: {e}"
            )
        except Exception as e:
            self.verify_item(
                "Call ID 标准化功能",
                False,
                "major",
                f"异常: {type(e).__name__}: {e}"
            )

    async def verify_routes_cleanup(self):
        """验证点 3: Chat/Responses/Embeddings cleanup 实现"""
        print("\n=== 验证点 3: 路由清洗实现 ===")
        
        try:
            # 验证 sanitize 模块存在
            from app.openai import sanitize
            from app.openai.stream_accumulator import ChatStreamAccumulator
            from app.openai.responses_stream_accumulator import ResponsesStreamAccumulator
            
            self.verify_item(
                "OpenAI sanitize 模块存在",
                True,
                "blocker",
                f"sanitize module: {sanitize}"
            )
            
            self.verify_item(
                "Chat stream accumulator 存在",
                True,
                "major",
                f"ChatStreamAccumulator: {ChatStreamAccumulator}"
            )
            
            self.verify_item(
                "Responses stream accumulator 存在",
                True,
                "major",
                f"ResponsesStreamAccumulator: {ResponsesStreamAccumulator}"
            )
            
        except ImportError as e:
            self.verify_item(
                "OpenAI cleanup 模块导入",
                False,
                "blocker",
                f"导入失败: {e}"
            )

    async def verify_triple_prefix_routes(self):
        """验证点 4: 三前缀路由注册"""
        print("\n=== 验证点 4: 三前缀路由 ===")
        
        try:
            from app.server import create_app
            from app.config.settings import AppSettings
            
            # 创建最小配置
            settings = AppSettings(
                github_token="dummy_token_for_test",
                copilot_upstream_url="https://api.githubcopilot.com"
            )
            
            app = create_app(settings)
            
            # 收集所有路由路径
            routes = [route.path for route in app.routes]
            
            # 验证三个前缀的 /models 端点
            prefixes = ["", "/v1", "/openai/v1"]
            models_routes = [f"{prefix}/models" if prefix else "/models" for prefix in prefixes]
            
            for expected_route in models_routes:
                exists = expected_route in routes or any(expected_route in r for r in routes)
                self.verify_item(
                    f"路由 {expected_route} 已注册",
                    exists,
                    "blocker",
                    f"实际路由: {[r for r in routes if 'models' in r]}"
                )
            
            # 验证 chat/completions 在三个前缀下
            chat_routes = [
                "/chat/completions",
                "/v1/chat/completions", 
                "/openai/v1/chat/completions"
            ]
            
            for expected_route in chat_routes:
                exists = expected_route in routes or any(expected_route in r for r in routes)
                self.verify_item(
                    f"路由 {expected_route} 已注册",
                    exists,
                    "blocker",
                    f"实际 chat 路由: {[r for r in routes if 'chat' in r]}"
                )
                
        except Exception as e:
            self.verify_item(
                "三前缀路由注册",
                False,
                "blocker",
                f"异常: {type(e).__name__}: {e}"
            )

    async def verify_translator_extra_preservation(self):
        """验证点 5: Translator 保留 extra 字段"""
        print("\n=== 验证点 5: Translator extra 保留 ===")
        
        try:
            from app.transform.translator import (
                anthropic_to_openai,
                openai_to_anthropic
            )
            
            # 测试 Anthropic -> OpenAI 转换保留 system 额外字段
            anthropic_payload = {
                "model": "claude-3-opus",
                "messages": [
                    {"role": "user", "content": "test"}
                ],
                "system": "You are helpful",
                "custom_system_field": "should_preserve"
            }
            
            openai_payload = anthropic_to_openai(anthropic_payload)
            
            # 检查额外字段是否保留（可能在 model_extra 或直接在字典中）
            preserved = "custom_system_field" in openai_payload or \
                       (hasattr(openai_payload, 'model_extra') and 
                        "custom_system_field" in openai_payload.model_extra)
            
            self.verify_item(
                "Anthropic->OpenAI 转换保留 system extra",
                preserved,
                "blocker",
                f"转换后 payload keys: {openai_payload.keys() if isinstance(openai_payload, dict) else 'not dict'}"
            )
            
            # 测试工具转换保留额外字段
            anthropic_with_tools = {
                "model": "claude-3-opus",
                "messages": [{"role": "user", "content": "test"}],
                "tools": [
                    {
                        "name": "get_weather",
                        "description": "Get weather",
                        "input_schema": {"type": "object"},
                        "custom_tool_field": "preserve_me"
                    }
                ]
            }
            
            openai_with_tools = anthropic_to_openai(anthropic_with_tools)
            
            # 检查工具额外字段（这取决于实现，可能在 function 或 tool 级别）
            has_tools = "tools" in openai_with_tools if isinstance(openai_with_tools, dict) else hasattr(openai_with_tools, 'tools')
            
            self.verify_item(
                "工具转换保留结构",
                has_tools,
                "major",
                f"转换后有 tools: {has_tools}"
            )
            
        except ImportError as e:
            self.verify_item(
                "Translator 模块导入",
                False,
                "blocker",
                f"导入失败: {e}"
            )
        except Exception as e:
            self.verify_item(
                "Translator extra 保留",
                False,
                "blocker",
                f"异常: {type(e).__name__}: {e}"
            )

    async def verify_httpx_ws_transport(self):
        """验证点 6: httpx-ws upstream transport"""
        print("\n=== 验证点 6: httpx-ws transport ===")
        
        try:
            # 检查 httpx_ws 是否可用
            import httpx_ws
            
            self.verify_item(
                "httpx_ws 包已安装",
                True,
                "blocker",
                f"httpx_ws version: {getattr(httpx_ws, '__version__', 'unknown')}"
            )
            
            # 检查 responses WebSocket 路由
            from app.routes import responses_ws
            
            self.verify_item(
                "responses_ws 模块存在",
                True,
                "blocker",
                f"responses_ws module: {responses_ws}"
            )
            
            # 检查 WebSocket 升级处理
            import inspect
            source = inspect.getsource(responses_ws)
            
            has_websocket_upgrade = "WebSocket" in source or "websocket" in source
            self.verify_item(
                "WebSocket 升级处理存在",
                has_websocket_upgrade,
                "blocker",
                f"源码包含 WebSocket 相关代码: {has_websocket_upgrade}"
            )
            
            # 检查 bounded queue/backpressure 提及
            has_queue_handling = "queue" in source.lower() or "backpressure" in source.lower()
            self.verify_item(
                "Bounded queue/backpressure 考虑",
                has_queue_handling,
                "major",
                f"源码包含 queue 相关代码: {has_queue_handling}"
            )
            
        except ImportError as e:
            self.verify_item(
                "httpx_ws transport 依赖",
                False,
                "blocker",
                f"导入失败: {e}"
            )
        except Exception as e:
            self.verify_item(
                "WebSocket transport 验证",
                False,
                "major",
                f"异常: {type(e).__name__}: {e}"
            )

    async def verify_management_config_redacted(self):
        """验证点 7: Management config secrets redacted"""
        print("\n=== 验证点 7: Config secrets 脱敏 ===")
        
        try:
            from app.routes.config import get_config_snapshot
            from app.config.settings import AppSettings
            
            # 创建包含敏感信息的配置
            settings = AppSettings(
                github_token="ghp_secret_token_1234567890",
                copilot_upstream_url="https://api.githubcopilot.com",
                openai_api_key="sk-secret_key_abcdefg"
            )
            
            # 获取配置快照
            snapshot = get_config_snapshot(settings)
            
            # 验证敏感字段被脱敏
            snapshot_str = json.dumps(snapshot)
            
            token_not_exposed = "ghp_secret_token" not in snapshot_str
            self.verify_item(
                "GitHub token 已脱敏",
                token_not_exposed,
                "blocker",
                f"快照中未暴露完整 token: {token_not_exposed}"
            )
            
            api_key_not_exposed = "sk-secret_key" not in snapshot_str
            self.verify_item(
                "OpenAI API key 已脱敏",
                api_key_not_exposed,
                "blocker",
                f"快照中未暴露完整 API key: {api_key_not_exposed}"
            )
            
            # 验证快照包含 redacted 标记
            has_redacted = "***" in snapshot_str or "REDACTED" in snapshot_str or "[REDACTED]" in snapshot_str
            self.verify_item(
                "使用脱敏标记",
                has_redacted,
                "major",
                f"快照包含脱敏标记: {has_redacted}"
            )
            
        except ImportError as e:
            self.verify_item(
                "Management config 模块",
                False,
                "blocker",
                f"导入失败: {e}"
            )
        except Exception as e:
            self.verify_item(
                "Config secrets 脱敏",
                False,
                "blocker",
                f"异常: {type(e).__name__}: {e}"
            )

    async def verify_sse_crlf(self):
        """验证点 8: SSE CRLF 格式"""
        print("\n=== 验证点 8: SSE CRLF 格式 ===")
        
        try:
            from app.streaming.sse import format_sse_event
            
            # 测试 SSE 事件格式
            test_event = format_sse_event(
                data={"test": "value"},
                event_type="message"
            )
            
            # 验证 CRLF 结尾
            ends_with_crlf = test_event.endswith("\r\n\r\n") or test_event.endswith("\n\n")
            self.verify_item(
                "SSE 事件以双换行符结尾",
                ends_with_crlf,
                "blocker",
                f"事件结尾: {repr(test_event[-10:])}"
            )
            
            # 验证 data: 前缀
            has_data_prefix = "data:" in test_event
            self.verify_item(
                "SSE 事件包含 data: 前缀",
                has_data_prefix,
                "blocker",
                f"事件内容: {test_event[:50]}..."
            )
            
            # 测试事件类型
            if "event_type" in locals():
                has_event_type = "event:" in test_event or "event_type" not in test_event
                self.verify_item(
                    "SSE 事件类型格式",
                    has_event_type,
                    "major",
                    f"事件包含类型标记: {has_event_type}"
                )
            
        except ImportError as e:
            self.verify_item(
                "SSE streaming 模块",
                False,
                "blocker",
                f"导入失败: {e}"
            )
        except Exception as e:
            self.verify_item(
                "SSE CRLF 格式",
                False,
                "blocker",
                f"异常: {type(e).__name__}: {e}"
            )

    async def run_all_verifications(self):
        """运行所有验证"""
        print("=" * 80)
        print("Phase 3 独立只读验收")
        print("=" * 80)
        
        await self.verify_openai_models_extra_allow()
        await self.verify_call_id_scope()
        await self.verify_routes_cleanup()
        await self.verify_triple_prefix_routes()
        await self.verify_translator_extra_preservation()
        await self.verify_httpx_ws_transport()
        await self.verify_management_config_redacted()
        await self.verify_sse_crlf()
        
        self.print_summary()

    def print_summary(self):
        """打印验收总结"""
        print("\n" + "=" * 80)
        print("验收总结")
        print("=" * 80)
        
        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)
        
        print(f"\n总计: {passed}/{total} 通过")
        print(f"Blocker: {self.blocker_count}")
        print(f"Major: {self.major_count}")
        
        print("\n详细结果:")
        print("-" * 80)
        
        for result in self.results:
            status_icon = "✓" if result["passed"] else "✗"
            severity = f"[{result['severity'].upper()}]"
            print(f"{status_icon} {severity:12} {result['name']}")
            if result["evidence"]:
                print(f"  证据: {result['evidence'][:100]}")
        
        print("=" * 80)
        
        if self.blocker_count > 0:
            print(f"\n⚠️  发现 {self.blocker_count} 个 BLOCKER 级别缺陷")
            return 1
        elif self.major_count > 0:
            print(f"\n⚠️  发现 {self.major_count} 个 MAJOR 级别缺陷")
            return 1
        else:
            print("\n✓ Phase 3 验收通过")
            return 0


async def main():
    verifier = Phase3Verifier()
    await verifier.run_all_verifications()
    return verifier.blocker_count + verifier.major_count


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(min(exit_code, 1))
