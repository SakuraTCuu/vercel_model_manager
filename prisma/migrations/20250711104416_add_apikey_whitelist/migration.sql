-- CreateTable
CREATE TABLE "ApiKeyWhitelist" (
    "id" SERIAL NOT NULL,
    "apiKeyId" INTEGER NOT NULL,
    "remark" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ApiKeyWhitelist_pkey" PRIMARY KEY ("id")
);

-- AddForeignKey
ALTER TABLE "ApiKeyWhitelist" ADD CONSTRAINT "ApiKeyWhitelist_apiKeyId_fkey" FOREIGN KEY ("apiKeyId") REFERENCES "ApiKey"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
