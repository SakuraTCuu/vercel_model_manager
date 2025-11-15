import { NextRequest, NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const page = Math.max(1, parseInt(searchParams.get('page') || '1', 10));
    const pageSize = Math.max(1, Math.min(100, parseInt(searchParams.get('pageSize') || '10', 10)));
    // 新增筛选参数
    const key = (searchParams.get('key') || '').trim();
    const mac = (searchParams.get('mac') || '').trim();
    const ip = (searchParams.get('ip') || '').trim();
    const cpu = (searchParams.get('cpu') || '').trim();
    const status = (searchParams.get('status') || '').trim(); // normal | exception | warning
    const q = (searchParams.get('q') || '').trim(); // message 关键词
    const start = (searchParams.get('start') || '').trim(); // ISO或yyyy-mm-dd hh:mm:ss
    const end = (searchParams.get('end') || '').trim();

    // 构建 where 条件
    const where: any = {};
    if (key) {
      // 同时支持匹配记录表中的 key 或 apiKey.key
      where.OR = [
        { key: { contains: key } },
        { apiKey: { key: { contains: key } } as any },
      ];
    }
    if (mac) where.mac = { contains: mac };
    if (ip) where.ip = { contains: ip };
    if (cpu) where.cpu = { contains: cpu };
    if (status) where.status = status; // 前端传原始值
    if (q) where.message = { contains: q };
    if (start || end) {
      const gte = start ? new Date(start) : undefined;
      const lte = end ? new Date(end) : undefined;
      where.timestamp = {
        ...(gte ? { gte } : {}),
        ...(lte ? { lte } : {}),
      };
    }

    const [total, data] = await Promise.all([
      prisma.apiKeyRequestLog.count({ where }),
      prisma.apiKeyRequestLog.findMany({
        where,
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
      const mapped = {
        id: item.id,
        key: item.key || (item.apiKey ? item.apiKey.key : 'unknown'),
        mac: item.mac || '-',
        cpu: item.cpu || '-',
        ip: item.ip || '-',
        time,
        // 更细分：exception=异常, warning=警告, 其他=正常
        status: item.status === 'exception' ? '异常' : (item.status === 'warning' ? '警告' : '正常'),
        error: item.status === 'exception'
          ? `${item.message || '异常'}${isWhitelist ? '（白名单）' : ''}`
          : '',
      };
      return mapped;
    });

    return NextResponse.json({ total, data: logs });
  } catch (err: any) {
    // 统一兜底，避免 500 无信息；前端仍然能看到错误提示
    return NextResponse.json({ total: 0, data: [], error: err?.message || 'Unknown error' }, { status: 500 });
  }
}