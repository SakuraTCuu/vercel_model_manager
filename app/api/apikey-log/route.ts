import { NextRequest, NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const page = Math.max(1, parseInt(searchParams.get('page') || '1', 10));
    const pageSize = Math.max(1, Math.min(100, parseInt(searchParams.get('pageSize') || '10', 10)));

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
      const isWhitelist = !!(item.apiKey && item.apiKey.whitelists && item.apiKey.whitelists.length > 0);
      const ts = item?.timestamp instanceof Date ? item.timestamp : (item?.timestamp ? new Date(item.timestamp) : null);
      const time = ts ? ts.toISOString().replace('T', ' ').slice(0, 19) : '-';
      return {
        id: item.id,
        key: item.key || (item.apiKey ? item.apiKey.key : 'unknown'),
        mac: item.mac || '-',
        cpu: item.cpu || '-',
        ip: item.ip || '-',
        time,
        status: item.status === 'exception' ? '异常' : '正常',
        error: item.status === 'exception'
          ? `${item.message || '异常'}${isWhitelist ? '（白名单）' : ''}`
          : '',
      };
    });

    return NextResponse.json({ total, data: logs });
  } catch (err: any) {
    // 统一兜底，避免 500 无信息；前端仍然能看到错误提示
    return NextResponse.json({ total: 0, data: [], error: err?.message || 'Unknown error' }, { status: 500 });
  }
}