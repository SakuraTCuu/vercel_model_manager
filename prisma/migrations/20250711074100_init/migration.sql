-- CreateTable
CREATE TABLE "ApiKey" (
    "id" SERIAL NOT NULL,
    "buyer" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "platform" TEXT NOT NULL,
    "amount" TEXT NOT NULL,
    "mac" TEXT NOT NULL,
    "lastRequest" TEXT NOT NULL,
    "requestCount" INTEGER NOT NULL,
    "ip" TEXT NOT NULL,
    "status" BOOLEAN NOT NULL,
    "remark" TEXT,
    "key" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ApiKey_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "ApiKey_key_key" ON "ApiKey"("key");
