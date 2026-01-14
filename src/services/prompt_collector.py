"""Prompt Data Collection Service.

收集和存储 prompt 数据用于后续分析和模型优化。
主要收集两个步骤：
1. 找 Target (find_target_recommendations)
2. 生成邮件 (generate_email)

数据格式：
{
    "id": "uuid",
    "user_info": {...},
    "prompt_find_target": "...",
    "output_find_target": "...",
    "prompt_generate_email": "...",
    "output_generate_email": "...",
    "timestamp": "ISO-8601"
}

DATA_DIR 由环境变量配置：
  - Render 生产环境: /var/data (Persistent Disk)
  - 本地开发: ./data
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field, asdict
from threading import Lock

# 从统一配置导入数据目录
from config import DATA_DIR

# Prompt 日志存储目录
DATA_DIR_PROMPTS = DATA_DIR / "prompt_logs"


def get_local_now() -> datetime:
    """获取本地时间（带时区）"""
    return datetime.now().astimezone()


@dataclass
class PromptRecord:
    """单条 Prompt 数据记录"""
    id: str
    user_info: dict[str, Any]
    prompt_find_target: str = ""
    output_find_target: str = ""
    prompt_generate_email: str = ""
    output_generate_email: str = ""
    timestamp: str = ""
    
    # 找到的推荐人物（结构化数据，包含职位、网址等）
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    
    # 额外元数据
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            # 使用本地时间，带时区信息
            self.timestamp = get_local_now().isoformat()
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromptRecord":
        return cls(
            id=data.get("id", ""),
            user_info=data.get("user_info", {}),
            prompt_find_target=data.get("prompt_find_target", ""),
            output_find_target=data.get("output_find_target", ""),
            prompt_generate_email=data.get("prompt_generate_email", ""),
            output_generate_email=data.get("output_generate_email", ""),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )


class PromptDataCollector:
    """Prompt 数据收集器 - 线程安全"""
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._current_sessions: dict[str, PromptRecord] = {}
        self._session_lock = Lock()
        self._enabled = os.environ.get("COLLECT_PROMPTS", "true").lower() in ("1", "true", "yes")
        
        # 确保数据目录存在
        DATA_DIR_PROMPTS.mkdir(parents=True, exist_ok=True)
    
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    def enable(self) -> None:
        self._enabled = True
    
    def disable(self) -> None:
        self._enabled = False
    
    def start_session(self, user_info: dict[str, Any] | None = None) -> str:
        """开始一个新的数据收集会话，返回 session_id"""
        if not self._enabled:
            return ""
        
        session_id = str(uuid.uuid4())
        record = PromptRecord(
            id=session_id,
            user_info=user_info or {},
        )
        
        with self._session_lock:
            self._current_sessions[session_id] = record
        
        return session_id
    
    def record_find_target(
        self,
        session_id: str,
        prompt: str,
        output: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """记录 find_target 步骤的 prompt 和 output"""
        if not self._enabled or not session_id:
            return
        
        with self._session_lock:
            if session_id not in self._current_sessions:
                return
            record = self._current_sessions[session_id]
            record.prompt_find_target = prompt
            record.output_find_target = output
            if metadata:
                record.metadata.update({"find_target": metadata})
    
    def record_generate_email(
        self,
        session_id: str,
        prompt: str,
        output: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """记录 generate_email 步骤的 prompt 和 output"""
        if not self._enabled or not session_id:
            return
        
        with self._session_lock:
            if session_id not in self._current_sessions:
                return
            record = self._current_sessions[session_id]
            record.prompt_generate_email = prompt
            record.output_generate_email = output
            if metadata:
                record.metadata.update({"generate_email": metadata})
    
    def save_find_target_partial(
        self,
        session_id: str,
        recommendations: list[dict[str, Any]],
    ) -> Path | None:
        """找人后立即保存部分数据（不结束会话）
        
        保存内容：
        - user_info（用户画像、purpose、field 等）
        - prompt_find_target（搜索 prompt）
        - output_find_target（原始输出）
        - recommendations（结构化的人物信息：姓名、职位、公司、网址等）
        """
        if not self._enabled or not session_id:
            return None
        
        with self._session_lock:
            if session_id not in self._current_sessions:
                return None
            record = self._current_sessions[session_id]
            record.recommendations = recommendations
        
        # 保存到单独的 find_target 目录
        return self._save_find_target_record(record)
    
    def _save_find_target_record(self, record: PromptRecord) -> Path:
        """保存找人阶段的记录到单独目录"""
        # 解析时间
        try:
            ts_dt = datetime.fromisoformat(record.timestamp)
        except (ValueError, TypeError):
            ts_dt = get_local_now()
        
        # 保存到 find_target_logs 目录
        find_target_dir = DATA_DIR_PROMPTS.parent / "find_target_logs"
        date_str = ts_dt.strftime("%Y-%m-%d")
        day_dir = find_target_dir / date_str
        day_dir.mkdir(parents=True, exist_ok=True)
        
        # 文件名
        ts = ts_dt.strftime("%H%M%S")
        filename = f"{ts}_{record.id[:8]}.json"
        filepath = day_dir / filename
        
        # 构建保存内容（只保存找人相关的字段）
        save_data = {
            "id": record.id,
            "timestamp": record.timestamp,
            "user_info": record.user_info,
            "prompt_find_target": record.prompt_find_target,
            "output_find_target": record.output_find_target,
            "recommendations": record.recommendations,
            "metadata": record.metadata.get("find_target", {}),
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        
        print(f"[PromptCollector] Saved find_target: {filepath}")
        return filepath

    def end_session(self, session_id: str, save: bool = True) -> PromptRecord | None:
        """结束会话，可选保存到文件"""
        if not self._enabled or not session_id:
            return None
        
        with self._session_lock:
            if session_id not in self._current_sessions:
                return None
            record = self._current_sessions.pop(session_id)
        
        if save:
            self._save_record(record)
        
        return record
    
    def _save_record(self, record: PromptRecord) -> Path:
        """保存记录到 JSON 文件"""
        # 解析 record 的 timestamp 来确定日期和时间
        try:
            # 尝试解析带时区的 ISO 格式
            ts_dt = datetime.fromisoformat(record.timestamp)
        except (ValueError, TypeError):
            # 回退到当前本地时间
            ts_dt = get_local_now()
        
        # 按日期分目录（使用 record 的时间）
        date_str = ts_dt.strftime("%Y-%m-%d")
        day_dir = DATA_DIR_PROMPTS / date_str
        day_dir.mkdir(parents=True, exist_ok=True)
        
        # 文件名：{timestamp}_{id[:8]}.json（使用 record 的时间）
        ts = ts_dt.strftime("%H%M%S")
        filename = f"{ts}_{record.id[:8]}.json"
        filepath = day_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(record.to_json())
        
        print(f"[PromptCollector] Saved: {filepath}")
        return filepath
    
    def save_immediate(
        self,
        user_info: dict[str, Any],
        prompt_find_target: str,
        output_find_target: str,
        prompt_generate_email: str,
        output_generate_email: str,
        metadata: dict[str, Any] | None = None,
    ) -> Path | None:
        """直接保存一条完整记录（不使用会话模式）"""
        if not self._enabled:
            return None
        
        record = PromptRecord(
            id=str(uuid.uuid4()),
            user_info=user_info,
            prompt_find_target=prompt_find_target,
            output_find_target=output_find_target,
            prompt_generate_email=prompt_generate_email,
            output_generate_email=output_generate_email,
            metadata=metadata or {},
        )
        
        return self._save_record(record)
    
    def load_all_records(self, date_filter: str | None = None) -> list[PromptRecord]:
        """加载所有记录，可选按日期过滤"""
        records = []
        
        if date_filter:
            dirs = [DATA_DIR_PROMPTS / date_filter] if (DATA_DIR_PROMPTS / date_filter).exists() else []
        else:
            dirs = [d for d in DATA_DIR_PROMPTS.iterdir() if d.is_dir()]
        
        for day_dir in dirs:
            for filepath in day_dir.glob("*.json"):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        records.append(PromptRecord.from_dict(data))
                except Exception as e:
                    print(f"[PromptCollector] Failed to load {filepath}: {e}")
        
        return records
    
    def export_to_jsonl(self, output_path: str | Path, date_filter: str | None = None) -> int:
        """导出所有记录到 JSONL 格式（每行一个 JSON）"""
        records = self.load_all_records(date_filter)
        output_path = Path(output_path)
        
        with open(output_path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        
        print(f"[PromptCollector] Exported {len(records)} records to {output_path}")
        return len(records)
    
    def export_to_csv(self, output_path: str | Path, date_filter: str | None = None) -> int:
        """导出所有记录到 CSV 格式"""
        import csv
        
        records = self.load_all_records(date_filter)
        output_path = Path(output_path)
        
        fieldnames = [
            "id", "timestamp", "user_info",
            "prompt_find_target", "output_find_target",
            "prompt_generate_email", "output_generate_email",
            "metadata"
        ]
        
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for record in records:
                row = {
                    "id": record.id,
                    "timestamp": record.timestamp,
                    "user_info": json.dumps(record.user_info, ensure_ascii=False),
                    "prompt_find_target": record.prompt_find_target,
                    "output_find_target": record.output_find_target,
                    "prompt_generate_email": record.prompt_generate_email,
                    "output_generate_email": record.output_generate_email,
                    "metadata": json.dumps(record.metadata, ensure_ascii=False),
                }
                writer.writerow(row)
        
        print(f"[PromptCollector] Exported {len(records)} records to {output_path}")
        return len(records)


# 全局单例
prompt_collector = PromptDataCollector()


# 便捷函数
def start_prompt_session(user_info: dict | None = None) -> str:
    """开始数据收集会话"""
    return prompt_collector.start_session(user_info)


def record_find_target_prompt(session_id: str, prompt: str, output: str) -> None:
    """记录 find_target 的 prompt/output"""
    prompt_collector.record_find_target(session_id, prompt, output)


def record_generate_email_prompt(session_id: str, prompt: str, output: str) -> None:
    """记录 generate_email 的 prompt/output"""
    prompt_collector.record_generate_email(session_id, prompt, output)


def save_find_target_results(session_id: str, recommendations: list[dict]) -> Path | None:
    """找人后立即保存结果（不结束会话）
    
    保存内容包括：
    - 用户信息（purpose, field, sender_name 等）
    - 搜索 prompt
    - 找到的人物信息（姓名、职位、公司、LinkedIn URL 等）
    """
    return prompt_collector.save_find_target_partial(session_id, recommendations)


def end_prompt_session(session_id: str) -> PromptRecord | None:
    """结束会话并保存"""
    return prompt_collector.end_session(session_id)
