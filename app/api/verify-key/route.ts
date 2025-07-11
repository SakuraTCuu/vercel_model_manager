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

  // 检查参数
  if (!key || !mac || !cpu) {
    status = 'exception';
    message = '缺少参数';
    // 日志写入（无 key 时无法查 apiKeyId）
    return NextResponse.json({ error: message }, { status: 400 });
  }
  const apiKey = await prisma.apiKey.findUnique({ where: { key }, include: { model: true } });
  if (!apiKey || !apiKey.status) {
    status = 'exception';
    message = '无效或已停用的key';
    // 日志写入（无效 key）
    if (apiKey) {
      await prisma.apiKeyRequestLog.create({
        data: {
          apiKeyId: apiKey.id,
          mac,
          cpu,
          ip,
          timestamp: now,
          status,
          message,
        },
      });
    }
    return NextResponse.json({ error: message }, { status: 401 });
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
      message = 'MAC 变更';
      macChanged = true;
    }
  }

  // 写入请求日志
  await prisma.apiKeyRequestLog.create({
    data: {
      apiKeyId: apiKey.id,
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
    return NextResponse.json({ error: message }, { status: 403 });
  }

  // 生成时间戳和异或结果（用模型的解密密钥）
  const timestamp = Math.floor(Date.now() / 1000); // 秒级时间戳
  const secret = apiKey.model?.decryptSecret || '';
  const xorResult = xorStrWithInt(secret, timestamp);

  return NextResponse.json({
    xorResult,
    timestamp,
    success: true,
  });
} 