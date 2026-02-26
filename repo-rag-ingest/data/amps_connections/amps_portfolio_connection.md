# AMPS Connection: amps-portfolio

topics: portfolio_nav
host: host.docker.internal
tcp_port: 9008
admin_port: 8086

amps_sow_query(topic="portfolio_nav", host="host.docker.internal", port=9008)
amps_list_topics(host="host.docker.internal", admin_port=8086)
