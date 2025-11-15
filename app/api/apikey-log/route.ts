import { NextRequest, NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const page = parseInt(searchParams.get('page') || '1', 10);
  const pageSize = parseInt(searchParams.get('pageSize') || '10', 10);

  const [total, data] = await Promise.all([
    prisma.apiKeyRequestLog.count(),
    prisma.apiKeyRequestLog.findMany({
      orderBy: { timestamp: 'desc' },
      skip: (page - 1) * pageSize,
      take: pageSize,
      include: {
        apiKey: {
          include: { whitelists: true },
        },
      },
    }),
  ]);

  // 返回 key 字段，若为白名单，异常后面加标志
  const logs = data.map((item: any) => {
    const isWhitelist = item.apiKey && item.apiKey.whitelists && item.apiKey.whitelists.length > 0;
    return {
      id: item.id,
      key: item.key || (item.apiKey ? item.apiKey.key : 'unknown'), // 优先使用key字段，如果不存在则从apiKey获取
      mac: item.mac,
      cpu: item.cpu,
      ip: item.ip,
      time: item.timestamp.toISOString().replace('T', ' ').slice(0, 19),
      status: item.status === 'exception' ? '异常' : '正常',
      error: item.status === 'exception'
        ? (item.message || '异常') + (isWhitelist ? '（白名单）' : '')
        : '',
    };
  });

  return NextResponse.json({ total, data: logs });
} 