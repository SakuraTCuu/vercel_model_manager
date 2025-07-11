import { NextRequest, NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

// 查询白名单（分页）
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const page = parseInt(searchParams.get('page') || '1', 10);
  const pageSize = parseInt(searchParams.get('pageSize') || '10', 10);
  const [total, data] = await Promise.all([
    prisma.apiKeyWhitelist.count(),
    prisma.apiKeyWhitelist.findMany({
      orderBy: { createdAt: 'desc' },
      skip: (page - 1) * pageSize,
      take: pageSize,
      include: { apiKey: true },
    }),
  ]);
  const list = data.map((item: any) => ({
    id: item.id,
    key: item.apiKey.key,
    buyer: item.apiKey.buyer,
    remark: item.remark,
    createdAt: item.createdAt,
  }));
  return NextResponse.json({ total, data: list });
}

// 新增白名单
export async function POST(req: NextRequest) {
  const { apiKeyId, remark } = await req.json();
  if (!apiKeyId) return NextResponse.json({ error: '缺少 apiKeyId' }, { status: 400 });
  const exists = await prisma.apiKeyWhitelist.findFirst({ where: { apiKeyId } });
  if (exists) return NextResponse.json({ error: '已在白名单' }, { status: 400 });
  const item = await prisma.apiKeyWhitelist.create({ data: { apiKeyId, remark } });
  return NextResponse.json(item);
}

// 删除白名单
export async function DELETE(req: NextRequest) {
  const { id } = await req.json();
  if (!id) return NextResponse.json({ error: '缺少 id' }, { status: 400 });
  await prisma.apiKeyWhitelist.delete({ where: { id } });
  return NextResponse.json({ success: true });
}

// 修改备注
export async function PATCH(req: NextRequest) {
  const { id, remark } = await req.json();
  if (!id) return NextResponse.json({ error: '缺少 id' }, { status: 400 });
  const item = await prisma.apiKeyWhitelist.update({ where: { id }, data: { remark } });
  return NextResponse.json(item);
} 