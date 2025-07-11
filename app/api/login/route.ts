import { NextRequest, NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

export async function POST(req: NextRequest) {
  const { username, password } = await req.json();
  if (!username || !password) {
    return NextResponse.json({ error: '缺少用户名或密码' }, { status: 400 });
  }
  const user = await prisma.adminUser.findUnique({ where: { username } });
  if (!user || user.password !== password) {
    return NextResponse.json({ error: '账号或密码错误' }, { status: 401 });
  }
  return NextResponse.json({ success: true });
} 