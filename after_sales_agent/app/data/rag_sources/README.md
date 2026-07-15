# RAG 知识库源文件目录

这里用于存放 RAG 知识库的原始源文件。建议人工维护的源文件都放在本目录下，程序生成的切片、索引、向量元数据不要放在这里。

推荐子目录：

```text
policies/      # 售后政策、平台规则、退换货规则
faq/           # 客服 FAQ、常见问题
products/      # 商品说明、品类售后规则、特殊商品限制
logistics/     # 物流规则、承运商说明、配送异常处理
refunds/       # 退款到账、支付渠道、财务处理规则
mall_docs/     # mall 项目接口文档、业务流程说明
raw_exports/   # 从后台、知识库、飞书/语雀等导出的原始文件
```

后续建议把程序生成文件放到：

```text
after_sales_agent/app/data/rag_index/
```

这样可以保证 `rag_sources/` 始终是可追溯、可人工审阅的知识源。
