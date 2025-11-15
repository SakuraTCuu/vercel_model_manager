/*
  Clear test data script for Prisma (PostgreSQL)

  Bulk cleanup (PowerShell):
    # 仅清日志
    node scripts/clear-test-data.js --mode=logs --yes

    # 清除日志+白名单+API Keys（保留模型）【默认】
    node scripts/clear-test-data.js --mode=keys --yes

    # 全量清除（包含模型）需要明确确认
    node scripts/clear-test-data.js --mode=all --include-models --yes

    # 预览要删除的数据量（不执行）
    node scripts/clear-test-data.js --mode=keys --dry-run

  Single-row deletion (PowerShell):
    # 按表+ID 删除一条（支持表: ApiKeyRequestLog | ApiKeyWhitelist | ApiKey | Model）
    node scripts/clear-test-data.js --table=ApiKey --id=123 --yes

    # 针对 ApiKey 也支持按 key 精确删除
    node scripts/clear-test-data.js --table=ApiKey --key=YOUR_32_CHAR_KEY --yes

  Notes:
  - 默认批量模式为 keys（更安全）。
  - 按条删除时，先删依赖方（如日志、白名单）再删主记录（ApiKey/Model），以避免外键约束错误。
  - 生产环境请务必先备份数据库，并确保 DATABASE_URL 指向正确环境。
*/

const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();

function parseArgs() {
  const args = process.argv.slice(2);
  const out = {
    mode: 'keys', // logs | keys | all
    yes: false,
    dryRun: false,
    includeModels: false,
    table: null, // ApiKeyRequestLog | ApiKeyWhitelist | ApiKey | Model
    id: null,
    key: null,
  };
  for (const a of args) {
    if (a.startsWith('--mode=')) out.mode = a.split('=')[1];
    if (a === '--yes' || a === '--force') out.yes = true;
    if (a === '--dry-run') out.dryRun = true;
    if (a === '--include-models') out.includeModels = true;
    if (a.startsWith('--table=')) out.table = a.split('=')[1];
    if (a.startsWith('--id=')) out.id = a.split('=')[1];
    if (a.startsWith('--key=')) out.key = a.split('=')[1];
  }
  return out;
}

async function countAll() {
  const counts = {
    ApiKeyRequestLog: await prisma.apiKeyRequestLog.count(),
    ApiKeyWhitelist: await prisma.apiKeyWhitelist.count(),
    ApiKey: await prisma.apiKey.count(),
    Model: await prisma.model.count(),
    AdminUser: await prisma.adminUser.count(),
  };
  return counts;
}

async function clearLogs() {
  const n = await prisma.apiKeyRequestLog.deleteMany({});
  return n.count;
}

async function clearWhitelists() {
  const n = await prisma.apiKeyWhitelist.deleteMany({});
  return n.count;
}

async function clearApiKeys() {
  const n = await prisma.apiKey.deleteMany({});
  return n.count;
}

async function clearModels() {
  const n = await prisma.model.deleteMany({});
  return n.count;
}

function banner(text) {
  console.log('\n' + '='.repeat(64));
  console.log(text);
  console.log('='.repeat(64));
}

function normalizeTableName(name) {
  const allow = ['ApiKeyRequestLog', 'ApiKeyWhitelist', 'ApiKey', 'Model'];
  if (!name) return null;
  const m = allow.find(t => t.toLowerCase() === String(name).toLowerCase());
  return m || null;
}

function getClientByTable(table) {
  switch (table) {
    case 'ApiKeyRequestLog': return prisma.apiKeyRequestLog;
    case 'ApiKeyWhitelist': return prisma.apiKeyWhitelist;
    case 'ApiKey': return prisma.apiKey;
    case 'Model': return prisma.model;
    default: return null;
  }
}

async function deleteSingleRow({ table, id, key, dryRun }) {
  const norm = normalizeTableName(table);
  if (!norm) {
    console.error(`\nERROR: Unknown --table=${table}. Use ApiKeyRequestLog | ApiKeyWhitelist | ApiKey | Model`);
    process.exit(1);
  }
  const client = getClientByTable(norm);
  if (!client) {
    console.error(`\nERROR: No Prisma client for table: ${norm}`);
    process.exit(1);
  }

  let where = null;
  if (id) {
    const n = Number(id);
    if (!Number.isFinite(n)) {
      console.error(`\nERROR: --id must be a number.`);
      process.exit(1);
    }
    where = { id: n };
  } else if (key && norm === 'ApiKey') {
    where = { key };
  } else {
    console.error(`\nERROR: For table=${norm}, provide --id; For ApiKey you may also use --key.`);
    process.exit(1);
  }

  // Show the row before deletion
  let found = null;
  try {
    // prefer findUnique; if key is unique or id is PK
    found = await client.findUnique({ where });
    if (!found && norm === 'ApiKeyRequestLog' && where.id) {
      // fallback to findFirst in case schema differs
      found = await client.findFirst({ where: { id: where.id } });
    }
  } catch (e) {
    console.error(`\nERROR: Query failed for ${norm}:`, e);
    process.exit(1);
  }

  if (!found) {
    console.log(`\nNo row found in ${norm} matching where=${JSON.stringify(where)}`);
    return { deleted: 0 };
  }

  console.log(`\nAbout to delete from ${norm}:`);
  console.dir(found, { depth: 2 });

  if (dryRun) {
    console.log('\nDry run only. Nothing will be deleted.');
    return { deleted: 0 };
  }

  try {
    await client.delete({ where });
    return { deleted: 1 };
  } catch (e) {
    console.error(`\nERROR: Delete failed. You may need to delete dependent rows first (logs/whitelists, etc.).`, e);
    process.exit(1);
  }
}

(async () => {
  const { mode, yes, dryRun, includeModels, table, id, key } = parseArgs();

  banner('Prisma test data cleanup');
  console.log(`Mode: ${mode}`);
  console.log(`Dry run: ${dryRun ? 'YES' : 'NO'}`);
  console.log(`Include models: ${includeModels ? 'YES' : 'NO'}`);

  // Single-row deletion path
  if (table) {
    banner('Single-row delete mode');
    console.log(`Table: ${table}`);
    if (id) console.log(`ID: ${id}`);
    if (key) console.log(`Key: ${key}`);
    console.log(`Dry run: ${dryRun ? 'YES' : 'NO'}`);

    if (!dryRun && !yes) {
      console.error('\nERROR: Please pass --yes to confirm deletion.');
      await prisma.$disconnect();
      process.exit(1);
    }

    const result = await deleteSingleRow({ table, id, key, dryRun });
    console.log(`\nDeleted rows: ${result.deleted}`);

    await prisma.$disconnect();
    process.exit(0);
  }

  const before = await countAll();
  console.log('\nCurrent counts:');
  console.table(before);

  if (dryRun) {
    console.log('\nDry run only. Nothing will be deleted.');
    await prisma.$disconnect();
    process.exit(0);
  }

  // Safety confirmations
  if (!yes) {
    console.error('\nERROR: Please pass --yes to confirm deletion.');
    await prisma.$disconnect();
    process.exit(1);
  }

  if (mode === 'all' && !includeModels) {
    console.error('\nERROR: Mode=all requires --include-models to also delete models.');
    await prisma.$disconnect();
    process.exit(1);
  }

  // Execute deletions in FK-safe order
  let deleted = { logs: 0, whitelists: 0, keys: 0, models: 0 };
  try {
    if (mode === 'logs') {
      deleted.logs = await clearLogs();
    } else if (mode === 'keys') {
      deleted.logs = await clearLogs();
      deleted.whitelists = await clearWhitelists();
      deleted.keys = await clearApiKeys();
    } else if (mode === 'all') {
      deleted.logs = await clearLogs();
      deleted.whitelists = await clearWhitelists();
      deleted.keys = await clearApiKeys();
      if (includeModels) {
        deleted.models = await clearModels();
      }
    } else {
      console.error(`\nERROR: Unknown mode: ${mode}. Use logs | keys | all`);
      process.exit(1);
    }
  } catch (e) {
    console.error('\nCleanup failed:', e);
    process.exit(1);
  }

  console.log('\nDeleted rows:');
  console.table(deleted);

  const after = await countAll();
  console.log('\nCounts after deletion:');
  console.table(after);

  console.log('\nDone.');
  await prisma.$disconnect();
  process.exit(0);
})();
