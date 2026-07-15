/*
 Agent 联调用最小 MySQL 初始化数据。

 使用方式：
 1. 先导入 mall/document/sql/mall.sql 建表和基础数据。
 2. 再执行本文件：mysql -uroot -p123456 mall < mall_agent_seed.sql

 示例账号/订单：
 - 用户：U100
 - 订单：ORD1001 已完成，可查订单、退款、提交售后
 - 订单：ORD1002 运输中，可查物流
 - 商品：SKU1001 / SKU1002
 - 售后单：9001
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DELETE FROM `oms_order_return_apply` WHERE `id` IN (9001);
DELETE FROM `oms_order_operate_history` WHERE `id` IN (10001, 10002, 10003, 10004);
DELETE FROM `oms_order_item` WHERE `id` IN (10001, 10002);
DELETE FROM `oms_order` WHERE `id` IN (1001, 1002);
DELETE FROM `ums_member` WHERE `id` = 100 OR `username` = 'U100';

INSERT INTO `ums_member`
(`id`, `member_level_id`, `username`, `password`, `nickname`, `phone`, `status`, `create_time`, `icon`, `gender`, `birthday`, `city`, `job`, `personalized_signature`, `source_type`, `integration`, `growth`, `luckey_count`, `history_integration`)
VALUES
(100, 4, 'U100', '$2a$10$Q08uzqvtPj61NnpYQZsVvOnyilJ3AU4VdngAcJFGvPhEeqhhC.hhS', '售后联调用户', '19900001000', 1, '2026-07-08 09:00:00', NULL, 0, NULL, '上海', '测试用户', 'Agent 联调用账号', 0, 0, 0, 0, 0);

INSERT INTO `oms_order`
(`id`, `member_id`, `coupon_id`, `order_sn`, `create_time`, `member_username`, `total_amount`, `pay_amount`, `freight_amount`, `promotion_amount`, `integration_amount`, `coupon_amount`, `discount_amount`, `pay_type`, `source_type`, `status`, `order_type`, `delivery_company`, `delivery_sn`, `auto_confirm_day`, `integration`, `growth`, `promotion_info`, `bill_type`, `bill_header`, `bill_content`, `bill_receiver_phone`, `bill_receiver_email`, `receiver_name`, `receiver_phone`, `receiver_post_code`, `receiver_province`, `receiver_city`, `receiver_region`, `receiver_detail_address`, `note`, `confirm_status`, `delete_status`, `use_integration`, `payment_time`, `delivery_time`, `receive_time`, `comment_time`, `modify_time`)
VALUES
(1001, 100, NULL, 'ORD1001', '2026-07-08 10:00:00', 'U100', 399.00, 399.00, 0.00, 0.00, 0.00, 0.00, 0.00, 1, 1, 3, 0, '顺丰速运', 'SF1000001', 15, 0, 0, '无优惠', 0, NULL, NULL, NULL, NULL, '测试用户', '19900001000', '200000', '上海市', '上海市', '浦东新区', '世纪大道 100 号', 'Agent 联调订单：已完成', 1, 0, NULL, '2026-07-08 10:05:00', '2026-07-08 18:00:00', '2026-07-09 12:00:00', NULL, '2026-07-09 12:00:00'),
(1002, 100, NULL, 'ORD1002', '2026-07-08 11:00:00', 'U100', 299.00, 299.00, 0.00, 0.00, 0.00, 0.00, 0.00, 1, 1, 2, 0, '顺丰速运', 'SF1000002', 15, 0, 0, '无优惠', 0, NULL, NULL, NULL, NULL, '测试用户', '19900001000', '200000', '上海市', '上海市', '浦东新区', '世纪大道 100 号', 'Agent 联调订单：运输中', 0, 0, NULL, '2026-07-08 11:05:00', '2026-07-08 19:00:00', NULL, NULL, '2026-07-08 19:00:00');

INSERT INTO `oms_order_item`
(`id`, `order_id`, `order_sn`, `product_id`, `product_pic`, `product_name`, `product_brand`, `product_sn`, `product_price`, `product_quantity`, `product_sku_id`, `product_sku_code`, `product_category_id`, `promotion_name`, `promotion_amount`, `coupon_amount`, `integration_amount`, `real_amount`, `gift_integration`, `gift_growth`, `product_attr`)
VALUES
(10001, 1001, 'ORD1001', 501, '', '轻量跑鞋', 'AgentDemo', 'SKU1001', 399.00, 1, 50101, 'SKU1001', 29, '无优惠', 0.00, 0.00, 0.00, 399.00, 0, 0, '[{"key":"颜色","value":"黑色"},{"key":"尺码","value":"42"}]'),
(10002, 1002, 'ORD1002', 502, '', '防水外套', 'AgentDemo', 'SKU1002', 299.00, 1, 50201, 'SKU1002', 29, '无优惠', 0.00, 0.00, 0.00, 299.00, 0, 0, '[{"key":"颜色","value":"蓝色"},{"key":"尺码","value":"L"}]');

INSERT INTO `oms_order_operate_history`
(`id`, `order_id`, `operate_man`, `create_time`, `order_status`, `note`)
VALUES
(10001, 1001, '系统', '2026-07-08 10:00:00', 0, '订单创建'),
(10002, 1001, '后台管理员', '2026-07-08 18:00:00', 2, '完成发货'),
(10003, 1001, '用户', '2026-07-09 12:00:00', 3, '确认收货'),
(10004, 1002, '后台管理员', '2026-07-08 19:00:00', 2, '完成发货，运输中');

INSERT INTO `oms_order_return_apply`
(`id`, `member_id`, `apply_type`, `idempotency_key`, `order_id`, `company_address_id`, `product_id`, `order_sn`, `create_time`, `member_username`, `return_amount`, `return_name`, `return_phone`, `status`, `handle_time`, `product_pic`, `product_name`, `product_brand`, `product_attr`, `product_count`, `product_price`, `product_real_price`, `reason`, `description`, `proof_pics`, `handle_note`, `handle_man`, `receive_man`, `receive_time`, `receive_note`)
VALUES
(9001, 100, 'return', 'seed-return-9001', 1001, NULL, 501, 'ORD1001', '2026-07-09 13:00:00', 'U100', 399.00, '测试用户', '19900001000', 1, '2026-07-09 14:00:00', '', '轻量跑鞋', 'AgentDemo', '颜色：黑色；尺码：42', 1, 399.00, 399.00, '七天无理由退货', '用户申请七天无理由退货', '', '售后已受理，等待退货入库', 'admin', NULL, NULL, NULL);

SET FOREIGN_KEY_CHECKS = 1;
