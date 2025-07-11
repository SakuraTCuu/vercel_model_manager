import { NextRequest, NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

// 获取模型列表
export async function GET(req: NextRequest) {
  const models = await prisma.model.findMany({ orderBy: { createdAt: 'desc' } });
  return NextResponse.json(models);
}

// 新增模型
export async function POST(req: NextRequest) {
  const body = await req.json();
  const model = await prisma.model.create({ data: body });
  return NextResponse.json(model);
}

// 编辑模型
export async function PATCH(req: NextRequest) {
  const { id, ...data } = await req.json();
  const model = await prisma.model.update({ where: { id }, data });
  return NextResponse.json(model);
}

// 删除模型
export async function DELETE(req: NextRequest) {
  const { id } = await req.json();
  await prisma.model.delete({ where: { id } });
  return NextResponse.json({ success: true });
} 