Read one page of positions for an account, with optional view, lots, totals, and sorting. Obtain account_id_key from accounts_list. Continue by passing returned nextPageNo as request.page_number with the same filters; this tool does not aggregate pages or truncate results. Request lots_required only when lot data is needed; use positions and orders_list together when reviewing exposure.

Synthetic argument example:

```json
{
  "account_id_key": "synthetic-key",
  "request": {
    "count": 25,
    "page_number": 1,
    "view": "QUICK",
    "lots_required": false
  }
}
```
