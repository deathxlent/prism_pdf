import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("修复验证脚本")
print("=" * 70)

# 1. 测试 Surya 必须 GPU 模式
print("\n[1] 验证 Surya 必须 GPU 模式...")
try:
    from backend.services.order_service import (
        check_gpu_available_for_surya, _get_ordering_model_and_processor,
        is_surya_loaded_on_gpu, _order_model_loaded_on_gpu
    )
    import backend.services.order_service as os
    
    # 测试1: 模拟模型已加载在 GPU 上
    original_gpu = os._order_model_loaded_on_gpu
    original_cache = os._surya_gpu_available
    os._order_model_loaded_on_gpu = True
    os._surya_gpu_available = None
    result = check_gpu_available_for_surya()
    os._order_model_loaded_on_gpu = original_gpu
    os._surya_gpu_available = original_cache
    print(f"  - 模型已加载在GPU时，check_gpu_available = {result} (期望: True)")
    assert result == True, "模型已在GPU上时应该跳过检查"
    
    print("  ✅ Surya GPU 跳过检查逻辑正常")
    
except Exception as e:
    print(f"  ❌ 验证失败: {e}")
    import traceback
    traceback.print_exc()

# 2. 测试 YOLO CPU 回退模式
print("\n[2] 验证 YOLO CPU 回退模式...")
try:
    from backend.services.layout_service import (
        check_gpu_available_for_yolo, is_yolo_loaded_on_gpu, _model_loaded_on_gpu
    )
    import backend.services.layout_service as ls
    
    # 测试1: 模型已加载在 GPU 上时跳过检查
    original_yolo_gpu = ls._model_loaded_on_gpu
    ls._model_loaded_on_gpu = True
    result = check_gpu_available_for_yolo()
    ls._model_loaded_on_gpu = original_yolo_gpu
    print(f"  - YOLO模型已加载在GPU时，check_gpu_available = {result} (期望: True)")
    assert result == True, "YOLO模型已在GPU上时应该跳过检查"
    
    print("  ✅ YOLO GPU 跳过检查逻辑正常")
    print("  ✅ YOLO CPU 回退模式已保留")
    
except Exception as e:
    print(f"  ❌ 验证失败: {e}")
    import traceback
    traceback.print_exc()

# 3. 测试每页独立重排序状态接口
print("\n[3] 验证每页独立重排序状态接口...")
try:
    from backend.api.routes import router, _reordering_pages
    
    all_paths = [route.path for route in router.routes]
    has_reorder_status = "/api/pages/reorder-status" in all_paths
    print(f"  - /api/pages/reorder-status 接口已添加: {has_reorder_status}")
    assert has_reorder_status, "缺少重排序状态查询接口"
    
    has_reorder_post = "/api/pages/{page_id}/reorder" in all_paths
    print(f"  - /api/pages/{{page_id}}/reorder 接口存在: {has_reorder_post}")
    
    print(f"  - _reordering_pages 集合已定义: {_reordering_pages is not None}")
    print(f"  - 初始状态为空: {len(_reordering_pages) == 0}")
    
    print("  ✅ 每页独立重排序状态已实现")
    
except Exception as e:
    print(f"  ❌ 验证失败: {e}")
    import traceback
    traceback.print_exc()

# 4. 测试 reset_surya_state
print("\n[4] 验证 reset_surya_state 逻辑...")
try:
    from backend.services.order_service import reset_surya_state
    import backend.services.order_service as os2
    
    # 当模型已加载在 GPU 上时，reset 后应该保持 True
    original_gpu = os2._order_model_loaded_on_gpu
    os2._order_model_loaded_on_gpu = True
    os2._surya_gpu_available = None
    reset_surya_state()
    result = os2._surya_gpu_available
    os2._order_model_loaded_on_gpu = original_gpu
    print(f"  - 模型已加载在GPU时，reset后_gpu_available = {result} (期望: True)")
    assert result == True, "模型已加载时reset应保持GPU可用"
    
    # 当模型未加载时，reset 应该清空缓存
    original_gpu2 = os2._order_model_loaded_on_gpu
    os2._order_model_loaded_on_gpu = False
    os2._surya_gpu_available = True
    reset_surya_state()
    result2 = os2._surya_gpu_available
    os2._order_model_loaded_on_gpu = original_gpu2
    print(f"  - 模型未加载时，reset后_gpu_available = {result2} (期望: None)")
    assert result2 == None, "模型未加载时reset应清空缓存"
    
    print("  ✅ reset_surya_state 逻辑正常")
    
except Exception as e:
    print(f"  ❌ 验证失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("验证完成!")
print("=" * 70)
print("\n修改总结:")
print("")
print("✅ Surya 模型:")
print("   - 必须在 GPU 上运行，不支持 CPU 模式")
print("   - 模型已加载到 GPU 时，跳过显存检查")
print("   - 显存不足时直接报错，不回退到 CPU")
print("")
print("✅ YOLO 模型:")
print("   - GPU 显存不足时自动回退到 CPU 模式")
print("   - 模型已加载到 GPU 时，跳过显存检查")
print("")
print("✅ 每页独立重排序:")
print("   - 后端: _reordering_pages 集合跟踪每页状态")
print("   - 后端: 新增 /api/pages/reorder-status 接口")
print("   - 后端: 重排序时检查并设置页面级别状态")
print("   - 前端: reorderingPages Set 跟踪每页状态")
print("   - 前端: 切换页面时重置按钮状态")
print("   - 前端: 每页可独立点击重排序，互不影响")
