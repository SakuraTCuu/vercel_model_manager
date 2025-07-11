# -*- coding: utf-8 -*-
import uuid
import platform
import subprocess
import urllib.request
import json
import base64

def get_mac():
    return ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff)
                     for ele in range(40, -1, -8)])

def get_cpu():
    try:
        cpu = platform.processor()
        if cpu:
            return cpu
    except:
        pass
    # 尝试获取CPU序列号
    try:
        if platform.system() == 'Windows':
            return subprocess.check_output('wmic cpu get ProcessorId', shell=True).decode().split('\n')[1].strip()
        elif platform.system() == 'Linux':
            return subprocess.check_output("cat /proc/cpuinfo | grep Serial | awk '{print $3}'", shell=True).decode().strip()
    except:
        pass
    return ''

def xor_str_with_int_base64(xor_result_b64, timestamp):
    xor_bytes = base64.b64decode(xor_result_b64)
    num_bytes = [
        (timestamp >> 24) & 0xff,
        (timestamp >> 16) & 0xff,
        (timestamp >> 8) & 0xff,
        timestamp & 0xff,
    ]
    secret = ''.join(
        chr(b ^ num_bytes[i % 4]) for i, b in enumerate(xor_bytes)
    )
    return secret

if __name__ == '__main__':
    key = input('请输入API Key: ').strip()
    mac = get_mac()
    cpu = get_cpu()
    print('MAC: {}'.format(mac))
    print('CPU: {}'.format(cpu))
    url = 'http://localhost:3000/api/verify-key'  # 修改为你的后端地址
    data = json.dumps({'key': key, 'mac': mac, 'cpu': cpu}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as resp:
            resp_data = resp.read().decode('utf-8')
            result = json.loads(resp_data)
            print('后端返回:', result)
            if result.get('success'):
                secret = xor_str_with_int_base64(result['xorResult'], result['timestamp'])
                print('解密密钥:', secret)
            else:
                print('校验失败')
    except Exception as e:
        print('请求失败:', e) 