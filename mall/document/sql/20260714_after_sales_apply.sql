ALTER TABLE `oms_order_return_apply`
    ADD COLUMN `member_id` bigint(20) NULL AFTER `id`,
    ADD COLUMN `apply_type` varchar(20) NOT NULL DEFAULT 'return' AFTER `member_id`,
    ADD COLUMN `idempotency_key` varchar(64) NULL AFTER `apply_type`;

UPDATE `oms_order_return_apply` ra
LEFT JOIN `ums_member` m ON m.username = ra.member_username
SET ra.member_id = m.id
WHERE ra.member_id IS NULL;

CREATE INDEX `idx_return_apply_member_order`
    ON `oms_order_return_apply` (`member_id`, `order_sn`);
CREATE UNIQUE INDEX `uk_return_apply_member_idempotency`
    ON `oms_order_return_apply` (`member_id`, `idempotency_key`);
