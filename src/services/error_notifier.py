"""Error notification service for WeChat Work webhook."""

import os
import json
import traceback
import time
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional
import requests


class ErrorNotifier:
    """Send error notifications to WeChat Work via webhook."""

    def __init__(self, webhook_url: Optional[str] = None, db_path: Optional[Path] = None):
        self.webhook_url = webhook_url or os.environ.get("WECHAT_WEBHOOK_URL", "")
        self.enabled = bool(self.webhook_url)
        self.timeout = 5  # seconds
        
        # Error deduplication
        self.recent_errors = {}  # {error_key: (timestamp, count)}
        self.dedup_window = 300  # 5 minutes in seconds
        self.max_dedup_entries = 1000  # Prevent memory leak
        
        # Database path for error logging - use config.DB_PATH if provided
        if db_path:
            self.db_path = Path(db_path)
        else:
            # Fallback to default (for backward compatibility)
            from config import DB_PATH
            self.db_path = Path(DB_PATH)
        self._ensure_error_logs_table()

    def notify_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        request_path: Optional[str] = None,
    ) -> bool:
        """
        Send error notification to WeChat Work.

        Args:
            error: The exception that occurred
            context: Additional context dict (optional)
            user_id: User ID if available (optional)
            request_path: Request path/endpoint (optional)

        Returns:
            True if notification sent successfully, False otherwise
        """
        # Always log error to database
        error_log_id = self._save_error_to_db(error, context, user_id, request_path)
        
        if not self.enabled:
            return False

        try:
            # Check for duplicate errors
            error_key = self._generate_error_key(error, request_path)
            now = time.time()
            
            # Clean up old entries periodically
            if len(self.recent_errors) > self.max_dedup_entries:
                self._cleanup_old_errors(now)
            
            # Check if this error was recently sent
            if error_key in self.recent_errors:
                last_time, count = self.recent_errors[error_key]
                if now - last_time < self.dedup_window:
                    # Update count and skip notification
                    self.recent_errors[error_key] = (now, count + 1)
                    print(f"[ERROR_NOTIFIER] Skipping duplicate error (count: {count + 1}): {error_key[:50]}...")
                    return True  # Return True to indicate it was handled
            
            # Send notification
            message = self._format_error_message(error, context, user_id, request_path)
            success = self._send_to_wechat(message)
            
            # Record this error for deduplication
            if success:
                self.recent_errors[error_key] = (now, 1)
            
            return success
        except Exception as e:
            # Don't let notification failures crash the app
            print(f"Failed to send error notification: {e}")
            return False

    def _format_error_message(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]],
        user_id: Optional[str],
        request_path: Optional[str],
    ) -> str:
        """Format error details as markdown message."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_type = type(error).__name__
        error_msg = str(error)

        # Build message sections
        sections = [
            f"## 🚨 Connact.ai 错误报警",
            f"**时间**: {timestamp}",
            f"**错误类型**: `{error_type}`",
        ]

        if request_path:
            sections.append(f"**请求路径**: `{request_path}`")

        if user_id:
            sections.append(f"**用户ID**: `{user_id}`")

        sections.append(f"\n**错误信息**:\n```\n{error_msg}\n```")

        # Add context if provided
        if context:
            context_str = json.dumps(context, indent=2, ensure_ascii=False)
            sections.append(f"\n**上下文**:\n```json\n{context_str}\n```")

        # Add traceback (limited to last 10 lines)
        tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
        tb_preview = "".join(tb_lines[-10:])  # Last 10 lines
        sections.append(f"\n**堆栈信息** (最后10行):\n```python\n{tb_preview}\n```")

        return "\n".join(sections)

    def _send_to_wechat(self, message: str) -> bool:
        """Send markdown message to WeChat Work webhook."""
        # Truncate message if too long (WeChat limit: 4096 bytes)
        max_bytes = 4000  # Leave some margin
        message_bytes = message.encode('utf-8')
        if len(message_bytes) > max_bytes:
            message = message_bytes[:max_bytes].decode('utf-8', errors='ignore')
            message += "\n\n...(消息过长已截断)"
        
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": message
            }
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            result = response.json()
            
            if result.get("errcode") == 0:
                return True
            else:
                print(f"WeChat API error: {result}")
                return False

        except requests.RequestException as e:
            print(f"WeChat webhook request failed: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error sending to WeChat: {e}")
            return False

    def notify_info(self, message: str) -> bool:
        """
        Send info message to WeChat Work (for non-error notifications).

        Args:
            message: Plain text message

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False

        payload = {
            "msgtype": "text",
            "text": {
                "content": message
            }
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            result = response.json()
            return result.get("errcode") == 0
        except Exception as e:
            print(f"Failed to send info notification: {e}")
            return False
    
    def _generate_error_key(self, error: Exception, request_path: Optional[str]) -> str:
        """Generate a unique key for error deduplication."""
        error_type = type(error).__name__
        error_msg = str(error)[:100]  # First 100 chars
        path = request_path or "unknown"
        return f"{error_type}:{error_msg}:{path}"
    
    def _cleanup_old_errors(self, current_time: float) -> None:
        """Remove errors older than dedup_window."""
        to_remove = []
        for key, (timestamp, _) in self.recent_errors.items():
            if current_time - timestamp > self.dedup_window:
                to_remove.append(key)
        
        for key in to_remove:
            del self.recent_errors[key]
        
        if to_remove:
            print(f"[ERROR_NOTIFIER] Cleaned up {len(to_remove)} old error entries")
    
    def _ensure_error_logs_table(self) -> None:
        """Ensure error_logs table exists in database."""
        try:
            if not self.db_path.parent.exists():
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS error_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    request_path TEXT,
                    user_id TEXT,
                    context TEXT,
                    stack_trace TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP,
                    resolved_by TEXT,
                    notes TEXT
                )
            """)
            
            # Create index for faster queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_error_logs_created 
                ON error_logs(created_at DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_error_logs_resolved 
                ON error_logs(resolved_at)
            """)
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[ERROR_NOTIFIER] Failed to create error_logs table: {e}")
    
    def _save_error_to_db(self, error: Exception, context: Optional[Dict[str, Any]], 
                          user_id: Optional[str], request_path: Optional[str]) -> Optional[int]:
        """Save error to database for admin review."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            error_type = type(error).__name__
            error_msg = str(error)
            context_json = json.dumps(context, ensure_ascii=False) if context else None
            
            # Get stack trace
            tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
            stack_trace = "".join(tb_lines)
            
            cursor.execute("""
                INSERT INTO error_logs 
                (error_type, error_message, request_path, user_id, context, stack_trace)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (error_type, error_msg, request_path, user_id, context_json, stack_trace))
            
            error_log_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return error_log_id
        except Exception as e:
            print(f"[ERROR_NOTIFIER] Failed to save error to database: {e}")
            return None


# Global instance - will be initialized with proper db_path on import
from config import DB_PATH
error_notifier = ErrorNotifier(db_path=DB_PATH)


def notify_error(
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    request_path: Optional[str] = None,
) -> bool:
    """
    Convenience function to notify error using global instance.

    Example:
        try:
            risky_operation()
        except Exception as e:
            notify_error(e, context={"operation": "generate_email"}, user_id=session.get("user_id"))
            raise  # Re-raise after notifying
    
    Returns:
        bool: True if notification sent successfully, False otherwise
    """
    return error_notifier.notify_error(error, context, user_id, request_path)
