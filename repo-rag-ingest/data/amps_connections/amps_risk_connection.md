# AMPS Connection: amps-risk

topics: risk_metrics
host: host.docker.internal
tcp_port: 9011
admin_port: 8089

amps_sow_query(topic="risk_metrics", host="host.docker.internal", port=9011)
amps_list_topics(host="host.docker.internal", admin_port=8089)
