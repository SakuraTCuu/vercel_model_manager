/*
  Warnings:

  - You are about to drop the column `model` on the `ApiKey` table. All the data in the column will be lost.
  - Added the required column `modelId` to the `ApiKey` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "ApiKey" DROP COLUMN "model",
ADD COLUMN     "modelId" INTEGER NOT NULL;

-- CreateTable
CREATE TABLE "Model" (
    "id" SERIAL NOT NULL,
    "name" TEXT NOT NULL,
    "label" TEXT NOT NULL,
    "platform" TEXT NOT NULL,
    "price" TEXT NOT NULL,
    "decryptSecret" TEXT NOT NULL,
    "size" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "description" TEXT,

    CONSTRAINT "Model_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ApiKeyRequestLog" (
    "id" SERIAL NOT NULL,
    "apiKeyId" INTEGER NOT NULL,
    "mac" TEXT NOT NULL,
    "cpu" TEXT NOT NULL,
    "ip" TEXT NOT NULL,
    "timestamp" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "status" TEXT NOT NULL,
    "message" TEXT,

    CONSTRAINT "ApiKeyRequestLog_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "Model_name_key" ON "Model"("name");

-- AddForeignKey
ALTER TABLE "ApiKey" ADD CONSTRAINT "ApiKey_modelId_fkey" FOREIGN KEY ("modelId") REFERENCES "Model"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ApiKeyRequestLog" ADD CONSTRAINT "ApiKeyRequestLog_apiKeyId_fkey" FOREIGN KEY ("apiKeyId") REFERENCES "ApiKey"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
