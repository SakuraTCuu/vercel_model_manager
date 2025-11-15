import { NextRequest, NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

function xorStrWithInt(str: string, num: number) {
  const numBytes = [
    (num >> 24) & 0xff,
    (num >> 16) & 0xff,
    (num >> 8) & 0xff,
    num & 0xff,
  ];
  return Buffer.from(
    str.split('').map((c, i) => c.charCodeAt(0) ^ numBytes[i % 4])
  ).toString('base64');
}

export async function POST(req: NextRequest) {
  const { key, mac, cpu } = await req.json();
  const ip = req.headers.get('x-forwarded-for') || req.headers.get('x-real-ip') || '';
  const now = new Date();
  let status = 'normal';
  let message = '';

  // 统一返回格式
  const formatResponse = (code: number, msg: string, id?: string, timestamp?: number) => {
    const response: any = {
      code,
      msg,
      id: id || '',
    };
    if (timestamp !== undefined) {
      response.timestamp = timestamp;
    }
    return NextResponse.json(response);
  };

  // 检查参数
  if (!key || !mac || !cpu) {
    // 记录缺少参数的日志
    await prisma.apiKeyRequestLog.create({
      data: {
        apiKeyId: null,
        key: key || 'unknown',
        mac: mac || 'unknown',
        cpu: cpu || 'unknown',
        ip,
        timestamp: now,
        status: 'exception',
        message: '缺少参数',
      },
    });
    return formatResponse(0, '缺少参数');
  }

  // 查询API Key
  const apiKey = await prisma.apiKey.findUnique({ where: { key }, include: { model: true } });
  
  // 检查model_id是否存在
  if (!apiKey) {
    // 记录未知model_id的日志
    await prisma.apiKeyRequestLog.create({
      data: {
        apiKeyId: null,
        key: key,
        mac,
        cpu,
        ip,
        timestamp: now,
        status: 'exception',
        message: '未知的model_id',
      },
    });
    return formatResponse(0, '未知的model_id');
  }

  // 检查API Key状态
  if (!apiKey.status) {
    status = 'exception';
    message = '已停用的key';
    // 记录日志
    await prisma.apiKeyRequestLog.create({
      data: {
        apiKeyId: apiKey.id,
        key: apiKey.key,
        mac,
        cpu,
        ip,
        timestamp: now,
        status,
        message,
      },
    });
    return formatResponse(0, '已停用的key');
  }

  // 检查 mac 是否变更
  let macChanged = false;
  let isWhitelist = false;
  if (!apiKey.mac) {
    // 首次绑定
    await prisma.apiKey.update({
      where: { key },
      data: { mac }
    });
  } else if (apiKey.mac !== mac) {
    // 检查白名单
    const whitelist = await prisma.apiKeyWhitelist.findFirst({ where: { apiKeyId: apiKey.id } });
    if (whitelist) {
      isWhitelist = true;
    } else {
      status = 'exception';
      message = 'MAC变更';
      macChanged = true;
    }
  }

  // 写入请求日志
  await prisma.apiKeyRequestLog.create({
    data: {
      apiKeyId: apiKey.id,
      key: apiKey.key,
      mac,
      cpu,
      ip,
      timestamp: now,
      status: status === 'exception' ? status : 'normal',
      message: message || '请求成功',
    },
  });

  // 更新 apiKey 表
  await prisma.apiKey.update({
    where: { key },
    data: {
      requestCount: apiKey.requestCount + 1,
      lastRequest: now.toISOString(),
      mac, // 记录最后一次请求的mac
    },
  });

  // 异常情况直接返回（白名单用户不拦截）
  if (status === 'exception' && !isWhitelist) {
    return formatResponse(0, 'MAC变更');
  }

  // 检查模型是否存在解密密钥
  if (!apiKey.model?.decryptSecret) {
    status = 'exception';
    message = '模型解密密钥未配置';
    // 记录日志
    await prisma.apiKeyRequestLog.create({
      data: {
        apiKeyId: apiKey.id,
        key: apiKey.key,
        mac,
        cpu,
        ip,
        timestamp: now,
        status,
        message,
      },
    });
    return formatResponse(0, '模型解密密钥未配置');
  }

  // 生成时间戳和异或结果（用模型的解密密钥）
  const timestamp = Math.floor(Date.now() / 1000); // 秒级时间戳
  const secret = apiKey.model.decryptSecret;
  const xorResult = xorStrWithInt(secret, timestamp);

  // 成功返回
  return formatResponse(1, 'ok', xorResult, timestamp);
} 