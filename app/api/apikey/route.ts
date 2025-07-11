import { NextRequest, NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

// 获取所有 API Key（分页可选）
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const page = parseInt(searchParams.get('page') || '1', 10);
  const pageSize = parseInt(searchParams.get('pageSize') || '10', 10);

  const [total, data] = await Promise.all([
    prisma.apiKey.count(),
    prisma.apiKey.findMany({
      orderBy: { lastRequest: 'desc' },
      skip: (page - 1) * pageSize,
      take: pageSize,
    }),
  ]);
  return NextResponse.json({ total, data });
}

// 新增 API Key
export async function POST(req: NextRequest) {
  const body = await req.json();
  // 只用 modelId，不用 model
  const item = await prisma.apiKey.create({ data: body });
  return NextResponse.json(item);
}

// 删除 API Key
export async function DELETE(req: NextRequest) {
  const { id } = await req.json();
  await prisma.apiKey.delete({ where: { id } });
  return NextResponse.json({ success: true });
}

// 更新 API Key（如激活/停用、更新请求次数等）
export async function PATCH(req: NextRequest) {
  const { id, ...data } = await req.json();
  const item = await prisma.apiKey.update({
    where: { id },
    data,
  });
  return NextResponse.json(item);
}
