Read balances and buying-power information for one account. First obtain account_id_key from accounts_list; optionally select account type and real-time NAV. Returns the complete client-modeled balance response. Balance data is an observation, not an order approval or guarantee of future buying power.

Synthetic argument example:

```json
{
  "account_id_key": "synthetic-key",
  "request": {
    "real_time_nav": true
  }
}
```
