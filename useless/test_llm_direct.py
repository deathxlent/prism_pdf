import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.services.llm_service import (
    _get_active_llm, _encode_image_file, _build_url,
    _extract_content_from_response, describe_image, translate_text
)

def test_vision_direct():
    print("=" * 70)
    print("直接测试 Vision")
    cfg = _get_active_llm()
    if not cfg:
        print("❌ 没配置")
        return False

    image_path = r"G:\ws\Prism PDF\tmp\ae3365ca461941228d683de19c0e3e31\output\picture_2650001.png"
    if not Path(image_path).exists():
        image_path = r"G:\ws\Prism PDF\tmp\ae3365ca461941228d683de19c0e3e31\output\picture_3660001.png"

    print(f"用图片: {image_path}")
    print(f"存在: {Path(image_path).exists()}, 大小: {Path(image_path).stat().st_size}")

    try:
        result = describe_image(image_path)
        print(f"\n✓ describe_image 成功! ({len(result)} 字符)")
        print(f"结果:\n{result}")
        return True
    except Exception as e:
        print(f"❌ 失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_translate_direct():
    print("\n" + "=" * 70)
    print("直接测试翻译")
    try:
        result = translate_text("你好，今天天气不错，我们一起去公园玩吧！", "en")
        print(f"\n✓ translate_text 成功!")
        print(f"结果: {result}")
        return True
    except Exception as e:
        print(f"❌ 失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_translate_direct()
    test_vision_direct()
