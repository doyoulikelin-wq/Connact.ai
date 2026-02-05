#!/usr/bin/env python3
"""
管理员工具：手动管理用户 Apollo Credits

使用方法:
    # 查看用户当前 credits
    python admin_credits.py view user@example.com
    
    # 给用户添加 10 个 credits
    python admin_credits.py add user@example.com 10
    
    # 列出所有用户的 credits 使用情况
    python admin_credits.py list
    
    # 查看特定用户的详细信息
    python admin_credits.py info user@example.com
"""

import sys
import argparse
from datetime import datetime
from src.services.user_data_service import user_data_service
from src.services.auth_service import auth_service


def view_user_credits(user_email: str):
    """查看用户当前 credits"""
    print(f"\n🔍 查询用户: {user_email}")
    
    # Get user ID from email
    try:
        user = auth_service.get_user_by_email(user_email)
        if not user:
            print(f"❌ 错误: 未找到用户 '{user_email}'")
            return
        
        user_id = user.user_id
        print(f"   用户ID: {user_id}")
        
        # Get credits
        credits = user_data_service.get_user_credits(user_id)
        
        print(f"\n💰 Credits 信息:")
        print(f"   剩余 Apollo Credits: {credits.apollo_credits}")
        print(f"   累计已使用: {credits.total_used}")
        
        if credits.last_used_at:
            print(f"   最后使用时间: {credits.last_used_at}")
        else:
            print(f"   最后使用时间: 从未使用")
        
    except Exception as e:
        print(f"❌ 错误: {e}")


def add_user_credits(user_email: str, amount: int):
    """给用户添加 credits"""
    print(f"\n➕ 给用户 {user_email} 添加 {amount} credits")
    
    if amount <= 0:
        print("❌ 错误: 数量必须大于 0")
        return
    
    try:
        # Get user ID from email
        user = auth_service.get_user_by_email(user_email)
        if not user:
            print(f"❌ 错误: 未找到用户 '{user_email}'")
            return
        
        user_id = user.user_id
        
        # Get current credits
        credits = user_data_service.get_user_credits(user_id)
        old_amount = credits.apollo_credits
        
        # Add credits
        new_amount = user_data_service.add_credits(user_id, amount)
        
        print(f"\n✅ 成功!")
        print(f"   用户ID: {user_id}")
        print(f"   原 credits: {old_amount}")
        print(f"   新增: +{amount}")
        print(f"   当前 credits: {new_amount}")
        
    except Exception as e:
        print(f"❌ 错误: {e}")


def list_all_users():
    """列出所有用户的 credits 使用情况"""
    print("\n📊 所有用户 Credits 使用情况\n")
    print(f"{'邮箱':<40} {'剩余':<8} {'已用':<8} {'最后使用'}")
    print("=" * 90)
    
    try:
        import sqlite3
        from pathlib import Path
        
        db_path = Path(__file__).parent / "data" / "connact.db"
        if not db_path.exists():
            print("❌ 数据库文件不存在")
            return
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        query = """
        SELECT 
            u.email,
            u.user_id,
            COALESCE(c.apollo_credits, 5) as credits,
            COALESCE(c.total_used, 0) as used,
            c.last_used_at
        FROM users u
        LEFT JOIN user_credits c ON u.user_id = c.user_id
        ORDER BY u.created_at DESC
        """
        
        rows = conn.execute(query).fetchall()
        
        if not rows:
            print("(没有用户)")
            return
        
        total_credits = 0
        total_used = 0
        
        for row in rows:
            email = row["email"]
            credits = row["credits"]
            used = row["used"]
            last_used = row["last_used_at"] or "从未使用"
            
            total_credits += credits
            total_used += used
            
            # Format last_used
            if last_used != "从未使用":
                try:
                    dt = datetime.fromisoformat(last_used.replace("Z", "+00:00"))
                    last_used = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass
            
            print(f"{email:<40} {credits:<8} {used:<8} {last_used}")
        
        print("=" * 90)
        print(f"{'总计':<40} {total_credits:<8} {total_used:<8}")
        print(f"\n共 {len(rows)} 个用户")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


def show_user_info(user_email: str):
    """显示用户的详细信息"""
    print(f"\n👤 用户详细信息: {user_email}\n")
    
    try:
        # Get user
        user = auth_service.get_user_by_email(user_email)
        if not user:
            print(f"❌ 错误: 未找到用户 '{user_email}'")
            return
        
        # Basic info
        print("基本信息:")
        print(f"  邮箱: {user.email}")
        print(f"  用户ID: {user.user_id}")
        print(f"  是否验证: {'是' if user.is_verified else '否'}")
        print(f"  创建时间: {user.created_at}")
        
        # Credits info
        credits = user_data_service.get_user_credits(user.user_id)
        print(f"\nCredits 信息:")
        print(f"  剩余 Apollo Credits: {credits.apollo_credits}")
        print(f"  累计已使用: {credits.total_used}")
        print(f"  最后使用时间: {credits.last_used_at or '从未使用'}")
        
        # Dashboard data
        dashboard = user_data_service.get_user_dashboard(user.user_id)
        print(f"\n使用统计:")
        print(f"  保存的联系人: {len(dashboard.get('contacts', []))}")
        print(f"  生成的邮件: {len(dashboard.get('emails', []))}")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(
        description="Connact.ai 管理员工具 - 手动管理用户 Apollo Credits",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 查看用户当前 credits
  python admin_credits.py view user@example.com
  
  # 给用户添加 10 个 credits
  python admin_credits.py add user@example.com 10
  
  # 列出所有用户
  python admin_credits.py list
  
  # 查看用户详细信息
  python admin_credits.py info user@example.com
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='操作命令')
    
    # view command
    parser_view = subparsers.add_parser('view', help='查看用户当前 credits')
    parser_view.add_argument('email', help='用户邮箱')
    
    # add command
    parser_add = subparsers.add_parser('add', help='给用户添加 credits')
    parser_add.add_argument('email', help='用户邮箱')
    parser_add.add_argument('amount', type=int, help='要添加的 credits 数量')
    
    # list command
    parser_list = subparsers.add_parser('list', help='列出所有用户的 credits')
    
    # info command
    parser_info = subparsers.add_parser('info', help='查看用户详细信息')
    parser_info.add_argument('email', help='用户邮箱')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    print("=" * 90)
    print("🔧 Connact.ai 管理员工具 - Credits 管理")
    print("=" * 90)
    
    if args.command == 'view':
        view_user_credits(args.email)
    elif args.command == 'add':
        add_user_credits(args.email, args.amount)
    elif args.command == 'list':
        list_all_users()
    elif args.command == 'info':
        show_user_info(args.email)
    
    print("\n" + "=" * 90)
    return 0


if __name__ == '__main__':
    sys.exit(main())
