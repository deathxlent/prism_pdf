from fastapi.testclient import TestClient
from backend.main import app
import json

client = TestClient(app)

print('=== 4. 激活 OpenAI 配置 ===')
r = client.get('/api/llm-config/openai')
configs = r.json()['configs']
config_id = None
if configs:
    config_id = configs[0]['id']
    r = client.put(f'/api/llm-config/openai/{config_id}/activate')
    print(f'激活状态: {r.status_code}')
    print(f'结果: {r.json()}')

print('\n=== 5. 获取当前活跃配置 ===')
r = client.get('/api/llm-config/active')
print(f'状态: {r.status_code}')
print(f'结果: {json.dumps(r.json(), indent=2, ensure_ascii=False)}')

print('\n=== 6. 更新配置 ===')
r = client.put(f'/api/llm-config/openai/{config_id}', json={
    'name': '我的OpenAI账号-已更新',
    'temperature': 0.5,
    'max_tokens': 8192,
    'model': 'gpt-4o-mini'
})
print(f'状态: {r.status_code}')
print(f'结果: {r.json()}')

print('\n=== 7. 检查配置文件位置 ===')
import os
from pathlib import Path
config_file = Path.cwd() / 'llm_configs.json'
if config_file.exists():
    print(f'文件存在: {config_file}, 大小: {config_file.stat().st_size} 字节')
else:
    for root, dirs, files in os.walk('.'):
        for f in files:
            if f == 'llm_configs.json':
                print(f'找到: {os.path.join(root, f)}')

print('\n=== 8. 清理测试数据（删除配置） ===')
r = client.delete(f'/api/llm-config/openai/{config_id}')
print(f'删除状态: {r.status_code}')
print(f'结果: {r.json()}')

r = client.get('/api/llm-config/deepseek')
deepseek_configs = r.json()['configs']
if deepseek_configs:
    ds_id = deepseek_configs[0]['id']
    r = client.delete(f'/api/llm-config/deepseek/{ds_id}')
    print(f'删除DeepSeek状态: {r.status_code}')
    print(f'结果: {r.json()}')
