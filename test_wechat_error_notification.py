#!/usr/bin/env python3
"""
测试企业微信错误通知功能

使用方法:
1. 设置环境变量 WECHAT_WEBHOOK_URL
2. 运行: python test_wechat_error_notification.py
"""

import os
import sys
from src.services.error_notifier import error_notifier


def test_basic_notification():
    """测试基础错误通知"""
    print("=" * 60)
    print("测试 1: 基础错误通知")
    print("=" * 60)
    
    if not error_notifier.enabled:
        print("❌ 企业微信通知未启用")
        print("   请设置环境变量: WECHAT_WEBHOOK_URL")
        return False
    
    try:
        # 模拟一个错误
        raise ValueError("这是一个测试错误消息")
    except Exception as e:
        success = error_notifier.notify_error(
            error=e,
            context={
                "test_type": "basic",
                "test_number": 1,
            },
            user_id="test_user_123",
            request_path="/api/test",
        )
        
        if success:
            print("✅ 基础错误通知发送成功")
            print("   请检查企业微信群查看消息")
            return True
        else:
            print("❌ 基础错误通知发送失败")
            return False


def test_api_error_simulation():
    """测试模拟 API 错误场景"""
    print("\n" + "=" * 60)
    print("测试 2: API 错误场景模拟")
    print("=" * 60)
    
    if not error_notifier.enabled:
        print("❌ 跳过 (通知未启用)")
        return False
    
    try:
        # 模拟一个 API 调用错误
        user_data = {"purpose": "test", "field": "ai"}
        raise ConnectionError("无法连接到外部 API 服务")
    except Exception as e:
        success = error_notifier.notify_error(
            error=e,
            context={
                "api_endpoint": "/api/find-recommendations",
                "user_input": user_data,
                "retry_count": 3,
            },
            user_id="user_abc_456",
            request_path="/api/find-recommendations",
        )
        
        if success:
            print("✅ API 错误通知发送成功")
            return True
        else:
            print("❌ API 错误通知发送失败")
            return False


def test_stack_trace():
    """测试包含完整堆栈跟踪的错误"""
    print("\n" + "=" * 60)
    print("测试 3: 复杂堆栈跟踪")
    print("=" * 60)
    
    if not error_notifier.enabled:
        print("❌ 跳过 (通知未启用)")
        return False
    
    def nested_function_1():
        def nested_function_2():
            def nested_function_3():
                raise RuntimeError("深层嵌套函数中的错误")
            nested_function_3()
        nested_function_2()
    
    try:
        nested_function_1()
    except Exception as e:
        success = error_notifier.notify_error(
            error=e,
            context={
                "operation": "nested_operation",
                "depth": 3,
            },
            user_id="test_user_789",
            request_path="/api/complex-operation",
        )
        
        if success:
            print("✅ 堆栈跟踪通知发送成功")
            print("   应该能看到完整的函数调用链")
            return True
        else:
            print("❌ 堆栈跟踪通知发送失败")
            return False


def test_info_notification():
    """测试信息通知（非错误）"""
    print("\n" + "=" * 60)
    print("测试 4: 信息通知")
    print("=" * 60)
    
    if not error_notifier.enabled:
        print("❌ 跳过 (通知未启用)")
        return False
    
    success = error_notifier.notify_info(
        "🎉 Connact.ai 测试通知\n" +
        "系统运行正常\n" +
        f"测试时间: {error_notifier._format_error_message.__globals__['datetime'].datetime.now()}"
    )
    
    if success:
        print("✅ 信息通知发送成功")
        return True
    else:
        print("❌ 信息通知发送失败")
        return False


def main():
    """运行所有测试"""
    print("🚀 企业微信错误通知功能测试")
    print()
    
    # 检查配置
    webhook_url = os.environ.get("WECHAT_WEBHOOK_URL", "")
    if webhook_url:
        print(f"✅ Webhook URL 已配置: {webhook_url[:30]}...")
    else:
        print("❌ 未配置 WECHAT_WEBHOOK_URL 环境变量")
        print()
        print("请按以下步骤配置:")
        print("1. 在企业微信中创建群机器人")
        print("2. 获取 Webhook URL")
        print("3. 设置环境变量:")
        print("   export WECHAT_WEBHOOK_URL='https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY'")
        print()
        print("或在代码中设置:")
        print("   from src.services.error_notifier import error_notifier")
        print("   error_notifier.webhook_url = 'YOUR_WEBHOOK_URL'")
        print("   error_notifier.enabled = True")
        sys.exit(1)
    
    print()
    
    # 运行测试
    tests = [
        test_basic_notification,
        test_api_error_simulation,
        test_stack_trace,
        test_info_notification,
    ]
    
    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"\n❌ 测试执行失败: {e}")
            results.append(False)
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"总计: {passed}/{total} 个测试通过")
    
    if passed == total:
        print("✅ 所有测试通过！企业微信通知功能正常")
        return 0
    else:
        print("⚠️  部分测试失败，请检查配置")
        return 1


if __name__ == "__main__":
    sys.exit(main())
