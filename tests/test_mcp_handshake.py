import subprocess, json, sys

def test_mcp(name, script_path, expected_count):
    p = subprocess.Popen(
        [sys.executable, script_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8'
    )
    # 1. Initialize
    init_req = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'test-client', 'version': '1.0'}
        }
    }
    p.stdin.write(json.dumps(init_req) + '\n')
    p.stdin.flush()
    line = p.stdout.readline()
    init_res = json.loads(line)
    assert 'result' in init_res, f'Init failed: {init_res}'

    # 2. Initialized notification
    notif = {'jsonrpc': '2.0', 'method': 'notifications/initialized', 'params': {}}
    p.stdin.write(json.dumps(notif) + '\n')
    p.stdin.flush()

    # 3. List tools
    tools_req = {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}}
    p.stdin.write(json.dumps(tools_req) + '\n')
    p.stdin.flush()
    line = p.stdout.readline()
    tools_res = json.loads(line)
    tools = tools_res['result']['tools']
    print(f'{name}: {len(tools)} tools visible (expected {expected_count})')
    for t in tools:
        print(f"  - {t['name']}")
    assert len(tools) == expected_count, f'Expected {expected_count} tools, got {len(tools)}'

    p.stdin.close()
    p.terminate()

if __name__ == '__main__':
    test_mcp('x-context-intelligence', r'C:\Users\Admin\marketing-ai-system\x-context-intelligence\mcp\server.py', 10)
    test_mcp('x-video-intelligence', r'C:\Users\Admin\marketing-ai-system\x-video-intelligence\mcp\server.py', 8)
    print('ALL MCP HANDSHAKES AND TOOL DISCOVERIES PASSED PERFECTLY!')
