#!/usr/bin/env python3
"""
企业微信错误通知测试脚本

使用方法：
1. 设置环境变量 WECHAT_WEBHOOK_URL
2. 运行: python test_wechat_notification.py

或者直接指定 webhook URL：
python test_wechat_notification.py YOUR_WEBHOOK_URL
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.services.error_notifier import error_notifier


def test_info_notification():
    """测试普通信息推送"""
    print("📤 测试普通信息推送...")
    success = error_notifier.notify_info(
        "✅ Connact.ai 企业微信通知测试\n\n"
        "如果你看到这条消息，说明配置成功！"
    )
    if success:
        print("✅ 信息推送成功！请检查企业微信群消息")
    else:
        print("❌ 信息推送失败，请检查配置")
    return success


def test_error_notification():
    """测试错误通知推送"""
    print("\n📤 测试错误通知推送...")
    
    # 模拟一个错误
    try:
        # 故意触发一个错误
        x = 1 / 0
    except Exception as e:
        from src.services.error_notifier import notify_error
        
        success = notify_error(
            e,
            context={
                "test_type": "error_notification_test",
                "method": "POST",
                "user_agent": "test_script"
            },
            user_id="test_user_123",
            request_path="/test/error"
        )
        
        if success:
            print("✅ 错误通知推送成功！请检查企业微信群消息")
        else:
            print("❌ 错误通知推送失败，请检查配置")
        
        return success


def test_complex_error():
    """测试复杂错误场景"""
    print("\n📤 测试复杂错误场景...")
    
    def nested_function_1():
        nested_function_2()
    
    def nested_function_2():
        nested_function_3()
    
    def nested_function_3():
        raise ValueError("这是一个嵌套函数调用链中的错误，用于测试完整的堆栈跟踪")
    
    try:
        nested_function_1()
    except Exception as e:
        from src.services.error_notifier import notify_error
        
        success = notify_error(
            e,
            context={
                "test_type": "complex_error_test",
                "nested_level": 3,
                "description": "测试深层嵌套调用的错误报告"
            },
            user_id="test_admin",
            request_path="/api/generate-email"
        )
        
        if success:
            print("✅ 复杂错误通知推送成功！")
        else:
            print("❌ 复杂错误通知推送失败")
        
        return success


def main():
    """主测试函数"""
    print("=" * 60)
    print("🧪 企业微信错误通知系统测试")
    print("=" * 60)
    
    # 检查配置
    webhook_url = None
    if len(sys.argv) > 1:
        webhook_url = sys.argv[1]
        os.environ["WECHAT_WEBHOOK_URL"] = webhook_url
        print(f"\n使用命令行参数提供的 webhook URL")
    else:
        webhook_url = os.environ.get("WECHAT_WEBHOOK_URL", "")
    
    if not webhook_url:
        print("\n❌ 错误：未设置 WECHAT_WEBHOOK_URL 环境变量")
        print("\n请先设置环境变量：")
        print("  export WECHAT_WEBHOOK_URL='https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY'")
        print("\n或者在命令行直接提供：")
        print("  python test_wechat_notification.py 'YOUR_WEBHOOK_URL'")
        return 1
    
    print(f"\n✅ Webhook URL 已配置")
    print(f"   {webhook_url[:50]}..." if len(webhook_url) > 50 else f"   {webhook_url}")
    
    # 运行测试
    results = []
    
    # 测试 1：普通信息
    results.append(("普通信息推送", test_info_notification()))
    
    # 测试 2：简单错误
    results.append(("简单错误通知", test_error_notification()))
    
    # 测试 3：复杂错误
    results.append(("复杂错误通知", test_complex_error()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{status}  {test_name}")
    
    total = len(results)
    passed = sum(1 for _, success in results if success)
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！企业微信通知系统配置正确。")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查配置。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
