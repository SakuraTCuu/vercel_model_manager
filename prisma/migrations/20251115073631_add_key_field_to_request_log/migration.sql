-- DropForeignKey
ALTER TABLE "ApiKeyRequestLog" DROP CONSTRAINT "ApiKeyRequestLog_apiKeyId_fkey";

-- AlterTable
ALTER TABLE "ApiKeyRequestLog" ADD COLUMN     "key" TEXT,
ALTER COLUMN "apiKeyId" DROP NOT NULL;

-- AddForeignKey
ALTER TABLE "ApiKeyRequestLog" ADD CONSTRAINT "ApiKeyRequestLog_apiKeyId_fkey" FOREIGN KEY ("apiKeyId") REFERENCES "ApiKey"("id") ON DELETE SET NULL ON UPDATE CASCADE;
