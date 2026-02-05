"""Moonshot AI Service - LinkedIn URL discovery using $web_search.

This module provides:
- Real web search via Moonshot's built-in $web_search function
- LinkedIn URL lookup with verification
- Cost: ￥0.03 per search + tokens

API: https://platform.moonshot.cn/docs/guide/use-web-search
"""

import os
import json
from typing import Optional
from dataclasses import dataclass
from openai import OpenAI


@dataclass
class MoonshotLinkedInResult:
    """Result from Moonshot LinkedIn URL lookup."""
    success: bool
    linkedin_url: Optional[str]
    confidence: str  # HIGH, MEDIUM, LOW, NOT_FOUND, ERROR
    token_usage: dict
    search_tokens: int  # Tokens used by web search
    error: Optional[str]


class MoonshotService:
    """Service for Moonshot AI LinkedIn URL discovery with real web search."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Moonshot service.
        
        Args:
            api_key: Moonshot API key. If None, reads from MOONSHOT_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("MOONSHOT_API_KEY")
        if not self.api_key:
            raise ValueError("Moonshot API key not provided and MOONSHOT_API_KEY not set")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.moonshot.cn/v1"
        )
        # Use kimi-k2-turbo-preview for large context window (web search results)
        self.model = "kimi-k2-turbo-preview"
    
    def _chat_with_web_search(self, messages: list[dict]) -> tuple[dict, dict]:
        """Call Moonshot with web search enabled.
        
        Returns:
            Tuple of (choice, usage_info)
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,
            max_tokens=2000,
            tools=[
                {
                    "type": "builtin_function",
                    "function": {
                        "name": "$web_search"
                    }
                }
            ]
        )
        
        choice = response.choices[0]
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }
        
        return choice, usage
    
    def find_linkedin_url(
        self,
        name: str,
        title: str = "",
        company: str = "",
        location: str = "",
        *,
        additional_context: str = "",
    ) -> MoonshotLinkedInResult:
        """Find LinkedIn URL for a person using real web search.
        
        Args:
            name: Person's name (can be partially obfuscated)
            title: Job title
            company: Company name
            location: Location (city, state)
            additional_context: Any additional context to help search
        
        Returns:
            MoonshotLinkedInResult with LinkedIn URL if found via web search
        """
        # Build search query
        search_parts = [name]
        if title:
            search_parts.append(title)
        if company:
            search_parts.append(company)
        if location:
            search_parts.append(location)
        
        search_query = " ".join(search_parts) + " LinkedIn"
        
        # Build prompt for Moonshot
        prompt = f"""请搜索并找到以下人物的 LinkedIn 个人主页 URL：

人物信息：
- 姓名：{name}
- 职位：{title or '未知'}
- 公司：{company or '未知'}
- 地点：{location or '未知'}

要求：
1. 使用网页搜索找到这个人的真实 LinkedIn 个人主页
2. 只返回 LinkedIn URL（格式：https://www.linkedin.com/in/...）
3. 如果找不到确切的人，回复 "NOT_FOUND"
4. 如果信息不足，回复 "INSUFFICIENT_INFO"
5. 不要猜测或编造 URL，只返回搜索到的真实结果

注意：即使姓名被部分混淆（如 "John Do***son"），也要尝试根据职位和公司信息搜索。"""
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的信息检索助手。你可以使用网页搜索找到准确的 LinkedIn 个人主页链接。不要猜测或编造链接，只返回真实搜索到的结果。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        try:
            search_tokens = 0
            total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            
            # Loop to handle tool calls
            finish_reason = None
            while finish_reason is None or finish_reason == "tool_calls":
                choice, usage = self._chat_with_web_search(messages)
                finish_reason = choice.finish_reason
                
                # Accumulate usage
                for key in total_usage:
                    total_usage[key] += usage[key]
                
                if finish_reason == "tool_calls":
                    # Add assistant message with tool calls
                    messages.append(choice.message)
                    
                    # Process each tool call
                    for tool_call in choice.message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_arguments = json.loads(tool_call.function.arguments)
                        
                        if tool_name == "$web_search":
                            # Extract search tokens from arguments
                            search_tokens = tool_arguments.get("usage", {}).get("total_tokens", 0)
                            
                            # Return arguments as-is (Moonshot executes the search)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_name,
                                "content": json.dumps(tool_arguments)
                            })
                        else:
                            # Unknown tool
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_name,
                                "content": json.dumps({"error": f"Unknown tool: {tool_name}"})
                            })
            
            # Extract final response
            linkedin_url = choice.message.content.strip()
            
            # Parse result
            if "NOT_FOUND" in linkedin_url:
                return MoonshotLinkedInResult(
                    success=False,
                    linkedin_url=None,
                    confidence="NOT_FOUND",
                    token_usage=total_usage,
                    search_tokens=search_tokens,
                    error=None
                )
            elif "INSUFFICIENT_INFO" in linkedin_url:
                return MoonshotLinkedInResult(
                    success=False,
                    linkedin_url=None,
                    confidence="INSUFFICIENT_INFO",
                    token_usage=total_usage,
                    search_tokens=search_tokens,
                    error=None
                )
            elif "linkedin.com/in/" in linkedin_url.lower():
                # Extract URL from response
                import re
                url_match = re.search(r'https://[^\s]+linkedin\.com/in/[^\s\)]+', linkedin_url, re.IGNORECASE)
                if url_match:
                    extracted_url = url_match.group(0)
                    # Clean up trailing punctuation
                    extracted_url = extracted_url.rstrip('.,;:!?')
                    
                    # Determine confidence
                    confidence = "HIGH"
                    if "***" in name:  # Obfuscated name
                        confidence = "MEDIUM"
                    if not company and not title:
                        confidence = "LOW"
                    
                    return MoonshotLinkedInResult(
                        success=True,
                        linkedin_url=extracted_url,
                        confidence=confidence,
                        token_usage=total_usage,
                        search_tokens=search_tokens,
                        error=None
                    )
                else:
                    # LinkedIn mentioned but no valid URL found
                    return MoonshotLinkedInResult(
                        success=False,
                        linkedin_url=None,
                        confidence="INVALID_RESPONSE",
                        token_usage=total_usage,
                        search_tokens=search_tokens,
                        error=f"Response mentions LinkedIn but no valid URL: {linkedin_url[:200]}"
                    )
            else:
                return MoonshotLinkedInResult(
                    success=False,
                    linkedin_url=None,
                    confidence="INVALID_RESPONSE",
                    token_usage=total_usage,
                    search_tokens=search_tokens,
                    error=f"Unexpected response: {linkedin_url[:200]}"
                )
        
        except Exception as e:
            return MoonshotLinkedInResult(
                success=False,
                linkedin_url=None,
                confidence="ERROR",
                token_usage={},
                search_tokens=0,
                error=str(e)
            )
    
    def batch_find_linkedin_urls(
        self,
        candidates: list[dict],
    ) -> list[MoonshotLinkedInResult]:
        """Find LinkedIn URLs for multiple candidates using web search.
        
        Args:
            candidates: List of dicts with keys: name, title, company, location
        
        Returns:
            List of MoonshotLinkedInResult objects
            
        Note: Each search costs ￥0.03 + tokens. Use wisely!
        """
        results = []
        for candidate in candidates:
            result = self.find_linkedin_url(
                name=candidate.get("name", ""),
                title=candidate.get("title", ""),
                company=candidate.get("company", ""),
                location=candidate.get("location", ""),
            )
            results.append(result)
        
        return results


def create_moonshot_service() -> MoonshotService | None:
    """Create Moonshot service if API key is available.
    
    Returns:
        MoonshotService instance or None if API key not configured
    """
    try:
        return MoonshotService()
    except ValueError:
        return None
