/ ─────────────────────────────────────────────────────────────────────────────
/ KDB+ Bond RFQ Server – Initialization script
/ Loaded at startup: q init.q -p 5000
/
/ Defines the bond_rfq table schema and utility functions.
/ In production, data is loaded from the historical store or replicated from AMPS.
/ In POC, data is loaded via the Python client after server starts.
/ ─────────────────────────────────────────────────────────────────────────────

/ ── Table schema ─────────────────────────────────────────────────────────────

bond_rfq:([]
    rfq_id:         `symbol$();
    desk:           `symbol$();
    trader_id:      `symbol$();
    trader_name:    `symbol$();
    isin:           `symbol$();
    bond_name:      `symbol$();
    issuer:         `symbol$();
    sector:         `symbol$();
    rating:         `symbol$();
    side:           `symbol$();
    notional_usd:   `float$();
    price:          `float$();
    spread_bps:     `float$();
    coupon:         `float$();
    rfq_date:       `date$();
    rfq_time:       `time$();
    response_time_ms:`long$();
    won:            `boolean$();
    hit_rate:       `float$();
    venue:          `symbol$()
    );

/ ── Utility functions ─────────────────────────────────────────────────────────

/ Best traders by hit rate for a given desk and date range
/ Usage: best_traders[`HY; 2024.01.01; 2024.12.31; 10]
best_traders:{[desk_sym; dt_from; dt_to; top_n]
    t: select from bond_rfq where desk=desk_sym, rfq_date within (dt_from; dt_to);
    agg: select rfq_count:count i, avg_spread_bps:avg spread_bps,
                total_notional:sum notional_usd, avg_hit_rate:avg hit_rate,
                win_count:sum won
         by trader_id, trader_name from t;
    top_n sublist `avg_hit_rate xdesc agg
    };

/ Desk summary
/ Usage: desk_summary[2024.01.01; 2024.12.31]
desk_summary:{[dt_from; dt_to]
    t: select from bond_rfq where rfq_date within (dt_from; dt_to);
    select rfq_count:count i, avg_spread_bps:avg spread_bps,
           total_notional:sum notional_usd, avg_hit_rate:avg hit_rate
    by desk from t
    };

-1 "KDB+ Bond RFQ server ready on port ", string system "p";
-1 "Tables: bond_rfq (", string count bond_rfq, " rows loaded)";
