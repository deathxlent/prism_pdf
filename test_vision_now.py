import sys
from pathlib import Path
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
sys.path.insert(0, str(Path(__file__).parent))
from backend.services.llm_service import describe_image

image_path = r"G:\ws\Prism PDF\tmp\ae3365ca461941228d683de19c0e3e31\output\picture_3660001.png"

print("=" * 70)
print(f"测试 Vision 图片描述 (超时时间: 3600 秒 = 60 分钟)")
print(f"图片: {image_path}")
print(f"存在: {Path(image_path).exists()}")
print("开始处理，请耐心等待...")
print("=" * 70)

try:
    result = describe_image(image_path)
    print("\n" + "=" * 70)
    print(f"✓ 成功! 描述长度: {len(result)} 字符")
    print("=" * 70)
    print(result)
except Exception as e:
    print(f"\n❌ 失败: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
