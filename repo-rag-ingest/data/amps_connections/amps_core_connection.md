# AMPS Connection: amps-core

topics: orders, positions, market-data
host: host.docker.internal
tcp_port: 9007
admin_port: 8085

amps_sow_query(topic="orders", host="host.docker.internal", port=9007)
amps_sow_query(topic="positions", host="host.docker.internal", port=9007)
amps_sow_query(topic="market-data", host="host.docker.internal", port=9007)
amps_list_topics(host="host.docker.internal", admin_port=8085)
