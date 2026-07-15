FROM docker.elastic.co/elasticsearch/elasticsearch:8.18.1

# mall-search 的商品字段使用 ik_max_word，插件版本必须与 Elasticsearch 完全一致。
RUN bin/elasticsearch-plugin install --batch \
    https://get.infini.cloud/elasticsearch/analysis-ik/8.18.1
